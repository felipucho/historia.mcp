"""Ciclo de vida del cliente MCP: conexión, reintento con backoff y cierre. No conoce las tools."""

import asyncio
import logging
import time
from collections.abc import Awaitable, Callable

from mcp import Client, StdioServerParameters
from mcp.server.mcpserver import MCPServer

from tools.base import ToolsUnavailable

logger = logging.getLogger(__name__)

_STOP_TIMEOUT = 5.0

# Corre dentro de la tarea supervisora, con el cliente ya abierto y antes de dar la conexión por lista.
OnOpen = Callable[[Client], Awaitable[None]]


# SOLID-S (responsabilidad única): mantiene viva la sesión con el servidor MCP.
# Conexión, backoff y cierre viven aquí. McpToolRegistry solo pide el cliente.
class McpSupervisor:
    """Mantiene una sesión MCP viva y la reconecta con backoff exponencial.

    El cliente MCP usa task groups de anyio: el contexto debe abrirse y cerrarse en la MISMA tarea.
    Por eso la sesión vive en una tarea supervisora propia y no en el handler que dispara la reconexión.
    """

    def __init__(
        self,
        server: StdioServerParameters | MCPServer,
        *,
        connect_timeout: float,
        retry_base: float,
        retry_max: float,
        on_open: OnOpen,
    ) -> None:
        self._server = server
        self._connect_timeout = connect_timeout
        self._retry_base = retry_base
        self._retry_max = retry_max
        self._on_open = on_open
        self._client: Client | None = None
        self._task: asyncio.Task[None] | None = None
        self._stop: asyncio.Event | None = None
        self._lock = asyncio.Lock()
        self._failures = 0
        self._retry_at = 0.0

    async def connect(self) -> None:
        async with self._lock:
            if self._client is None:
                await self._connect_locked()

    async def client(self) -> Client:
        """Cliente vivo. Si la conexión cayó, reconecta respetando el backoff o lanza ToolsUnavailable."""
        if self._client is not None:
            return self._client
        async with self._lock:
            if self._client is None:
                if (wait := self._retry_at - time.monotonic()) > 0:
                    raise ToolsUnavailable(f"Servidor MCP no disponible; próximo reintento en {wait:.0f}s")
                await self._connect_locked()
        assert self._client is not None
        return self._client

    async def invalidate(self, client: Client) -> None:
        """Cierra la sesión solo si todavía es la vigente: dos handlers que fallan a la vez no cierran una sesión nueva."""
        async with self._lock:
            if self._client is client:
                await self._stop_locked()

    async def aclose(self) -> None:
        async with self._lock:
            await self._stop_locked()

    async def _connect_locked(self) -> None:
        ready: asyncio.Future[Client] = asyncio.get_running_loop().create_future()
        stop = asyncio.Event()
        task = asyncio.create_task(self._supervise(ready, stop), name="mcp-supervisor")
        try:
            client = await asyncio.wait_for(asyncio.shield(ready), self._connect_timeout)
        except Exception as exc:
            stop.set()
            task.cancel()
            await asyncio.gather(task, return_exceptions=True)
            if ready.done() and not ready.cancelled():
                ready.exception()  # marca la excepción como consumida
            self._failures += 1
            delay = min(self._retry_max, self._retry_base * 2 ** (self._failures - 1))
            self._retry_at = time.monotonic() + delay
            logger.error("mcp_connect_failed", extra={"error": repr(exc), "retry_in_s": delay})
            raise ToolsUnavailable("Servidor MCP no disponible") from exc
        self._client, self._task, self._stop = client, task, stop
        self._failures = 0

    async def _supervise(self, ready: asyncio.Future[Client], stop: asyncio.Event) -> None:
        try:
            async with Client(self._server) as client:
                await self._on_open(client)
                ready.set_result(client)
                await stop.wait()
        except BaseException as exc:
            if not ready.done():
                ready.set_exception(exc if isinstance(exc, Exception) else ToolsUnavailable("conexión cancelada"))
            elif not isinstance(exc, asyncio.CancelledError):
                logger.error("mcp_supervisor_error", extra={"error": repr(exc)})
            if isinstance(exc, asyncio.CancelledError):
                raise
        finally:
            if ready.done() and not ready.cancelled() and ready.exception() is None:
                logger.info("mcp_disconnected")

    async def _stop_locked(self) -> None:
        task, stop = self._task, self._stop
        self._client, self._task, self._stop = None, None, None
        if task is None or stop is None:
            return
        stop.set()
        try:
            await asyncio.wait_for(task, _STOP_TIMEOUT)
        except TimeoutError:
            logger.warning("mcp_stop_timeout")
        except Exception as exc:  # noqa: BLE001 - el cierre no debe fallar por un hijo en mal estado
            logger.warning("mcp_stop_error", extra={"error": repr(exc)})
