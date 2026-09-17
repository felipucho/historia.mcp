"""Servidor MCP por stdio: expone la consulta histórica. Nada más.

Se lanza como subproceso desde el backend (`python -m mcp_server`, cwd=backend/).
stdout es el canal del protocolo: todo log va a stderr.
"""

import logging
import sys
from typing import Annotated

from mcp.server.mcpserver import MCPServer
from pydantic import Field

from config import Settings
from logging_config import setup_logging
from store.history import HistoryStore, HistoryStoreError, render_documents, render_index

logger = logging.getLogger("mcp_server")


def build_server(store: HistoryStore) -> MCPServer:
    server = MCPServer("HistoriaVarillas")

    @server.tool(structured_output=False)
    def consultar_fundacion_las_varillas(tema: Annotated[str, Field(max_length=200)] = "") -> str:
        """Busca en la biblioteca histórica de Las Varillas (fundación, ferrocarril, historiadores, fechas).

        Pasá en 'tema' palabras clave, nombres o un ID de documento (ej: 'Dabbene', 'ferrocarril 1900').
        Con 'tema' vacío devuelve el índice de documentos.
        """
        if not tema.strip():
            logger.info("tool_index")
            return "ÍNDICE DE DOCUMENTOS:\n" + render_index(store.documents)
        results = store.search(tema)
        logger.info("tool_search", extra={"tema": tema, "hits": [doc.id for doc in results]})
        if not results:
            return f"Sin documentos para '{tema}'. Índice disponible:\n" + render_index(store.documents)
        return render_documents(results)

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
