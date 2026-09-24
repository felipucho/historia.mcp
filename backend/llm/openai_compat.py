"""OpenAICompatClient: HTTP async contra /chat/completions (Groq, Cerebras, OpenRouter). No sabe de MCP ni de WebSocket.

La key vive en .env y solo la usa el backend: el navegador nunca la ve.
"""

import json
import logging
from collections.abc import Iterator, Sequence
from contextlib import contextmanager
from typing import Any

import httpx

from llm.provider import (
    DeltaCallback,
    InvalidToolCall,
    LLMError,
    LLMProvider,
    LLMResponse,
    LLMTimeout,
    LLMUnavailable,
    Message,
    ToolCall,
    ToolSpec,
    new_tool_call_id,
)

logger = logging.getLogger(__name__)


class OpenAICompatClient(LLMProvider):
    def __init__(
        self,
        base_url: str,
        model: str,
        api_key: str,
        *,
        temperature: float,
        connect_timeout: float,
        read_timeout: float,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._model = model
        self._api_key = api_key
        self._temperature = temperature
        self._read_timeout = read_timeout
        timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=10.0, pool=5.0)
        headers = {"Authorization": f"Bearer {api_key}"} if api_key else {}
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, headers=headers, transport=transport)

    async def chat(self, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> LLMResponse:
        self._require_key()
        data = await self._request(self._payload(messages, tools, stream=False))
        choices = data.get("choices")
        message = choices[0].get("message") if isinstance(choices, list) and choices and isinstance(choices[0], dict) else None
        if not isinstance(message, dict):
            raise LLMError("Respuesta del modelo en la nube sin 'choices[0].message'")
        raw_calls = message.get("tool_calls") or []
        return LLMResponse(content=message.get("content") or "", tool_calls=[self._from_wire(raw) for raw in raw_calls])

    async def chat_stream(self, messages: Sequence[Message], tools: Sequence[ToolSpec], on_delta: DeltaCallback) -> LLMResponse:
        """SSE: cada 'data:' trae un delta. Las tool calls llegan en fragmentos por 'index' y se arman al final."""
        self._require_key()
        parts: list[str] = []
        calls: dict[int, dict[str, Any]] = {}
        with self._errors():
            async with self._client.stream("POST", "/chat/completions", json=self._payload(messages, tools, stream=True)) as response:
                if response.is_error:
                    await response.aread()
                    self._raise_for_status(response)
                async for line in response.aiter_lines():
                    if not line.startswith("data:"):
                        continue
                    data = line.removeprefix("data:").strip()
                    if data == "[DONE]":
                        break
                    delta = self._parse_event(data)
                    if text := delta.get("content"):
                        parts.append(text)
                        await on_delta(text)
                    for raw in delta.get("tool_calls") or []:
                        self._merge_call_fragment(calls, raw)
        return LLMResponse(content="".join(parts), tool_calls=[self._from_wire(calls[index]) for index in sorted(calls)])

    async def health(self) -> None:
        # Sin request de red: el free tier cuenta cada llamada. La key se valida en el primer mensaje.
        self._require_key()

    async def aclose(self) -> None:
        await self._client.aclose()

    def _require_key(self) -> None:
        if not self._api_key:
            raise LLMUnavailable("Falta la API key del modelo en la nube (GROQ_API_KEY en .env)")

    def _payload(self, messages: Sequence[Message], tools: Sequence[ToolSpec], *, stream: bool) -> dict[str, Any]:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [self._to_wire(message) for message in messages],
            "temperature": self._temperature,
        }
        if stream:
            payload["stream"] = True
        if tools:
            payload["tools"] = [{"type": "function", "function": spec.model_dump()} for spec in tools]
            payload["tool_choice"] = "auto"
        return payload

    async def _request(self, payload: dict[str, Any]) -> dict[str, Any]:
        with self._errors():
            response = await self._client.post("/chat/completions", json=payload)
        self._raise_for_status(response)
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError("El modelo en la nube devolvió un cuerpo que no es JSON") from exc
        if not isinstance(data, dict):
            raise LLMError("El modelo en la nube devolvió JSON inesperado")
        return data

    @contextmanager
    def _errors(self) -> Iterator[None]:
        """Traduce errores de httpx a los del contrato. En stream cubre también la lectura de cada evento."""
        try:
            yield
        except httpx.TimeoutException as exc:
            raise LLMTimeout(f"El modelo en la nube no respondió en {self._read_timeout:.0f}s") from exc
        except httpx.TransportError as exc:
            raise LLMUnavailable(f"No se pudo conectar a {self._base_url}") from exc

    @staticmethod
    def _raise_for_status(response: httpx.Response) -> None:
        if response.status_code in (401, 403):
            raise LLMUnavailable("API key del modelo en la nube inválida o revocada")
        if response.status_code == 429:
            raise LLMUnavailable("Se agotó el límite gratuito del modelo en la nube")
        if response.status_code == 400 and "tool_use_failed" in response.text:
            # Groq valida la tool call del modelo y devuelve 400 si está mal formada.
            raise InvalidToolCall(f"El modelo generó una llamada a herramienta inválida: {response.text[:300]}")
        if response.status_code == 404 and "model_not_found" in response.text:
            raise LLMUnavailable("El modelo configurado en GROQ_MODEL no existe en Groq")
        if response.is_error:
            raise LLMError(f"El modelo en la nube respondió {response.status_code}: {response.text[:300]}")

    @staticmethod
    def _parse_event(data: str) -> dict[str, Any]:
        """Devuelve choices[0].delta de un evento SSE ({} si no trae choices)."""
        try:
            event = json.loads(data)
        except json.JSONDecodeError as exc:
            raise LLMError(f"Evento SSE que no es JSON: {data[:200]}") from exc
        if not isinstance(event, dict):
            raise LLMError("Evento SSE con JSON inesperado")
        if error := event.get("error"):
            # Groq manda errores a mitad del stream como evento, con el status HTTP ya en 200.
            if "tool_use_failed" in str(error):
                raise InvalidToolCall(f"El modelo generó una llamada a herramienta inválida: {str(error)[:300]}")
            raise LLMError(f"El modelo en la nube cortó el stream: {str(error)[:300]}")
        choices = event.get("choices")
        if not (isinstance(choices, list) and choices and isinstance(choices[0], dict)):
            return {}
        delta = choices[0].get("delta")
        return delta if isinstance(delta, dict) else {}

    @staticmethod
    def _merge_call_fragment(calls: dict[int, dict[str, Any]], raw: Any) -> None:
        if not isinstance(raw, dict):
            raise InvalidToolCall(f"fragmento de tool_call inválido: {raw!r:.200}")
        slot = calls.setdefault(raw.get("index", 0), {"id": None, "function": {"name": "", "arguments": ""}})
        if raw.get("id"):
            slot["id"] = raw["id"]
        function = raw.get("function") or {}
        slot["function"]["name"] += function.get("name") or ""
        slot["function"]["arguments"] += function.get("arguments") or ""

    @staticmethod
    def _to_wire(message: Message) -> dict[str, Any]:
        wire: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            # En el formato OpenAI los arguments viajan como string JSON, no como objeto.
            wire["tool_calls"] = [
                {"id": call.id, "type": "function", "function": {"name": call.name, "arguments": json.dumps(call.arguments, ensure_ascii=False)}}
                for call in message.tool_calls
            ]
        if message.role == "tool":
            wire["tool_call_id"] = message.tool_call_id
        return wire

    @staticmethod
    def _from_wire(raw: Any) -> ToolCall:
        function = raw.get("function") if isinstance(raw, dict) else None
        if not isinstance(function, dict) or not isinstance(function.get("name"), str) or not function["name"]:
            raise InvalidToolCall(f"tool_call sin function.name: {raw!r:.200}")
        arguments = function.get("arguments") or "{}"
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise InvalidToolCall(f"arguments no es JSON en {function['name']}") from exc
        if not isinstance(arguments, dict):
            raise InvalidToolCall(f"arguments no es un objeto en {function['name']}")
        return ToolCall(id=raw.get("id") or new_tool_call_id(), name=function["name"], arguments=arguments)
