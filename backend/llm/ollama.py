"""OllamaClient: HTTP async contra /api/chat. No sabe de MCP ni de WebSocket."""

import json
import logging
from collections.abc import Sequence
from typing import Any

import httpx

from llm.provider import (
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

_HEALTH_TIMEOUT = httpx.Timeout(5.0)
_TEXT_TOOL_CALL_KEYS = {"type", "name", "parameters", "arguments"}


class OllamaClient(LLMProvider):
    def __init__(
        self,
        base_url: str,
        model: str,
        *,
        num_ctx: int,
        keep_alive: str,
        connect_timeout: float,
        read_timeout: float,
        temperature: float | None = None,
        transport: httpx.AsyncBaseTransport | None = None,
    ) -> None:
        self._base_url = base_url
        self._model = model
        self._options: dict[str, Any] = {"num_ctx": num_ctx}
        if temperature is not None:
            self._options["temperature"] = temperature
        self._keep_alive = keep_alive
        self._read_timeout = read_timeout
        # connect corto: Ollama caído se detecta en segundos. read largo: generación en CPU.
        timeout = httpx.Timeout(connect=connect_timeout, read=read_timeout, write=10.0, pool=5.0)
        self._client = httpx.AsyncClient(base_url=base_url, timeout=timeout, transport=transport)

    async def chat(self, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> LLMResponse:
        payload: dict[str, Any] = {
            "model": self._model,
            "messages": [self._to_wire(message) for message in messages],
            "stream": False,
            "keep_alive": self._keep_alive,
            "options": self._options,
        }
        if tools:
            payload["tools"] = [{"type": "function", "function": spec.model_dump()} for spec in tools]
        data = await self._request("POST", "/api/chat", json=payload)
        message = data.get("message")
        if not isinstance(message, dict):
            raise LLMError("Respuesta de Ollama sin 'message'")
        content = message.get("content") or ""
        raw_calls = message.get("tool_calls") or []
        if raw_calls:
            return LLMResponse(content=content, tool_calls=[self._from_wire(raw) for raw in raw_calls])
        text_call = self._parse_text_tool_call(content, {spec.name for spec in tools})
        if text_call:
            return LLMResponse(tool_calls=[text_call])
        return LLMResponse(content=content)

    async def health(self) -> None:
        data = await self._request("GET", "/api/tags", timeout=_HEALTH_TIMEOUT)
        available = {name for model in data.get("models", []) for name in (model.get("name"), model.get("model"))}
        if self._model not in available and f"{self._model}:latest" not in available:
            raise LLMUnavailable(f"Ollama responde pero falta el modelo '{self._model}'. Ejecutá: ollama pull {self._model}")

    async def warm_up(self) -> None:
        # /api/generate sin prompt solo carga el modelo en memoria.
        await self._request("POST", "/api/generate", json={"model": self._model, "keep_alive": self._keep_alive})
        logger.info("ollama_model_loaded", extra={"model": self._model})

    async def aclose(self) -> None:
        await self._client.aclose()

    async def _request(self, method: str, path: str, **kwargs: Any) -> dict[str, Any]:
        try:
            response = await self._client.request(method, path, **kwargs)
        except httpx.ConnectTimeout as exc:
            raise LLMUnavailable(f"Ollama no acepta conexiones en {self._base_url}") from exc
        except httpx.TimeoutException as exc:
            raise LLMTimeout(f"Ollama no respondió en {self._read_timeout:.0f}s") from exc
        except httpx.TransportError as exc:
            raise LLMUnavailable(f"No se pudo conectar a Ollama en {self._base_url}. ¿Está corriendo 'ollama serve'?") from exc
        if response.status_code == 404:
            raise LLMUnavailable(f"Modelo '{self._model}' no disponible en Ollama. Ejecutá: ollama pull {self._model}")
        if response.is_error:
            raise LLMError(f"Ollama respondió {response.status_code}: {response.text[:300]}")
        try:
            data = response.json()
        except ValueError as exc:
            raise LLMError("Ollama devolvió un cuerpo que no es JSON") from exc
        if not isinstance(data, dict):
            raise LLMError("Ollama devolvió JSON inesperado")
        return data

    @staticmethod
    def _to_wire(message: Message) -> dict[str, Any]:
        wire: dict[str, Any] = {"role": message.role, "content": message.content}
        if message.tool_calls:
            wire["tool_calls"] = [
                {"id": call.id, "function": {"name": call.name, "arguments": call.arguments}}
                for call in message.tool_calls
            ]
        if message.role == "tool":
            # Ollama correlaciona por tool_name; tool_call_id se envía para versiones que lo soportan.
            wire["tool_name"] = message.name
            wire["tool_call_id"] = message.tool_call_id
        return wire

    @staticmethod
    def _from_wire(raw: Any) -> ToolCall:
        function = raw.get("function") if isinstance(raw, dict) else None
        if not isinstance(function, dict) or not isinstance(function.get("name"), str):
            raise InvalidToolCall(f"tool_call sin function.name: {raw!r:.200}")
        arguments = function.get("arguments") or {}
        if isinstance(arguments, str):
            try:
                arguments = json.loads(arguments)
            except json.JSONDecodeError as exc:
                raise InvalidToolCall(f"arguments no es JSON en {function['name']}") from exc
        if not isinstance(arguments, dict):
            raise InvalidToolCall(f"arguments no es un objeto en {function['name']}")
        return ToolCall(id=raw.get("id") or new_tool_call_id(), name=function["name"], arguments=arguments)

    @staticmethod
    def _parse_text_tool_call(content: str, tool_names: set[str]) -> ToolCall | None:
        """Modelos chicos a veces escriben la tool call como JSON en el content.

        Solo se acepta si el content ENTERO es un objeto JSON con 'name'. Sin regex: texto normal
        con llaves no se confunde con una llamada. Un objeto con 'name' pero inválido falla explícito.
        """
        text = content.strip()
        if text.startswith("```") and text.endswith("```"):
            text = text.strip("`").removeprefix("json").strip()
        if not (text.startswith("{") and text.endswith("}")):
            return None
        try:
            data = json.loads(text)
        except json.JSONDecodeError:
            return None
        if not isinstance(data, dict) or "name" not in data:
            return None
        name = data["name"]
        arguments = data.get("parameters", data.get("arguments", {}))
        if not set(data) <= _TEXT_TOOL_CALL_KEYS or name not in tool_names or not isinstance(arguments, dict):
            logger.warning("text_tool_call_rejected", extra={"content": text[:300]})
            raise InvalidToolCall(f"Llamada a herramienta inválida en texto: {text[:200]}")
        logger.info("text_tool_call_parsed", extra={"tool": name})
        return ToolCall(name=name, arguments=arguments)
