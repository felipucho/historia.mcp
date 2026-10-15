"""Implementación MCP del contrato de tools.base. McpToolRegistry descubre las tools del servidor MCP: agregar una tool no toca main.py."""

import asyncio
import logging
from typing import Any, cast

from llm.provider import ToolSpec
from mcp import Client, MCPError, StdioServerParameters
from mcp.server.mcpserver import MCPServer
from mcp.types import RequestParamsMeta, TextContent
from mcp_meta import USER_QUESTION_META

from tools.base import ToolError, ToolRegistry, ToolsUnavailable
from tools.mcp_supervisor import McpSupervisor

logger = logging.getLogger(__name__)

_CONNECTION_CLOSED = -32000
_LIVENESS_TIMEOUT = 3.0


async def _fetch_tools(client: Client) -> dict[str, ToolSpec]:
    tools: dict[str, ToolSpec] = {}
    cursor: str | None = None
    while True:
        listing = await client.list_tools(cursor=cursor, cache_mode="bypass")
        for tool in listing.tools:
            tools[tool.name] = ToolSpec(name=tool.name, description=tool.description or "", parameters=tool.input_schema)
        if not (cursor := listing.next_cursor):
            return tools


class McpToolRegistry(ToolRegistry):
    """Descubre y ejecuta las tools del servidor MCP. La conexión y los reintentos los maneja McpSupervisor."""

    def __init__(
        self,
        server: StdioServerParameters | MCPServer,
        *,
        connect_timeout: float,
        call_timeout: float,
        retry_base: float,
        retry_max: float,
    ) -> None:
        self._call_timeout = call_timeout
        self._tools: dict[str, ToolSpec] = {}
        self._supervisor = McpSupervisor(
            server,
            connect_timeout=connect_timeout,
            retry_base=retry_base,
            retry_max=retry_max,
            on_open=self._on_open,
        )

    async def connect(self) -> None:
        await self._supervisor.connect()

    async def specs(self) -> list[ToolSpec]:
        # tools/list sirve de chequeo de vida (ping no existe desde el protocolo 2026-07-28)
        # y refresca las tools si el servidor cambió.
        client = await self._supervisor.client()
        try:
            self._tools = await asyncio.wait_for(_fetch_tools(client), _LIVENESS_TIMEOUT)
        except Exception as exc:  # noqa: BLE001 - proceso muerto o colgado: se reconecta en este mismo mensaje
            logger.warning("mcp_liveness_failed", extra={"error": repr(exc)})
            await self._supervisor.invalidate(client)
            await self._supervisor.client()
        return list(self._tools.values())

    async def call(self, name: str, arguments: dict[str, Any], *, user_question: str | None = None) -> str:
        if name not in self._tools:
            raise ToolError(f"Herramienta desconocida: {name}. Disponibles: {', '.join(self._tools)}")
        client = await self._supervisor.client()
        meta = cast(RequestParamsMeta, {USER_QUESTION_META: user_question}) if user_question else None
        try:
            result = await client.call_tool(name, arguments, read_timeout_seconds=self._call_timeout, meta=meta)
        except MCPError as exc:
            if exc.code == _CONNECTION_CLOSED:
                await self._supervisor.invalidate(client)
                raise ToolsUnavailable("Se perdió la conexión con el servidor MCP") from exc
            raise ToolError(exc.message) from exc
        except Exception as exc:
            await self._supervisor.invalidate(client)
            raise ToolsUnavailable("Se perdió la conexión con el servidor MCP") from exc
        text = "\n".join(block.text for block in result.content if isinstance(block, TextContent)).strip()
        if result.is_error:
            raise ToolError(text or "La herramienta devolvió un error sin detalle")
        return text or "(sin resultados)"

    async def aclose(self) -> None:
        await self._supervisor.aclose()

    async def _on_open(self, client: Client) -> None:
        # Las tools se descubren dentro de la tarea supervisora: si falla, la conexión cuenta como fallida y entra el backoff.
        self._tools = await _fetch_tools(client)
        logger.info("mcp_connected", extra={"tools": sorted(self._tools)})
