"""McpToolRegistry contra el servidor MCP real en memoria (sin subproceso) y contra un proceso que muere."""

import sys

import pytest
from mcp import Client, StdioServerParameters

from mcp_meta import USER_QUESTION_META
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
    assert result.startswith("AVISO: «Lorenzo» no aparece")


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


async def test_pregunta_original_por_meta_detecta_nombre_aunque_el_modelo_busque_solo_apellido(store):
    registry = _registry(build_server(store))
    try:
        await registry.connect()
        result = await registry.call(TOOL_NAME, {"tema": "Alvarez"}, user_question="¿Quién fue Juan Alvarez?")
    finally:
        await registry.aclose()
    assert result.startswith("AVISO: «Juan Alvarez» no aparece")
    assert "debates_origen_03" in result


@pytest.mark.parametrize(
    ("tema", "question"),
    [
        ("historia de Las Varillas", "¿Qué sabés de la historia de Las Varillas?"),
        ("Valter Dabbene", "Hola Valter Dabbene, ¿quién es?"),
    ],
)
async def test_preguntas_validas_no_generan_aviso(store, tema, question):
    registry = _registry(build_server(store))
    try:
        await registry.connect()
        result = await registry.call(TOOL_NAME, {"tema": tema}, user_question=question)
    finally:
        await registry.aclose()
    assert not result.startswith("AVISO")
    assert "debates_origen_02" in result


async def test_meta_invalido_se_ignora_sin_romper_la_tool(store):
    async with Client(build_server(store)) as client:
        result = await client.call_tool(TOOL_NAME, {"tema": "Lorenzo Dabbene"}, meta={USER_QUESTION_META: {"x": 1}})
    [block] = result.content
    assert not result.is_error
    assert block.text.startswith("AVISO: «Lorenzo» no aparece")  # cae al tema, como sin _meta


async def test_aviso_acota_cantidad_y_largo_de_terminos(store):
    long_word = "x" * 60
    question = f"¿Qué dicen alfa beta gama {long_word}?"
    registry = _registry(build_server(store))
    try:
        await registry.connect()
        result = await registry.call(TOOL_NAME, {"tema": question}, user_question=question)
    finally:
        await registry.aclose()
    warning = result.split("\n", 1)[0]
    assert long_word not in result
    assert warning.startswith("AVISO: «dicen», «alfa», «beta» no aparece")


async def test_terminos_inventados_por_el_modelo_no_se_repiten(store):
    registry = _registry(build_server(store))
    try:
        await registry.connect()
        result = await registry.call(TOOL_NAME, {"tema": "mundoalberto2022"}, user_question="¿Quién ganó el mundial 2022?")
    finally:
        await registry.aclose()
    assert "mundoalberto2022" not in result
    assert result.startswith("Sin documentos")


async def test_tema_es_obligatorio_y_vacio_pide_palabras_clave(store):
    registry = _registry(build_server(store))
    try:
        [spec] = await registry.specs()
        result = await registry.call(TOOL_NAME, {"tema": "  "})
    finally:
        await registry.aclose()
    assert spec.parameters["required"] == ["tema"]
    assert "palabras clave" in result


async def test_sin_resultados_devuelve_indice_para_reintentar(store):
    registry = _registry(build_server(store))
    try:
        await registry.connect()
        result = await registry.call(TOOL_NAME, {"tema": "tren"})
    finally:
        await registry.aclose()
    assert result.startswith("AVISO") and "Sin documentos" in result
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
