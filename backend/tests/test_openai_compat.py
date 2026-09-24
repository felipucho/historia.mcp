import json

import httpx
import pytest

from llm.openai_compat import OpenAICompatClient
from llm.provider import InvalidToolCall, LLMError, LLMTimeout, LLMUnavailable, Message, ToolCall
from tests.conftest import TOOL_NAME, TOOL_SPEC


def _client(handler, api_key: str = "gsk_test") -> OpenAICompatClient:
    return OpenAICompatClient(
        "http://groq.test/openai/v1",
        "llama-3.3-70b-versatile",
        api_key,
        temperature=0.3,
        connect_timeout=5,
        read_timeout=30,
        transport=httpx.MockTransport(handler),
    )


def _reply(message: dict) -> httpx.Response:
    return httpx.Response(200, json={"choices": [{"index": 0, "message": {"role": "assistant", **message}}]})


async def test_payload_en_formato_openai_con_key_y_arguments_como_string():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["url"] = str(request.url)
        captured["auth"] = request.headers.get("authorization")
        captured["body"] = json.loads(request.content)
        return _reply({"content": "ok"})

    call = ToolCall(id="call_1", name=TOOL_NAME, arguments={"tema": "Dabbene"})
    history = [
        Message(role="system", content="sys"),
        Message(role="user", content="¿Quién es Dabbene?"),
        Message(role="assistant", tool_calls=[call]),
        Message(role="tool", content="Valter Dabbene", tool_call_id="call_1", name=TOOL_NAME),
    ]
    response = await _client(handler).chat(history, [TOOL_SPEC])

    assert response.content == "ok"
    assert captured["url"] == "http://groq.test/openai/v1/chat/completions"
    assert captured["auth"] == "Bearer gsk_test"
    body = captured["body"]
    assert body["temperature"] == 0.3
    assert body["tools"][0]["function"]["name"] == TOOL_NAME
    assert body["messages"][2]["tool_calls"][0]["function"]["arguments"] == '{"tema": "Dabbene"}'
    assert body["messages"][3] == {"role": "tool", "content": "Valter Dabbene", "tool_call_id": "call_1"}


async def test_tool_calls_de_la_respuesta():
    def handler(request: httpx.Request) -> httpx.Response:
        return _reply({
            "content": None,
            "tool_calls": [{"id": "call_x", "type": "function", "function": {"name": TOOL_NAME, "arguments": '{"tema": "tren"}'}}],
        })

    response = await _client(handler).chat([Message(role="user", content="tren")], [TOOL_SPEC])
    assert response.content == ""
    assert response.tool_calls == [ToolCall(id="call_x", name=TOOL_NAME, arguments={"tema": "tren"})]


async def test_arguments_invalidos():
    def handler(request: httpx.Request) -> httpx.Response:
        return _reply({"tool_calls": [{"id": "c", "function": {"name": TOOL_NAME, "arguments": "{no json"}}]})

    with pytest.raises(InvalidToolCall):
        await _client(handler).chat([Message(role="user", content="x")], [TOOL_SPEC])


async def test_sin_key_no_hace_request():
    def handler(request: httpx.Request) -> httpx.Response:
        raise AssertionError("no debería llamar a la red")

    client = _client(handler, api_key="")
    with pytest.raises(LLMUnavailable, match="GROQ_API_KEY"):
        await client.chat([Message(role="user", content="x")], [])
    with pytest.raises(LLMUnavailable):
        await client.health()


@pytest.mark.parametrize(
    ("status", "body", "error", "match"),
    [
        (401, "invalid api key", LLMUnavailable, "inválida"),
        (429, "rate limit", LLMUnavailable, "límite gratuito"),
        (400, '{"error": {"code": "tool_use_failed"}}', InvalidToolCall, "herramienta"),
        (500, "boom", LLMError, "500"),
    ],
)
async def test_errores_http(status, body, error, match):
    client = _client(lambda request: httpx.Response(status, text=body))
    with pytest.raises(error, match=match):
        await client.chat([Message(role="user", content="x")], [])


async def test_timeout():
    def handler(request: httpx.Request) -> httpx.Response:
        raise httpx.ReadTimeout("lento", request=request)

    with pytest.raises(LLMTimeout):
        await _client(handler).chat([Message(role="user", content="x")], [])


def _sse(*events: dict | str) -> httpx.Response:
    lines = [f"data: {event if isinstance(event, str) else json.dumps(event)}\n\n" for event in events]
    return httpx.Response(200, content="".join(lines).encode(), headers={"content-type": "text/event-stream"})


def _delta(**delta) -> dict:
    return {"choices": [{"index": 0, "delta": delta}]}


async def _stream(client: OpenAICompatClient):
    deltas: list[str] = []

    async def on_delta(text: str) -> None:
        deltas.append(text)

    response = await client.chat_stream([Message(role="user", content="x")], [TOOL_SPEC], on_delta)
    return response, deltas


async def test_stream_emite_deltas_de_texto():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _sse(_delta(role="assistant", content=""), _delta(content="Llegó "), _delta(content="en 1900."), {"choices": []}, "[DONE]")

    response, deltas = await _stream(_client(handler))
    assert captured["body"]["stream"] is True
    assert deltas == ["Llegó ", "en 1900."]
    assert response.content == "Llegó en 1900."


async def test_stream_arma_tool_call_fragmentada():
    def handler(request: httpx.Request) -> httpx.Response:
        return _sse(
            _delta(tool_calls=[{"index": 0, "id": "call_1", "type": "function", "function": {"name": TOOL_NAME, "arguments": ""}}]),
            _delta(tool_calls=[{"index": 0, "function": {"arguments": '{"tema": '}}]),
            _delta(tool_calls=[{"index": 0, "function": {"arguments": '"tren"}'}}]),
            "[DONE]",
        )

    response, deltas = await _stream(_client(handler))
    assert deltas == []
    assert response.tool_calls == [ToolCall(id="call_1", name=TOOL_NAME, arguments={"tema": "tren"})]


@pytest.mark.parametrize(
    ("error", "expected"),
    [({"code": "tool_use_failed", "message": "bad"}, InvalidToolCall), ({"message": "overloaded"}, LLMError)],
)
async def test_stream_error_como_evento(error, expected):
    client = _client(lambda request: _sse(_delta(content="Ho"), {"error": error}))
    with pytest.raises(expected):
        await _stream(client)


@pytest.mark.parametrize(("status", "error"), [(429, LLMUnavailable), (401, LLMUnavailable)])
async def test_stream_errores_http(status, error):
    with pytest.raises(error):
        await _stream(_client(lambda request: httpx.Response(status, text="x")))


async def test_modelo_inexistente_es_unavailable():
    body = '{"error": {"code": "model_not_found"}}'
    with pytest.raises(LLMUnavailable, match="GROQ_MODEL"):
        await _client(lambda request: httpx.Response(404, text=body)).chat([Message(role="user", content="x")], [])
