import threading
from collections.abc import Sequence
from datetime import UTC, datetime

from store.repository import (
    BookRepository,
    Fragmento,
    Libro,
    RepositorioError,
    SlugOcupado,
    contenido_de,
)


# SOLID-L (sustitución de Liskov): FakeRepo cumple BookRepository y reemplaza a MongoBookRepository en tests.
# El lock deja usarlo desde asyncio.to_thread, igual que el repositorio real.
class FakeRepo(BookRepository):
    """Repositorio en memoria con la misma semántica que MongoBookRepository."""

    def __init__(self) -> None:
        self._lock = threading.Lock()
        self._libros: dict[str, Libro] = {}
        self._fragmentos: dict[str, list[Fragmento]] = {}
        self._version = 0

    def ping(self) -> None:
        return None

    def version(self) -> int:
        with self._lock:
            return self._version

    def guardar_libro(self, libro: Libro) -> None:
        with self._lock:
            existente = self._libros.get(libro.slug)
            if existente is None:
                self._libros[libro.slug] = libro.model_copy(update={"creado": datetime.now(UTC)})
                self._fragmentos[libro.slug] = []
            elif contenido_de(existente) != contenido_de(libro):
                raise SlugOcupado(f"El slug {libro.slug!r} ya existe con otro contenido")

    def guardar_fragmentos(self, libro_slug: str, fragmentos: Sequence[Fragmento]) -> None:
        with self._lock:
            if libro_slug not in self._libros:
                raise RepositorioError(f"No existe el libro {libro_slug!r}")
            if any(fragmento.libro_slug != libro_slug for fragmento in fragmentos):
                raise RepositorioError("Hay fragmentos que pertenecen a otro libro")
            ids = [fragmento.id for fragmento in fragmentos]
            if len(set(ids)) != len(ids):
                raise RepositorioError("Hay IDs de fragmento repetidos dentro del libro")
            ajenos = {f.id for slug, fs in self._fragmentos.items() if slug != libro_slug for f in fs}
            if repetidos := sorted(set(ids) & ajenos):
                raise RepositorioError(f"IDs de fragmento ya usados por otro libro: {', '.join(repetidos)}")
            if self._fragmentos[libro_slug] == list(fragmentos):
                return
            self._fragmentos[libro_slug] = list(fragmentos)
            if self._libros[libro_slug].estado == "publicado":
                self._version += 1

    def publicar(self, slug: str) -> int:
        with self._lock:
            libro = self._libros.get(slug)
            if libro is None:
                raise RepositorioError(f"No existe el libro {slug!r}")
            if libro.estado == "publicado":
                return self._version
            self._libros[slug] = libro.model_copy(update={"estado": "publicado"})
            self._version += 1
            return self._version

    def listar_publicados(self) -> list[Libro]:
        with self._lock:
            return [libro for libro in self._libros.values() if libro.estado == "publicado"]

    def fragmentos_publicados(self) -> list[Fragmento]:
        with self._lock:
            return [
                fragmento
                for slug, fragmentos in self._fragmentos.items()
                if self._libros[slug].estado == "publicado"
                for fragmento in fragmentos
            ]
