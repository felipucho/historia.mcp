"""HistorianAgent: loop de razonamiento con tools. No sabe de transporte (WS/HTTP) ni de proveedor concreto."""

import logging
from collections import deque
from collections.abc import Awaitable, Callable
from itertools import chain
from typing import Literal

from llm.provider import LLMProvider, Message
from tools.registry import ToolError, ToolRegistry

logger = logging.getLogger(__name__)

AgentState = Literal["thinking", "tool_call"]
StatusCallback = Callable[[AgentState, str | None], Awaitable[None]]

EMPTY_ANSWER = "No pude generar una respuesta. Probá reformular la pregunta."


class MaxIterationsExceeded(Exception):
    """El modelo siguió pidiendo tools sin llegar a una respuesta final."""


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
    def __init__(
        self,
        llm: LLMProvider,
        tools: ToolRegistry,
        system_prompt: str,
        *,
        max_iterations: int = 5,
        max_turns: int = 6,
    ) -> None:
        self._llm = llm
        self._tools = tools
        self._system_prompt = system_prompt
        self._max_iterations = max_iterations
        self._max_turns = max_turns

    def new_conversation(self) -> Conversation:
        return Conversation(self._system_prompt, self._max_turns)

    async def run(self, conversation: Conversation, text: str, on_status: StatusCallback) -> str:
        # Sin tools no se consulta al modelo: un 3B sin datos inventa historia.
        specs = await self._tools.specs()
        question = Message(role="user", content=text)
        pending = [question]
        for iteration in range(1, self._max_iterations + 1):
            await on_status("thinking", None)
            response = await self._llm.chat(conversation.with_pending(pending), specs)
            if not response.tool_calls:
                answer = response.content.strip()
                if not answer:
                    logger.warning("empty_answer", extra={"iteration": iteration})
                    return EMPTY_ANSWER
                conversation.commit(question, Message(role="assistant", content=answer))
                logger.info("agent_answer", extra={"iteration": iteration, "chars": len(answer)})
                return answer
            pending.append(Message(role="assistant", content=response.content, tool_calls=response.tool_calls))
            for call in response.tool_calls:
                await on_status("tool_call", call.name)
                logger.info("tool_call", extra={"iteration": iteration, "tool": call.name, "arguments": call.arguments})
                try:
                    result = await self._tools.call(call.name, call.arguments)
                except ToolError as exc:
                    logger.warning("tool_error", extra={"tool": call.name, "error": str(exc)})
                    result = f"ERROR de herramienta: {exc}"
                pending.append(Message(role="tool", content=result, tool_call_id=call.id, name=call.name))
        logger.warning("max_iterations", extra={"max_iterations": self._max_iterations})
        raise MaxIterationsExceeded(f"Sin respuesta final tras {self._max_iterations} iteraciones")
