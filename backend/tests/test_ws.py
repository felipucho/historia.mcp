import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agents.historian import HistorianAgent
from api import ws
from api.ratelimit import ConnectionLimiter
from config import Settings
from llm.provider import LLMResponse, LLMUnavailable, ToolCall
from store.history import render_documents, render_index
from tests.conftest import TOOL_NAME, FakeLLM, FakeTools

ORIGIN = "http://localhost:5173"


def _echo_users(messages) -> LLMResponse:
    return LLMResponse(content="|".join(m.content for m in messages if m.role == "user"))


def _client(llm=None, tools=None, **settings_overrides) -> TestClient:
    settings = Settings(_env_file=None, cors_origins=[ORIGIN], **settings_overrides)
    app = FastAPI()
    app.include_router(ws.router)
    app.state.settings = settings
    app.state.agent = HistorianAgent(llm or FakeLLM(_echo_users), tools or FakeTools(), "SYSTEM")
    app.state.connections = ConnectionLimiter(settings.ws_max_connections_per_ip)
    return TestClient(app)


def _connect(client: TestClient, origin: str = ORIGIN):
    return client.websocket_connect("/ws/chat", headers={"origin": origin})


def _until_final(socket) -> dict:
    """Consume eventos hasta response/error y el idle posterior."""
    while (event := socket.receive_json())["type"] in ("status", "delta"):
        pass
    assert socket.receive_json() == {"type": "status", "state": "idle"}
    return event


def test_flujo_completo_estados_y_respuesta():
    with _connect(_client()) as socket:
        socket.send_json({"text": "hola"})
        assert socket.receive_json() == {"type": "status", "state": "thinking"}
        assert socket.receive_json() == {"type": "delta", "content": "hola"}
        assert socket.receive_json() == {"type": "response", "content": "hola", "provider": "local"}
        assert socket.receive_json() == {"type": "status", "state": "idle"}


def test_criterio_9_origin_ajeno_cierra_1008():
    with _connect(_client(), origin="https://evil.example") as socket:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            socket.receive_json()
    assert excinfo.value.code == 1008


def test_sin_origin_cierra_1008():
    with _client().websocket_connect("/ws/chat") as socket:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            socket.receive_json()
    assert excinfo.value.code == 1008


def test_criterio_4_dos_clientes_no_comparten_historial():
    client = _client()
    with _connect(client) as a, _connect(client) as b:
        a.send_json({"text": "soy A"})
        assert _until_final(a)["content"] == "soy A"
        b.send_json({"text": "soy B"})
        assert _until_final(b)["content"] == "soy B"
        a.send_json({"text": "¿quién soy?"})
        assert _until_final(a)["content"] == "soy A|¿quién soy?"


def test_criterio_5_segundo_mensaje_en_curso_recibe_busy():
    llm = FakeLLM(_echo_users, delay=0.5)
    with _connect(_client(llm=llm)) as socket:
        socket.send_json({"text": "primera"})
        assert socket.receive_json() == {"type": "status", "state": "thinking"}
        socket.send_json({"text": "segunda"})
        assert socket.receive_json()["code"] == "busy"
        assert _until_final(socket) == {"type": "response", "content": "primera", "provider": "local"}
        socket.send_json({"text": "tercera"})
        assert _until_final(socket)["content"] == "primera|tercera"


def test_criterio_6_llm_caido_mensaje_claro_sin_detalle_interno():
    llm = FakeLLM([LLMUnavailable("ConnectError http://10.0.0.5:11434 Traceback")])
    with _connect(_client(llm=llm)) as socket:
        socket.send_json({"text": "hola"})
        event = _until_final(socket)
    assert event["code"] == "llm_unavailable"
    assert "http" not in event["message"] and "Traceback" not in event["message"]


def test_mcp_caido_devuelve_tools_unavailable():
    with _connect(_client(tools=FakeTools(unavailable=True))) as socket:
        socket.send_json({"text": "¿Quién es Dabbene?"})
        assert _until_final(socket)["code"] == "tools_unavailable"


@pytest.mark.parametrize(
    "frame",
    ["no es json", '{"text": "   "}', '{"text": "' + "a" * 1001 + '"}', '{"text": "hola", "extra": 1}', '{"txt": "hola"}'],
)
def test_input_invalido(frame):
    with _connect(_client()) as socket:
        socket.send_text(frame)
        assert socket.receive_json()["code"] == "invalid_input"


