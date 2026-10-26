import asyncio
import os
from collections.abc import Callable, Sequence

import pytest
from config import ROOT_DIR
from llm.provider import LLMProvider, LLMResponse, Message, ToolSpec
from pymongo import MongoClient
from store.history import HistoryStore
from store.mongo_repository import MongoBookRepository
from store.repository import BookRepository
from tools.base import ToolError, ToolRegistry, ToolsUnavailable

from tests.fake_repository import FakeRepo

TOOL_NAME = "consultar_fundacion_las_varillas"
TOOL_SPEC = ToolSpec(
    name=TOOL_NAME,
    description="Busca en la biblioteca histórica",
    parameters={"type": "object", "properties": {"tema": {"type": "string"}}},
)


# SOLID-L (sustitución de Liskov): FakeLLM cumple LLMProvider y reemplaza a OllamaClient en tests.
# Hereda chat_stream por defecto: el agente corre igual con el doble.
# SOLID-D (inversión de dependencias): los tests inyectan estos dobles (FakeLLM y FakeTools) por constructor.
# El agente no sabe que son falsos: depende solo de las abstracciones.
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


# SOLID-L (sustitución de Liskov): FakeTools cumple ToolRegistry y reemplaza a McpToolRegistry.
class FakeTools(ToolRegistry):
    def __init__(self, results: dict[str, str] | None = None, *, unavailable: bool = False) -> None:
        self._results = results or {}
        self._unavailable = unavailable
        self.calls: list[tuple[str, dict]] = []
        self.user_questions: list[str | None] = []

    async def specs(self) -> list[ToolSpec]:
        if self._unavailable:
            raise ToolsUnavailable("fake caído")
        return [TOOL_SPEC]

    async def call(self, name: str, arguments: dict, *, user_question: str | None = None) -> str:
        self.calls.append((name, arguments))
        self.user_questions.append(user_question)
        if name not in self._results:
            raise ToolError(f"Herramienta desconocida: {name}")
        return self._results[name]


@pytest.fixture(scope="session")
def store() -> HistoryStore:
    return HistoryStore.from_file(ROOT_DIR / "fundacion.json")


@pytest.fixture
def mongo_repo() -> MongoBookRepository:
    """Repositorio real sobre una base de prueba. Se salta si MONGODB_URL_TEST no está definida.

    Solo borra bases cuyo nombre termina en _test: nunca toca la base de la aplicación.
    """
    url = os.environ.get("MONGODB_URL_TEST")
    if not url:
        pytest.skip("MONGODB_URL_TEST no definida")
    db_name = os.environ.get("MONGODB_DB_TEST", "historia_test")
    if not db_name.endswith("_test"):
        raise pytest.UsageError("MONGODB_DB_TEST tiene que terminar en _test")
    admin = MongoClient(url, serverSelectionTimeoutMS=3000)
    admin.drop_database(db_name)
    repo = MongoBookRepository.from_url(url, db_name)
    yield repo
    repo.cerrar()
    admin.drop_database(db_name)
    admin.close()


# La misma batería corre contra el fake y contra MongoBookRepository (este último solo con MONGODB_URL_TEST).
@pytest.fixture(params=["fake", pytest.param("mongo", marks=pytest.mark.mongo)])
def repo(request) -> BookRepository:
    if request.param == "fake":
        return FakeRepo()
    return request.getfixturevalue("mongo_repo")
