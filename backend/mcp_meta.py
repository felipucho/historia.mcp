"""Contratos compartidos por el cliente MCP, el servidor y el prompt.

Módulo sin dependencias: el subproceso MCP no debe importar código del lado cliente.
"""

# SOLID-D (inversión de dependencias): contrato compartido por el servidor MCP y el cliente.
# Ninguno de los dos importa al otro: ambos dependen de este módulo, que no importa nada.
# Extensión en _meta (canal del protocolo para contexto fuera de los argumentos): la pregunta original
# del usuario viaja con cada llamada, así la tool no depende de que el modelo la resuma bien.
USER_QUESTION_META = "historia-varillas/user_question"

# Mismo tope que el WebSocket. El servidor lo aplica igual: cualquier cliente MCP puede mandar _meta.
USER_QUESTION_MAX_CHARS = 1000

# Prefijo del texto que devuelve la tool cuando falta un término. La regla 5 del prompt lo nombra:
# si cambia aquí, cambia también la regla.
AVISO_PREFIJO = "AVISO"
