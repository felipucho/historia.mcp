"""Contrato LLM. El agente solo ve estos tipos; cada proveedor traduce a su formato de cable."""

import uuid
from abc import ABC, abstractmethod
from collections.abc import Awaitable, Callable, Sequence
from typing import Any, Literal, Self

from pydantic import BaseModel, Field, model_validator


# Recibe cada pedazo de texto de la respuesta a medida que el modelo lo genera.
DeltaCallback = Callable[[str], Awaitable[None]]


def new_tool_call_id() -> str:
    return f"call_{uuid.uuid4().hex[:16]}"


class ToolCall(BaseModel):
    id: str = Field(default_factory=new_tool_call_id)
    name: str = Field(min_length=1)
    arguments: dict[str, Any] = Field(default_factory=dict)


class Message(BaseModel):
    role: Literal["system", "user", "assistant", "tool"]
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)
    tool_call_id: str | None = None
    name: str | None = None

    @model_validator(mode="after")
    def _tool_messages_are_correlated(self) -> Self:
        if self.role == "tool" and not (self.tool_call_id and self.name):
            raise ValueError("un mensaje role=tool requiere tool_call_id y name")
        return self


class ToolSpec(BaseModel):
    name: str
    description: str = ""
    parameters: dict[str, Any]


class LLMResponse(BaseModel):
    content: str = ""
    tool_calls: list[ToolCall] = Field(default_factory=list)


class LLMError(Exception):
    """Error del proveedor. El mensaje se loguea; no se muestra crudo al usuario."""


class LLMUnavailable(LLMError):
    """Proveedor inalcanzable o modelo ausente. El mensaje es apto para el usuario."""


class LLMTimeout(LLMError):
    """El proveedor no respondió dentro del timeout de lectura."""


class InvalidToolCall(LLMError):
    """El modelo intentó llamar una herramienta con un formato o nombre inválido."""


class LLMProvider(ABC):
    @abstractmethod
    async def chat(self, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> LLMResponse: ...

    async def chat_stream(self, messages: Sequence[Message], tools: Sequence[ToolSpec], on_delta: DeltaCallback) -> LLMResponse:
        """Igual que chat, pero emite el texto por on_delta mientras se genera. Devuelve la respuesta completa.

        Por defecto no hay stream real: emite el texto entero al final. Solo se emite texto de respuestas
        sin tool calls, salvo que el proveedor ya lo haya mandado antes de saber que venía una tool call.
        """
        response = await self.chat(messages, tools)
        if response.content and not response.tool_calls:
            await on_delta(response.content)
        return response

    @abstractmethod
    async def health(self) -> None:
        """Lanza LLMUnavailable si el proveedor no puede atender pedidos."""

    async def warm_up(self) -> None:
        """Opcional: precarga el modelo."""

    async def aclose(self) -> None:
        """Opcional: libera conexiones."""
