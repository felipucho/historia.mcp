"""Carga, valida y consulta fundacion.json. Sin conocimiento de MCP, LLM ni HTTP."""

import codecs
import functools
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

# Palabras sobre la consulta misma o el tema general del corpus. Si no están en los documentos no cuentan
# como término faltante: avisar "no hay registros de «historia»" rompía la pregunta más común.
_GENERIC_TERMS = frozenset(
    """
    acerca ayudame ayudar buen buenas buenos ciudad conoce conocer conoces conta contar contas conto cosa
    cosas dato datos deci decir decis dia dias documento documentos explica explicame explicar fuente fuentes
    general gracias historia historias historica historicas historico historicos hola info informacion noches
    ocurrio origen origenes pasado paso podes podrias puede puedes queria quiero quisiera respecto resumen
    sabe saber sabes sabias sucedio tardes tema temas
    """.split()
)

_TOKEN_RE = re.compile(r"[a-z0-9]+")
_NAME_RE = re.compile(r"\b[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+(?:\s+[A-ZÁÉÍÓÚÑ][a-záéíóúñü]+)+")
_MAX_NAME_WORDS = 3
_FIELD_WEIGHTS = {"tags": 3, "titulo": 2, "contenido": 1}


def normalize(text: str) -> str:
    decomposed = unicodedata.normalize("NFKD", text.casefold())
    return "".join(char for char in decomposed if not unicodedata.combining(char))


def tokenize(text: str) -> list[str]:
    return [token for token in _TOKEN_RE.findall(normalize(text)) if token not in STOPWORDS]


def _within_one_edit(a: str, b: str) -> bool:
    """Distancia de Levenshtein <= 1 sin armar la matriz completa."""
    if abs(len(a) - len(b)) > 1:
        return False
    if len(a) > len(b):
        a, b = b, a
    i = j = edits = 0
    while i < len(a) and j < len(b):
        if a[i] != b[j]:
            edits += 1
            if edits > 1:
                return False
            if len(a) == len(b):
                i += 1
        else:
            i += 1
        j += 1
    return edits + (len(b) - j) <= 1


@dataclass(frozen=True, slots=True)
class _IndexedDoc:
    doc: Documento
    fields: dict[str, frozenset[str]]
    tokens: frozenset[str]

    @classmethod
    def build(cls, doc: Documento) -> "_IndexedDoc":
        fields = {
            "tags": frozenset(tokenize(" ".join(doc.tags))),
            "titulo": frozenset(tokenize(doc.titulo)),
            "contenido": frozenset(tokenize(doc.contenido)),
        }
        return cls(doc=doc, fields=fields, tokens=frozenset().union(*fields.values()))


@dataclass(frozen=True, slots=True)
class SearchResult:
    documents: list[Documento]
    # Términos de la consulta que no aparecen en ningún documento (ej: un nombre de pila que no existe).
    unmatched_terms: list[str]


class HistoryStore:
    def __init__(self, documents: Sequence[Documento]) -> None:
        if not documents:
            raise HistoryStoreError("El corpus histórico está vacío")
        ids = [doc.id for doc in documents]
        if duplicates := sorted({doc_id for doc_id in ids if ids.count(doc_id) > 1}):
            raise HistoryStoreError(f"IDs duplicados en el corpus: {', '.join(duplicates)}")
        self._documents = tuple(documents)
        self._indexed = tuple(_IndexedDoc.build(doc) for doc in self._documents)
        self._vocabulary = frozenset().union(*(item.tokens for item in self._indexed))
        # El typo scan recorre todo el vocabulario; unknown_names lo llama por cada palabra con mayúscula.
        self._resolve = functools.lru_cache(maxsize=4096)(self._resolve_uncached)
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

    def search(self, tema: str, limit: int = 3) -> SearchResult:
        """Ranking por tokens enteros, sin stopwords ni acentos, tolerante a un typo. Match exacto de id gana.

        Un término presente en TODOS los documentos (ej: 'varillas') no discrimina: solo puntúa cuando la
        consulta no tiene términos específicos ('historia de Las Varillas' es una pregunta general y devuelve
        el corpus). Sin ninguna coincidencia no hay resultados.
        """
        if exact := self.get(tema.strip()):
            return SearchResult([exact], [])
        resolved = {term: self._resolve(term) for term in dict.fromkeys(tokenize(tema))}
        unmatched = [term for term, variants in resolved.items() if not variants and term not in _GENERIC_TERMS]
        doc_freq = {term: sum(bool(variants & item.tokens) for item in self._indexed) for term, variants in resolved.items()}
        specific = {term: resolved[term] for term, freq in doc_freq.items() if 0 < freq < len(self._indexed)}
        scoring = specific or {term: variants for term, variants in resolved.items() if variants}

        scored = []
        for position, item in enumerate(self._indexed):
            score = sum(
                weight * sum(bool(variants & item.fields[field]) for variants in scoring.values())
                for field, weight in _FIELD_WEIGHTS.items()
            )
            if score:
                scored.append((-score, position, item.doc))
        return SearchResult([doc for _, _, doc in sorted(scored)[:limit]], unmatched)

    def unknown_names(self, text: str) -> list[str]:
        """Nombres propios con el apellido en el corpus y el resto no (ej: 'Lorenzo Dabbene').

        Detecta el caso que un modelo chico resuelve mal: busca solo el apellido y le atribuye el documento
        a la persona que nombró el usuario. Solo el patrón [nombres desconocidos] + apellido conocido, hasta
        3 palabras: 'Hola Valter Dabbene' o 'Las Varillas Córdoba' no son personas inexistentes.
        """
        found = []
        for match in _NAME_RE.finditer(text):
            parts = [
                part for part in match.group().split()
                if normalize(part) not in STOPWORDS and normalize(part) not in _GENERIC_TERMS
            ]
            if not 2 <= len(parts) <= _MAX_NAME_WORDS:
                continue
            *given_names, surname = parts
            if self._resolve(normalize(surname)) and not any(self._resolve(normalize(part)) for part in given_names):
                found.append(" ".join(parts))
        return found

    def _resolve_uncached(self, term: str) -> frozenset[str]:
        if term in self._vocabulary:
            return frozenset({term})
        # Typos de una letra solo en palabras largas: '1903' nunca debe matchear '1904'.
        if term.isalpha() and len(term) >= 5:
            return frozenset(token for token in self._vocabulary if token.isalpha() and _within_one_edit(term, token))
        return frozenset()


def render_index(documents: Iterable[Documento]) -> str:
    return "\n".join(
        f"- ID: {doc.id} | {doc.titulo} | Fecha clave: {doc.metadata.fecha_clave} | Tags: {', '.join(doc.tags)}"
        for doc in documents
    )


def render_documents(documents: Iterable[Documento]) -> str:
    # Un dato por línea con etiqueta: el modelo cita "Fuente" y "Fecha clave" sin mezclarlos con el criterio.
    return "\n\n---\n\n".join(
        f"[{doc.id}] {doc.titulo}\n"
        f"Fuente: {doc.metadata.fuente}\n"
        f"Fecha clave: {doc.metadata.fecha_clave}\n"
        f"Criterio: {doc.metadata.criterio_historiografico}\n"
        f"Contenido: {doc.contenido}"
        for doc in documents
    )
