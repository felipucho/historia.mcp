"""Contrato de _meta entre el cliente MCP (tools.registry) y el servidor (mcp_server).

Módulo sin dependencias: el subproceso MCP no debe importar código del lado cliente.
"""

# Extensión en _meta (canal del protocolo para contexto fuera de los argumentos): la pregunta original
# del usuario viaja con cada llamada, así la tool no depende de que el modelo la resuma bien.
USER_QUESTION_META = "historia-varillas/user_question"

# Mismo tope que el WebSocket. El servidor lo aplica igual: cualquier cliente MCP puede mandar _meta.
USER_QUESTION_MAX_CHARS = 1000
