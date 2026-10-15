"""Traducción de tool calls desde el formato de cable. Ollama y OpenAI-compatible devuelven la misma forma."""

import json
from typing import Any

from llm.provider import InvalidToolCall, ToolCall, new_tool_call_id


def tool_call_from_wire(raw: Any) -> ToolCall:
    """Valida un tool call del proveedor: exige function.name y arguments como objeto o como string JSON."""
    function = raw.get("function") if isinstance(raw, dict) else None
    if not isinstance(function, dict) or not isinstance(function.get("name"), str) or not function["name"]:
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
