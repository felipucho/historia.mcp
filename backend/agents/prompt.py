"""System prompt: persona desde ia_config/*.txt (misma fuente que web.py) + reglas del agente + índice."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

RULES = """REGLAS:
1. Para cualquier dato histórico (personas, fechas, lugares, teorías) usá la herramienta de búsqueda antes de responder. No respondas de memoria.
2. Basate solo en lo que devuelve la herramienta. Si no hay datos, decí que no tenés esa información.
3. Si el usuario nombra a una persona y el registro tiene otro nombre de pila con el mismo apellido, aclaralo explícitamente con el nombre del registro. Nunca confirmes un nombre que no figura en los documentos.
4. Respondé en español, en pocas oraciones, citando la fuente del documento."""


def _read(directory: Path, name: str, default: str) -> str:
    try:
        return (directory / name).read_text(encoding="utf-8").strip() or default
    except FileNotFoundError:
        return default
    except OSError as exc:
        logger.warning("ia_config_read_failed", extra={"file": name, "error": str(exc)})
        return default


def build_system_prompt(ia_config_dir: Path, index_text: str) -> str:
    nombre = _read(ia_config_dir, "nombre.txt", "Asistente Histórico")
    personalidad = _read(ia_config_dir, "personalidad.txt", "Sos un experto en la historia de Las Varillas.")
    instrucciones = _read(ia_config_dir, "instrucciones.txt", "")
    conocimiento = _read(ia_config_dir, "conocimiento.txt", "")
    sections = [
        f"Tu nombre es {nombre}.",
        f"Personalidad:\n{personalidad}",
        f"Instrucciones:\n{instrucciones}" if instrucciones else "",
        f"Contexto adicional:\n{conocimiento}" if conocimiento else "",
        RULES,
        f"ÍNDICE DE DOCUMENTOS (solo títulos; el contenido se obtiene con la herramienta):\n{index_text}",
    ]
    return "\n\n".join(section for section in sections if section)