def test_frame_binario_es_invalido():
    with _connect(_client()) as socket:
        socket.send_bytes(b'{"text": "hola"}')
        assert socket.receive_json()["code"] == "invalid_input"


def test_rate_limit_por_conexion():
    with _connect(_client(ws_rate_capacity=1, ws_rate_refill_per_minute=0.01)) as socket:
        socket.send_json({"text": "uno"})
        _until_final(socket)
        socket.send_json({"text": "dos"})
        assert socket.receive_json()["code"] == "rate_limited"


def test_limite_de_conexiones_por_ip():
    client = _client(ws_max_connections_per_ip=1)
    with _connect(client), _connect(client) as second:
        with pytest.raises(WebSocketDisconnect) as excinfo:
            second.receive_json()
    assert excinfo.value.code == 1013


def test_sanitiza_control_y_normaliza_nfc():
    assert ws.sanitize_text("  Café\x00‮ ok\n ") == "Café ok"


def test_provider_cloud_responde_con_su_modelo_y_comparte_historial():
    local, cloud = FakeLLM(_echo_users), FakeLLM(lambda messages: LLMResponse(content="nube"))
    with _connect(_client(llm={"local": local, "cloud": cloud})) as socket:
        socket.send_json({"text": "uno"})
        assert _until_final(socket)["provider"] == "local"
        socket.send_json({"text": "dos", "provider": "cloud"})
        assert _until_final(socket) == {"type": "response", "content": "nube", "provider": "cloud"}
    # Cambiar de modelo no borra la conversación: la nube ve el turno que respondió el local.
    assert [m.content for m in cloud.calls[0] if m.role == "user"] == ["uno", "dos"]


def test_provider_cloud_sin_configurar_devuelve_provider_unavailable():
    with _connect(_client()) as socket:
        socket.send_json({"text": "hola", "provider": "cloud"})
        event = _until_final(socket)
    assert event["code"] == "provider_unavailable"
    assert "GROQ_API_KEY" in event["message"]


def test_provider_desconocido_es_input_invalido():
    with _connect(_client()) as socket:
        socket.send_json({"text": "hola", "provider": "gpt"})
        assert socket.receive_json()["code"] == "invalid_input"


def test_citas_y_detalle_de_la_tool(store):
    doc = store.documents[0]
    llm = FakeLLM([
        LLMResponse(tool_calls=[ToolCall(name=TOOL_NAME, arguments={"tema": "ferrocarril"})]),
        LLMResponse(content="Llegó en 1900."),
    ])
    tools = FakeTools({TOOL_NAME: render_documents([doc, doc])})
    with _connect(_client(llm=llm, tools=tools)) as socket:
        socket.send_json({"text": "¿Cuándo llegó el tren?"})
        assert socket.receive_json() == {"type": "status", "state": "thinking"}
        assert socket.receive_json() == {"type": "status", "state": "tool_call", "tool": TOOL_NAME, "detail": "ferrocarril"}
        event = _until_final(socket)
    assert event["sources"] == [doc.id]


def test_sin_resultados_de_tool_no_hay_citas(store):
    llm = FakeLLM([
        LLMResponse(tool_calls=[ToolCall(name=TOOL_NAME, arguments={"tema": "intendente"})]),
        LLMResponse(content="No hay registros."),
    ])
    # El resultado sin documentos trae el índice ("- ID: x |"), que no cuenta como cita.
    tools = FakeTools({TOOL_NAME: "Sin documentos. Índice:\n" + render_index(store.documents)})
    with _connect(_client(llm=llm, tools=tools)) as socket:
        socket.send_json({"text": "¿Quién fue el primer intendente?"})
        assert "sources" not in _until_final(socket)


def test_deltas_llegan_antes_de_la_respuesta_final():
    class StreamingLLM(FakeLLM):
        async def chat_stream(self, messages, tools, on_delta):
            for piece in ("Lle", "gó en ", "1900."):
                await on_delta(piece)
            return LLMResponse(content="Llegó en 1900.")

    with _connect(_client(llm=StreamingLLM([]))) as socket:
        socket.send_json({"text": "¿Cuándo llegó el tren?"})
        events = []
        while (event := socket.receive_json())["type"] != "response":
            events.append(event)
        assert socket.receive_json() == {"type": "status", "state": "idle"}
    assert [e["content"] for e in events if e["type"] == "delta"] == ["Lle", "gó en ", "1900."]
    assert event["content"] == "Llegó en 1900."
