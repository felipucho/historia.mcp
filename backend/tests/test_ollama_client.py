import json

import httpx
import pytest

from llm.ollama import OllamaClient
from llm.provider import InvalidToolCall, LLMError, LLMTimeout, LLMUnavailable, Message, ToolCall
from tests.conftest import TOOL_NAME, TOOL_SPEC


def _client(handler) -> OllamaClient:
    return OllamaClient(
        "http://ollama.test",
        "llama3.2",
        num_ctx=8192,
        keep_alive="5m",
        connect_timeout=5,
        read_timeout=90,
        transport=httpx.MockTransport(handler),
    )


def _chat_reply(message: dict) -> httpx.Response:
    return httpx.Response(200, json={"message": {"role": "assistant", **message}, "done": True})


async def test_payload_normalizado_a_formato_ollama():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return _chat_reply({"content": "ok"})

    call = ToolCall(id="call_1", name=TOOL_NAME, arguments={"tema": "Dabbene"})
    history = [
        Message(role="system", content="sys"),
        Message(role="user", content="¿Quién es Dabbene?"),
        Message(role="assistant", tool_calls=[call]),
        Message(role="tool", content="Valter Dabbene", tool_call_id="call_1", name=TOOL_NAME),
    ]
    response = await _client(handler).chat(history, [TOOL_SPEC])

    assert response.content == "ok"
    assert captured["stream"] is False
    assert captured["options"] == {"num_ctx": 8192}
    assert captured["tools"][0] == {"type": "function", "function": TOOL_SPEC.model_dump()}
    assert captured["messages"][2]["tool_calls"] == [
        {"id": "call_1", "function": {"name": TOOL_NAME, "arguments": {"tema": "Dabbene"}}}
    ]
    assert captured["messages"][3] == {
        "role": "tool", "content": "Valter Dabbene", "tool_name": TOOL_NAME, "tool_call_id": "call_1",
    }


async def test_temperatura_configurable_viaja_en_options():
    captured = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured.update(json.loads(request.content))
        return _chat_reply({"content": "ok"})

    client = OllamaClient(
        "http://ollama.test", "llama3.2", num_ctx=4096, keep_alive="5m", connect_timeout=5, read_timeout=90,
        temperature=0.1, transport=httpx.MockTransport(handler),
    )
    await client.chat([Message(role="user", content="x")], [])
    assert captured["options"] == {"num_ctx": 4096, "temperature": 0.1}


async def test_tool_calls_nativas_reciben_id_si_ollama_no_lo_manda():
    def handler(request):
        return _chat_reply({"content": "", "tool_calls": [{"function": {"name": TOOL_NAME, "arguments": {"tema": "x"}}}]})

    response = await _client(handler).chat([Message(role="user", content="hola")], [TOOL_SPEC])

    [call] = response.tool_calls
    assert call.id.startswith("call_") and call.name == TOOL_NAME and call.arguments == {"tema": "x"}


async def test_arguments_como_string_json():
    def handler(request):
        return _chat_reply({"tool_calls": [{"id": "abc", "function": {"name": TOOL_NAME, "arguments": '{"tema": "tren"}'}}]})

    [call] = (await _client(handler).chat([Message(role="user", content="x")], [TOOL_SPEC])).tool_calls
    assert (call.id, call.arguments) == ("abc", {"tema": "tren"})


async def test_tool_call_escrita_como_json_en_content():
    def handler(request):
        return _chat_reply({"content": f'```json\n{{"name": "{TOOL_NAME}", "parameters": {{"tema": "1903"}}}}\n```'})

    response = await _client(handler).chat([Message(role="user", content="x")], [TOOL_SPEC])
    assert response.content == ""
    assert response.tool_calls[0].name == TOOL_NAME
    assert response.tool_calls[0].arguments == {"tema": "1903"}


async def test_json_con_tool_desconocida_falla_explicito():
    def handler(request):
        return _chat_reply({"content": '{"name": "borrar_todo", "parameters": {}}'})

    with pytest.raises(InvalidToolCall):
        await _client(handler).chat([Message(role="user", content="x")], [TOOL_SPEC])


async def test_texto_con_llaves_no_es_tool_call():
    content = 'La teoría {1900} dice {"name": "x"} pero no es una llamada.'

    def handler(request):
        return _chat_reply({"content": content})

    response = await _client(handler).chat([Message(role="user", content="x")], [TOOL_SPEC])
    assert (response.content, response.tool_calls) == (content, [])


