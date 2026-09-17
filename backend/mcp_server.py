"""Servidor MCP por stdio: expone la consulta histórica. Nada más.

Se lanza como subproceso desde el backend (`python -m mcp_server`, cwd=backend/).
stdout es el canal del protocolo: todo log va a stderr.
"""

import logging
import re
import sys
from typing import Annotated

from mcp.server.mcpserver import Context, MCPServer
from pydantic import Field

from config import Settings
from logging_config import setup_logging
from mcp_meta import USER_QUESTION_MAX_CHARS, USER_QUESTION_META
from store.history import HistoryStore, HistoryStoreError, normalize, render_documents, render_index, tokenize

logger = logging.getLogger("mcp_server")

# Las palabras del aviso salen del input del usuario y van dentro de una instrucción al modelo: acotadas.
_MAX_WARNED_TERMS = 3
_MAX_WARNED_TERM_CHARS = 40


def _user_question(ctx: Context) -> str | None:
    """_meta lo manda cualquier cliente MCP: input externo, se valida tipo y largo."""
    value = (ctx.request_context.meta or {}).get(USER_QUESTION_META)
    return value[:USER_QUESTION_MAX_CHARS] if isinstance(value, str) else None


def _original_words(text: str, normalized_terms: list[str]) -> list[str]:
    """Recupera la grafía original ('Lorenzo') de los términos normalizados ('lorenzo')."""
    originals = {normalize(word): word for word in reversed(re.findall(r"\w+", text))}
    return [originals.get(term, term) for term in normalized_terms]


def _missing_terms(store: HistoryStore, tema: str, unmatched: list[str], user_question: str | None) -> list[str]:
    """Qué avisarle al modelo que NO figura en los documentos.

    Con la pregunta original (llega por _meta): nombres con una parte inexistente ('Juan Alvarez' aunque el
    modelo haya buscado solo 'Alvarez') y términos sin coincidencia que escribió el usuario. Los términos que
    inventó el modelo no se repiten: los copiaría textual en la respuesta.
    """
    if not user_question:
        missing = _original_words(tema, unmatched)
    else:
        names = store.unknown_names(user_question)
        covered = {normalize(part) for name in names for part in name.split()}
        asked = set(tokenize(user_question))
        terms = [term for term in unmatched if term in asked and term not in covered]
        missing = names + _original_words(user_question, terms)
    return [term for term in missing if len(term) <= _MAX_WARNED_TERM_CHARS][:_MAX_WARNED_TERMS]


def build_server(store: HistoryStore) -> MCPServer:
    server = MCPServer("HistoriaVarillas")

    @server.tool(structured_output=False)
    def consultar_fundacion_las_varillas(
        tema: Annotated[
            str,
            Field(max_length=200, description="Palabras clave concretas: nombres, fechas o lugares (ej: 'fundación', 'ferrocarril 1900')"),
        ],
        ctx: Context,
    ) -> str:
        """Busca documentos en la biblioteca histórica de Las Varillas (fundación, ferrocarril, historiadores, fechas)."""
        # Sin modo índice: el índice ya va en el system prompt. Con tema vacío el modelo recibía solo
        # títulos y respondía "no tengo información" aunque los documentos tenían la respuesta.
        if not tema.strip():
            logger.info("tool_empty_tema")
            return "Falta 'tema'. Volvé a llamar la herramienta con palabras clave concretas (ej: 'fundación', 'ferrocarril')."
        user_question = _user_question(ctx)
        result = store.search(tema)
        missing = _missing_terms(store, tema, result.unmatched_terms, user_question)
        logger.info(
            "tool_search",
            extra={"tema": tema, "hits": [doc.id for doc in result.documents], "missing": missing},
        )
        # El aviso va primero y es una instrucción concreta: un modelo de 3B no detecta solo que un
        # nombre de pila no coincide y atribuye el documento al nombre que usó el usuario.
        warning = ""
        if missing:
            words = ", ".join(f"«{word}»" for word in missing)
            warning = (
                f"AVISO: {words} no aparece en ningún documento. Empezá tu respuesta con: "
                f"\"No hay registros de {words} en los documentos.\" Después usá solo los datos de abajo, con los "
                "nombres exactamente como figuran, sin agregar profesiones, nacionalidades ni parentescos.\n\n"
            )
        if not result.documents:
            return f"{warning}Sin documentos para esa búsqueda. Índice disponible:\n" + render_index(store.documents)
        return warning + render_documents(result.documents)

    return server


def main() -> None:
    settings = Settings()
    setup_logging(settings.log_level, stream=sys.stderr)
    try:
        store = HistoryStore.from_file(settings.data_file)
    except HistoryStoreError as exc:
        logger.critical("mcp_server_data_error", extra={"error": str(exc)})
        sys.exit(1)
    logger.info("mcp_server_start", extra={"documents": len(store.documents)})
    try:
        build_server(store).run("stdio")
    except KeyboardInterrupt:  # Ctrl+C llega también al hijo en la misma consola
        pass


if __name__ == "__main__":
    main()
