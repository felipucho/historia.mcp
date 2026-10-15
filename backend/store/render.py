"""Formato del texto que ve el modelo: índice, documentos y extracción de citas. Sin conocimiento de MCP ni LLM.

rendered_ids lee la cabecera que escribe render_documents: cambiar una obliga a revisar la otra.
"""

import re
from collections.abc import Iterable

from store.history import Documento

# Cabecera de cada documento en render_documents: "[id] titulo". Mismo patrón que Documento.id.
_RENDERED_ID_RE = re.compile(r"^\[([A-Za-z0-9][A-Za-z0-9_-]*)\] ", re.MULTILINE)


# SOLID-S (responsabilidad única): arma el texto que lee el modelo (índice y documentos).
# Separado de HistoryStore: cambiar el formato no toca la carga ni la búsqueda.
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


def rendered_ids(text: str) -> list[str]:
    """IDs de los documentos presentes en un texto armado por render_documents, en orden y sin repetir."""
    return list(dict.fromkeys(_RENDERED_ID_RE.findall(text)))
