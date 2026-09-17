import asyncio
from collections.abc import Callable, Sequence

import pytest

from config import ROOT_DIR
from llm.provider import LLMProvider, LLMResponse, Message, ToolSpec
from store.history import HistoryStore
from tools.registry import ToolRegistry, ToolsUnavailable

TOOL_NAME = "consultar_fundacion_las_varillas"
TOOL_SPEC = ToolSpec(
    name=TOOL_NAME,
    description="Busca en la biblioteca histórica",
    parameters={"type": "object", "properties": {"tema": {"type": "string"}}},
)


class FakeLLM(LLMProvider):
    """Respuestas guionadas (lista) o calculadas (callable). Registra los mensajes de cada llamada."""

    def __init__(
        self,
        script: Sequence[LLMResponse | Exception] | Callable[[list[Message]], LLMResponse],
        delay: float = 0.0,
    ) -> None:
        self._script = script if callable(script) else list(script)
        self._delay = delay
        self.calls: list[list[Message]] = []

    async def chat(self, messages: Sequence[Message], tools: Sequence[ToolSpec]) -> LLMResponse:
        self.calls.append(list(messages))
        if self._delay:
            await asyncio.sleep(self._delay)
        if callable(self._script):
            return self._script(list(messages))
        item = self._script.pop(0)
        if isinstance(item, Exception):
            raise item
        return item

    async def health(self) -> None:
        return None


class FakeTools(ToolRegistry):
    def __init__(self, results: dict[str, str] | None = None, *, unavailable: bool = False) -> None:
        self._results = results or {}
        self._unavailable = unavailable
        self.calls: list[tuple[str, dict]] = []

    async def specs(self) -> list[ToolSpec]:
        if self._unavailable:
            raise ToolsUnavailable("fake caído")
        return [TOOL_SPEC]

    async def call(self, name: str, arguments: dict) -> str:
        self.calls.append((name, arguments))
        return self._results[name]


@pytest.fixture(scope="session")
def store() -> HistoryStore:
    return HistoryStore.from_file(ROOT_DIR / "fundacion.json")
