"""Carga, valida y consulta fundacion.json. Sin conocimiento de MCP, LLM ni HTTP."""

import codecs
import re
import unicodedata
from collections.abc import Iterable, Sequence
from dataclasses import dataclass
from pathlib import Path

from pydantic import BaseModel, Field, TypeAdapter, ValidationError


class Metadata(BaseModel):
    criterio_historiografico: str
    fecha_clave: str
    fuente: str


class Documento(BaseModel):
    # El id se usa como ancla DOM en el frontend: restringido a caracteres seguros.
    id: str = Field(pattern=r"^[A-Za-z0-9][A-Za-z0-9_-]*$", max_length=64)
    titulo: str = Field(min_length=1)
    contenido: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    metadata: Metadata


class HistoryStoreError(RuntimeError):
    """fundacion.json ausente, corrupto o con schema inválido."""


_CORPUS = TypeAdapter(list[Documento])

# Sin acentos: se comparan contra texto ya normalizado.
STOPWORDS = frozenset(
    """
    a al algo ante antes cada como con contame cual cuales cuando cuanto de decime del desde
    dime donde e el ella ellas ellos en entre era es esa ese eso esta este esto fue fueron ha
    habia hablame hay la las le les lo los mas me mi muy nada ni no nos o para pero por porque
    que quien quienes se segun ser si sin sobre son su sus te tiene tu un una unas uno unos y ya yo
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_FIELD_WEIGHTS = {"tags": 3, "titulo": 2, "contenido": 1}


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def tokenize(text: str) -> list[str]:
    return [token for token in _TOKEN_RE.findall(normalize(text)) if token not in STOPWORDS]


@dataclass(frozen=True, slots=True)
class _IndexedDoc:
    doc: Documento
    fields: dict[str, frozenset[str]]


class HistoryStore:
    def __init__(self, documents: Sequence[Documento]) -> None:
        if not documents:
            raise HistoryStoreError("El corpus histórico está vacío")
        ids = [doc.id for doc in documents]
        if duplicates := sorted({doc_id for doc_id in ids if ids.count(doc_id) > 1}):
            raise HistoryStoreError(f"IDs duplicados en el corpus: {', '.join(duplicates)}")
        self._documents = tuple(documents)
        self._indexed = tuple(
            _IndexedDoc(
                doc=doc,
                fields={
                    "tags": frozenset(tokenize(" ".join(doc.tags))),
                    "titulo": frozenset(tokenize(doc.titulo)),
                    "contenido": frozenset(tokenize(doc.contenido)),
                },
            )
            for doc in self._documents
        )
        self._full_text = "\n\n".join(f"## {doc.titulo}\n{doc.contenido}" for doc in self._documents)

    @classmethod
    def from_file(cls, path: Path) -> "HistoryStore":
        try:
            raw = path.read_bytes()
        except FileNotFoundError as exc:
            raise HistoryStoreError(f"No existe el archivo de datos: {path}") from exc
        except OSError as exc:
            raise HistoryStoreError(f"No se pudo leer {path}: {exc}") from exc
        try:
            documents = _CORPUS.validate_json(raw.removeprefix(codecs.BOM_UTF8))
        except ValidationError as exc:
            raise HistoryStoreError(f"{path.name} inválido ({exc.error_count()} errores): {exc}") from exc
        return cls(documents)

    @property
    def documents(self) -> tuple[Documento, ...]:
        return self._documents

    @property
    def full_text(self) -> str:
        return self._full_text

    def get(self, doc_id: str) -> Documento | None:
        return next((doc for doc in self._documents if doc.id == doc_id), None)

    def search(self, tema: str, limit: int = 3) -> list[Documento]:
        """Ranking por tokens enteros, sin stopwords, sin acentos. Match exacto de id gana."""
        if exact := self.get(tema.strip()):
            return [exact]
        terms = set(tokenize(tema))
        if not terms:
            return []
        scored = []
        for position, item in enumerate(self._indexed):
            score = sum(weight * len(terms & item.fields[field]) for field, weight in _FIELD_WEIGHTS.items())
            if score:
                scored.append((-score, position, item.doc))
        return [doc for _, _, doc in sorted(scored)[:limit]]


def render_index(documents: Iterable[Documento]) -> str:
    return "\n".join(
        f"- ID: {doc.id} | {doc.titulo} | Fecha clave: {doc.metadata.fecha_clave} | Tags: {', '.join(doc.tags)}"
        for doc in documents
    )


def render_documents(documents: Iterable[Documento]) -> str:
    return "\n\n---\n\n".join(
        f"[{doc.id}] {doc.titulo}\n"
        f"{doc.contenido}\n"
        f"Criterio: {doc.metadata.criterio_historiografico} | "
        f"Fecha clave: {doc.metadata.fecha_clave} | Fuente: {doc.metadata.fuente}"
        for doc in documents
    )
