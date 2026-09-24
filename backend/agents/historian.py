"""HistorianAgent: loop de razonamiento con tools. No sabe de transporte (WS/HTTP) ni de proveedor concreto."""

import logging
from collections import deque
from collections.abc import Awaitable, Callable, Mapping
from itertools import chain
from typing import Literal

from llm.provider import DeltaCallback, LLMProvider, Message
from tools.registry import ToolError, ToolRegistry

logger = logging.getLogger(__name__)

AgentState = Literal["thinking", "tool_call"]
# detail: el primer argumento de texto de la tool (ej: el tema buscado), para mostrarlo en la UI.
StatusCallback = Callable[..., Awaitable[None]]
ToolResultCallback = Callable[[str], None]

EMPTY_ANSWER = "No pude generar una respuesta. Probá reformular la pregunta."
DEFAULT_PROVIDER = "local"
_MAX_DETAIL_CHARS = 200


class MaxIterationsExceeded(Exception):
    """El modelo siguió pidiendo tools sin llegar a una respuesta final."""


class UnknownProvider(Exception):
    """Se pidió un proveedor de LLM que no está configurado."""


def _detail(arguments: dict) -> str | None:
    text = next((value for value in arguments.values() if isinstance(value, str) and value.strip()), None)
    return text.strip()[:_MAX_DETAIL_CHARS] if text else None


class Conversation:
    """Historial de UNA conexión: system prompt fijo + ventana de los últimos N turnos.

    Se guarda cada turno como (pregunta, respuesta final). Los resultados de tools no se
    conservan: son la mayor parte de los tokens y el modelo los vuelve a pedir si los necesita.
    Así el system prompt nunca queda fuera de num_ctx y no quedan mensajes tool huérfanos.
    """

    def __init__(self, system_prompt: str, max_turns: int) -> None:
        self._system = Message(role="system", content=system_prompt)
        self._turns: deque[tuple[Message, Message]] = deque(maxlen=max_turns)

    def with_pending(self, pending: list[Message]) -> list[Message]:
        return [self._system, *chain.from_iterable(self._turns), *pending]

    def commit(self, question: Message, answer: Message) -> None:
        self._turns.append((question, answer))

    def __len__(self) -> int:
        return len(self._turns)


class HistorianAgent:
    """El historial es por conversación, no por proveedor: se puede cambiar de modelo a mitad de charla."""

    def __init__(
        self,
        llm: LLMProvider | Mapping[str, LLMProvider],
        tools: ToolRegistry,
        system_prompt: str,
        *,
        max_iterations: int = 5,
        max_turns: int = 6,
    ) -> None:
        self._llms = dict(llm) if isinstance(llm, Mapping) else {DEFAULT_PROVIDER: llm}
        self._tools = tools
        self._system_prompt = system_prompt
        self._max_iterations = max_iterations
        self._max_turns = max_turns

    @property
    def providers(self) -> tuple[str, ...]:
        return tuple(self._llms)

    def new_conversation(self) -> Conversation:
        return Conversation(self._system_prompt, self._max_turns)

    async def run(
        self,
        conversation: Conversation,
        text: str,
        on_status: StatusCallback,
        *,
        provider: str = DEFAULT_PROVIDER,
        on_tool_result: ToolResultCallback | None = None,
        on_delta: DeltaCallback | None = None,
    ) -> str:
        """Devuelve la respuesta final. Con on_delta el texto además se emite mientras se genera.

        Lo que se emitió antes de una tool call (preámbulo del modelo) queda descartado: el cliente
        lo borra al recibir el estado tool_call, y la respuesta final es lo que devuelve este método.
        """
        if (llm := self._llms.get(provider)) is None:
            raise UnknownProvider(f"Proveedor no configurado: {provider}")
        # Sin tools no se consulta al modelo: un 3B sin datos inventa historia.
        specs = await self._tools.specs()
        question = Message(role="user", content=text)
        pending = [question]
        for iteration in range(1, self._max_iterations + 1):
            await on_status("thinking", None)
            messages = conversation.with_pending(pending)
            response = await (llm.chat(messages, specs) if on_delta is None else llm.chat_stream(messages, specs, on_delta))
            if not response.tool_calls:
                answer = response.content.strip()
                if not answer:
                    logger.warning("empty_answer", extra={"iteration": iteration})
                    return EMPTY_ANSWER
                conversation.commit(question, Message(role="assistant", content=answer))
                logger.info("agent_answer", extra={"iteration": iteration, "chars": len(answer), "provider": provider})
                return answer
            pending.append(Message(role="assistant", content=response.content, tool_calls=response.tool_calls))
            for call in response.tool_calls:
                await on_status("tool_call", call.name, detail=_detail(call.arguments))
                logger.info("tool_call", extra={"iteration": iteration, "tool": call.name, "arguments": call.arguments})
                try:
                    result = await self._tools.call(call.name, call.arguments, user_question=text)
                except ToolError as exc:
                    logger.warning("tool_error", extra={"tool": call.name, "error": str(exc)})
                    result = f"ERROR de herramienta: {exc}"
                else:
                    if on_tool_result is not None:
                        on_tool_result(result)
                pending.append(Message(role="tool", content=result, tool_call_id=call.id, name=call.name))
        logger.warning("max_iterations", extra={"max_iterations": self._max_iterations})
        raise MaxIterationsExceeded(f"Sin respuesta final tras {self._max_iterations} iteraciones")
