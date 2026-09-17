import pytest
from fastapi import FastAPI
from fastapi.testclient import TestClient
from starlette.websockets import WebSocketDisconnect

from agents.historian import HistorianAgent
from api import ws
from api.ratelimit import ConnectionLimiter
from config import Settings
from llm.provider import LLMResponse, LLMUnavailable
from tests.conftest import FakeLLM, FakeTools

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
    while (event := socket.receive_json())["type"] == "status":
        pass
    assert socket.receive_json() == {"type": "status", "state": "idle"}
    return event


def test_flujo_completo_estados_y_respuesta():
    with _connect(_client()) as socket:
        socket.send_json({"text": "hola"})
        assert socket.receive_json() == {"type": "status", "state": "thinking"}
        assert socket.receive_json() == {"type": "response", "content": "hola"}
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
        assert _until_final(socket) == {"type": "response", "content": "primera"}
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
