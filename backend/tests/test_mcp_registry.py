"""McpToolRegistry contra el servidor MCP real en memoria (sin subproceso) y contra un proceso que muere."""

import sys

import pytest
from mcp import StdioServerParameters

from mcp_server import build_server
from tests.conftest import TOOL_NAME
from tools.registry import McpToolRegistry, ToolError, ToolsUnavailable


def _registry(server, **overrides) -> McpToolRegistry:
    options = {"connect_timeout": 20.0, "call_timeout": 5.0, "retry_base": 30.0, "retry_max": 60.0} | overrides
    return McpToolRegistry(server, **options)


async def test_descubre_tools_y_ejecuta_busqueda(store):
    registry = _registry(build_server(store))
    try:
        await registry.connect()
        [spec] = await registry.specs()
        result = await registry.call(TOOL_NAME, {"tema": "¿Quién es Lorenzo Dabbene?"})
    finally:
        await registry.aclose()

    assert spec.name == TOOL_NAME
    assert "tema" in spec.parameters["properties"]
    assert "Valter Dabbene" in result and "debates_origen_01" not in result


async def test_specs_reutiliza_la_conexion_viva(store, caplog):
    registry = _registry(build_server(store))
    caplog.set_level("INFO", logger="tools.registry")
    try:
        for _ in range(3):
            await registry.specs()
    finally:
        await registry.aclose()
    assert [r.msg for r in caplog.records].count("mcp_connected") == 1
    assert "mcp_liveness_failed" not in [r.msg for r in caplog.records]


async def test_tema_vacio_devuelve_indice(store):
    registry = _registry(build_server(store))
    try:
        await registry.connect()
        result = await registry.call(TOOL_NAME, {})
    finally:
        await registry.aclose()
    assert result.count("- ID:") == 3


async def test_tool_desconocida_es_tool_error(store):
    registry = _registry(build_server(store))
    try:
        await registry.connect()
        with pytest.raises(ToolError):
            await registry.call("preguntar_a_ollama", {"prompt": "x"})
    finally:
        await registry.aclose()


async def test_servidor_que_muere_aplica_backoff():
    dead = StdioServerParameters(command=sys.executable, args=["-c", "import sys; sys.exit(3)"])
    registry = _registry(dead, connect_timeout=10.0)

    with pytest.raises(ToolsUnavailable):
        await registry.connect()
    with pytest.raises(ToolsUnavailable, match="próximo reintento"):
        await registry.specs()
    await registry.aclose()