@pytest.mark.parametrize(
    ("exception", "expected"),
    [
        (httpx.ConnectError("refused"), LLMUnavailable),
        (httpx.ConnectTimeout("connect"), LLMUnavailable),
        (httpx.ReadTimeout("read"), LLMTimeout),
    ],
)
async def test_errores_de_transporte_tipados(exception, expected):
    def handler(request):
        raise exception

    with pytest.raises(expected):
        await _client(handler).chat([Message(role="user", content="x")], [])


async def test_modelo_ausente_sugiere_pull():
    def handler(request):
        return httpx.Response(404, json={"error": "model 'llama3.2' not found"})

    with pytest.raises(LLMUnavailable, match="ollama pull llama3.2"):
        await _client(handler).chat([Message(role="user", content="x")], [])


async def test_error_http_generico_no_es_unavailable():
    def handler(request):
        return httpx.Response(500, text="boom")

    with pytest.raises(LLMError) as excinfo:
        await _client(handler).chat([Message(role="user", content="x")], [])
    assert not isinstance(excinfo.value, LLMUnavailable)


async def test_health_detecta_modelo_faltante():
    def handler(request):
        return httpx.Response(200, json={"models": [{"name": "llama3:latest", "model": "llama3:latest"}]})

    with pytest.raises(LLMUnavailable, match="falta el modelo"):
        await _client(handler).health()


async def test_health_acepta_tag_latest():
    def handler(request):
        return httpx.Response(200, json={"models": [{"name": "llama3.2:latest", "model": "llama3.2:latest"}]})

    await _client(handler).health()


def _ndjson(*chunks: dict) -> httpx.Response:
    return httpx.Response(200, content="\n".join(json.dumps(chunk) for chunk in chunks).encode())


async def _stream(client: OllamaClient, tools=(TOOL_SPEC,)):
    deltas: list[str] = []

    async def on_delta(text: str) -> None:
        deltas.append(text)

    response = await client.chat_stream([Message(role="user", content="x")], list(tools), on_delta)
    return response, deltas


async def test_stream_emite_cada_pedazo_y_devuelve_el_texto_completo():
    captured: dict = {}

    def handler(request: httpx.Request) -> httpx.Response:
        captured["body"] = json.loads(request.content)
        return _ndjson(
            {"message": {"role": "assistant", "content": "Llegó "}, "done": False},
            {"message": {"role": "assistant", "content": "en 1900."}, "done": False},
            {"message": {"role": "assistant", "content": ""}, "done": True},
        )

    response, deltas = await _stream(_client(handler))
    assert captured["body"]["stream"] is True
    assert deltas == ["Llegó ", "en 1900."]
    assert response.content == "Llegó en 1900." and response.tool_calls == []


async def test_stream_tool_call_nativa_no_emite_texto():
    def handler(request: httpx.Request) -> httpx.Response:
        call = {"function": {"name": TOOL_NAME, "arguments": {"tema": "tren"}}}
        return _ndjson({"message": {"content": "", "tool_calls": [call]}, "done": False}, {"message": {"content": ""}, "done": True})

    response, deltas = await _stream(_client(handler))
    assert deltas == []
    assert response.tool_calls[0].arguments == {"tema": "tren"}


async def test_stream_retiene_json_que_resulta_ser_tool_call():
    # Un 3B a veces escribe la tool call como texto: no debe aparecer en el chat.
    def handler(request: httpx.Request) -> httpx.Response:
        return _ndjson(
            {"message": {"content": '{"name": "'}},
            {"message": {"content": TOOL_NAME + '", "parameters": {"tema": "tren"}}'}},
            {"message": {"content": ""}, "done": True},
        )

    response, deltas = await _stream(_client(handler))
    assert deltas == []
    assert response.tool_calls[0].name == TOOL_NAME


async def test_stream_json_que_no_es_tool_call_se_emite_al_final():
    def handler(request: httpx.Request) -> httpx.Response:
        return _ndjson({"message": {"content": "{no es "}}, {"message": {"content": "json}"}}, {"done": True})

    response, deltas = await _stream(_client(handler))
    assert deltas == ["{no es json}"]
    assert response.content == "{no es json}"


async def test_stream_error_a_mitad_es_llm_error():
    def handler(request: httpx.Request) -> httpx.Response:
        return _ndjson({"message": {"content": "Hola"}}, {"error": "model runner crashed"})

    with pytest.raises(LLMError, match="cortó"):
        await _stream(_client(handler))


async def test_stream_modelo_ausente_sugiere_pull():
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(404, json={"error": "model not found"})

    with pytest.raises(LLMUnavailable, match="ollama pull"):
        await _stream(_client(handler))
