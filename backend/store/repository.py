"""Protocolo de persistencia de libros y fragmentos. Sin conocimiento de HTTP, MCP ni LLM."""

from abc import ABC, abstractmethod
from collections.abc import Sequence
from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, Field, field_validator

from store.tags import normalizar_tags

# El id del fragmento es el ancla DOM del lector (plan 4.2): mismos caracteres seguros que Documento.
ID_PATTERN = r"^[A-Za-z0-9][A-Za-z0-9_-]*$"
SLUG_PATTERN = r"^[a-z0-9][a-z0-9-]*$"


class RepositorioError(RuntimeError):
    """Operación rechazada: libro inexistente, fragmento ajeno, id repetido o base no disponible."""


class SlugOcupado(RepositorioError):
    """Ya existe un libro con ese slug y contenido distinto."""


class Tagueo(BaseModel):
    origen: str = "manual"
    revisado: bool = True


class Libro(BaseModel):
    slug: str = Field(pattern=SLUG_PATTERN, max_length=80)
    titulo: str = Field(min_length=1)
    autor: str = Field(min_length=1)
    anio: int
    fuente_tipo: Literal["primaria", "secundaria"]
    estado: Literal["borrador", "publicado"] = "borrador"
    resumen: str = ""
    temas: list[str] = Field(default_factory=list)
    hash_texto: str | None = None
    creado: datetime | None = None


class Fragmento(BaseModel):
    id: str = Field(pattern=ID_PATTERN, max_length=64)
    libro_slug: str = Field(pattern=SLUG_PATTERN, max_length=80)
    orden: int = Field(ge=1)
    seccion: str = ""
    titulo: str = Field(min_length=1)
    contenido: str = Field(min_length=1)
    tags: list[str] = Field(default_factory=list)
    metadata: dict[str, Any] = Field(default_factory=dict)
    tagueo: Tagueo = Field(default_factory=Tagueo)

    # Va en el modelo, no en cada repositorio: fake, Mongo y la siembra quedan con las mismas reglas.
    @field_validator("tags")
    @classmethod
    def _normalizar_tags(cls, tags: list[str]) -> list[str]:
        return normalizar_tags(tags)


def contenido_de(libro: Libro) -> dict[str, Any]:
    """Campos que cuentan para decidir si dos libros con el mismo slug son el mismo.

    El estado y la fecha de creación no cuentan: la siembra vuelve a guardar el libro después de publicarlo.
    """
    return libro.model_dump(exclude={"estado", "creado"})


# SOLID-D (inversión de dependencias): la API, el MCP y la siembra dependen de esta abstracción, no del driver.
class BookRepository(ABC):
    """Única puerta a la base. Las operaciones son síncronas: el backend las llama con asyncio.to_thread."""

    @abstractmethod
    def ping(self) -> None:
        """Verifica la conexión. Lanza RepositorioError que nombra la variable a revisar si no responde."""

    @abstractmethod
    def version(self) -> int:
        """Devuelve meta.version. Sin datos todavía, 0."""

    @abstractmethod
    def guardar_libro(self, libro: Libro) -> None:
        """Inserta el libro. Con el mismo slug y el mismo contenido no hace nada, y no cambia el estado guardado.

        Con el mismo slug y otro contenido lanza SlugOcupado.
        """

    @abstractmethod
    def guardar_fragmentos(self, libro_slug: str, fragmentos: Sequence[Fragmento]) -> None:
        """Reemplaza todos los fragmentos del libro. Si el libro está publicado, sube meta.version.

        Lanza RepositorioError si el libro no existe, si un fragmento es de otro libro, o si un id se repite
        dentro del libro o ya existe en otro.
        """

    @abstractmethod
    def publicar(self, slug: str) -> int:
        """Pasa el libro a publicado y sube meta.version en 1. Si ya estaba publicado, no cambia nada.

        Devuelve la versión vigente. Lanza RepositorioError si el libro no existe.
        """

    @abstractmethod
    def listar_publicados(self) -> list[Libro]:
        """Libros con estado publicado."""

    @abstractmethod
    def fragmentos_publicados(self) -> list[Fragmento]:
        """Fragmentos de todos los libros publicados."""
