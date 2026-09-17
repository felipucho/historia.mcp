"""Registro de herramientas. McpToolRegistry descubre las tools del servidor MCP: agregar una tool no toca main.py."""

import asyncio
import logging
import time
from abc import ABC, abstractmethod
from typing import Any

from mcp import Client, MCPError, StdioServerParameters
from mcp.server.mcpserver import MCPServer
from mcp.types import TextContent

from llm.provider import ToolSpec
from mcp_meta import USER_QUESTION_META

logger = logging.getLogger(__name__)

_CONNECTION_CLOSED = -32000
_LIVENESS_TIMEOUT = 3.0
_STOP_TIMEOUT = 5.0


async def _fetch_tools(client: Client) -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}
    cursor: str | None = None
    while True:
        listing = await client.list_tools(cursor=cursor, cache_mode="bypass")
        for tool in listing.tools:
            tools[tool.name] = ToolSpec(name=tool.name, description=tool.description or "", parameters=tool.input_schema)
        if not (cursor := listing.next_cursor):
            return tools


class ToolError(Exception):
    """La herramienta falló. El mensaje vuelve al modelo como resultado de la tool."""


class ToolsUnavailable(Exception):
    """El backend de herramientas no está disponible."""


class ToolRegistry(ABC):
    @abstractmethod
    async def specs(self) -> list[ToolSpec]:
        """Tools disponibles. Lanza ToolsUnavailable."""

    @abstractmethod
    async def call(self, name: str, arguments: dict[str, Any], *, user_question: str | None = None) -> str:
        """Ejecuta una tool. Lanza ToolError o ToolsUnavailable."""


class McpToolRegistry(ToolRegistry):
    """Conexión MCP con reintento y backoff exponencial.

    El cliente MCP usa task groups de anyio: el contexto debe abrirse y cerrarse en la MISMA
    tarea. Por eso vive en una tarea supervisora propia y no en el handler que dispara la reconexión.
    """

    def __init__(
        self,
        server: StdioServerParameters | MCPServer,
        *,
        connect_timeout: float,
        call_timeout: float,
        retry_base: float,
        retry_max: float,
    ) -> None:
        self._server = server
        self._connect_timeout = connect_timeout
        self._call_timeout = call_timeout
        self._retry_base = retry_base
        self._retry_max = retry_max
        self._client: Client | None = None
        self._tools: dict[str, ToolSpec] = {}
        self._task: asyncio.Task[None] | None = None
        self._stop: asyncio.Event | None = None
        self._lock = asyncio.Lock()
        self._failures = 0
        self._retry_at = 0.0

    async def connect(self) -> None:
        async with self._lock:
            if self._client is None:
                await self._connect_locked()

    async def specs(self) -> list[ToolSpec]:
        # tools/list sirve de chequeo de vida (ping no existe desde el protocolo 2026-07-28)
        # y refresca las tools si el servidor cambió.
        client = await self._ensure()
        try:
            self._tools = await asyncio.wait_for(_fetch_tools(client), _LIVENESS_TIMEOUT)
        except Exception as exc:  # proceso muerto o colgado: se reconecta en este mismo mensaje
            logger.warning("mcp_liveness_failed", extra={"error": repr(exc)})
            await self._invalidate(client)
            await self._ensure()
        return list(self._tools.values())

    async def call(self, name: str, arguments: dict[str, Any], *, user_question: str | None = None) -> str:
        if name not in self._tools:
            raise ToolError(f"Herramienta desconocida: {name}. Disponibles: {', '.join(self._tools)}")
        client = await self._ensure()
        meta = {USER_QUESTION_META: user_question} if user_question else None
        try:
            result = await client.call_tool(name, arguments, read_timeout_seconds=self._call_timeout, meta=meta)
        except MCPError as exc:
            if exc.code == _CONNECTION_CLOSED:
                await self._invalidate(client)
                raise ToolsUnavailable("Se perdió la conexión con el servidor MCP") from exc
            raise ToolError(exc.message) from exc
        except Exception as exc:
            await self._invalidate(client)
            raise ToolsUnavailable("Se perdió la conexión con el servidor MCP") from exc
        text = "\n".join(block.text for block in result.content if isinstance(block, TextContent)).strip()
        if result.is_error:
            raise ToolError(text or "La herramienta devolvió un error sin detalle")
        return text or "(sin resultados)"

    async def aclose(self) -> None:
        async with self._lock:
            await self._stop_supervisor()

    async def _ensure(self) -> Client:
        if self._client is not None:
            return self._client
        async with self._lock:
            if self._client is None:
                if (wait := self._retry_at - time.monotonic()) > 0:
                    raise ToolsUnavailable(f"Servidor MCP no disponible; próximo reintento en {wait:.0f}s")
                await self._connect_locked()
        assert self._client is not None
        return self._client

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
        logger.info("mcp_connected", extra={"tools": sorted(self._tools)})

    async def _supervise(self, ready: asyncio.Future[Client], stop: asyncio.Event) -> None:
        try:
            async with Client(self._server) as client:
                self._tools = await _fetch_tools(client)
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

    async def _invalidate(self, client: Client) -> None:
        async with self._lock:
            if self._client is client:
                await self._stop_supervisor()

    async def _stop_supervisor(self) -> None:
        task, stop = self._task, self._stop
        self._client, self._task, self._stop = None, None, None
        if task is None or stop is None:
            return
        stop.set()
        try:
            await asyncio.wait_for(task, _STOP_TIMEOUT)
        except TimeoutError:
            logger.warning("mcp_stop_timeout")
        except Exception as exc:
            logger.warning("mcp_stop_error", extra={"error": repr(exc)})
