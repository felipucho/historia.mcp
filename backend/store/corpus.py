"""Convierte los fragmentos publicados al formato Documento que usan el lector y el prompt."""

import threading

from store.history import Documento, HistoryStore, Metadata
from store.repository import BookRepository, Fragmento


def documentos_publicados(repo: BookRepository) -> list[Documento]:
    return [documento_desde(fragmento) for fragmento in repo.fragmentos_publicados()]


def documento_desde(fragmento: Fragmento) -> Documento:
    # Documento todavía exige los tres campos de metadata de fundacion.json. La parte D lo relaja.
    return Documento(
        id=fragmento.id,
        titulo=fragmento.titulo,
        contenido=fragmento.contenido,
        tags=fragmento.tags,
        metadata=Metadata.model_validate(fragmento.metadata),
    )


class CorpusVivo:
    """Índice en memoria que se rehace cuando cambia meta.version (plan 4.3, opción 1).

    La versión se lee antes de cargar los datos. Si un cambio llega durante la carga, la versión guardada queda
    vieja y la llamada siguiente vuelve a cargar.
    """

    def __init__(self, repo: BookRepository) -> None:
        self._repo = repo
        self._lock = threading.Lock()
        self._version: int | None = None
        self._store: HistoryStore | None = None

    def store(self) -> HistoryStore:
        version = self._repo.version()
        with self._lock:
            if self._store is None or version != self._version:
                self._store = HistoryStore(documentos_publicados(self._repo), permitir_vacio=True)
                self._version = version
            return self._store
