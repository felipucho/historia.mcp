"""System prompt: persona desde ia_config/*.txt (misma fuente que web.py) + reglas del agente + índice."""

import logging
from pathlib import Path

logger = logging.getLogger(__name__)

# Reglas cortas, imperativas y al final del prompt: un modelo de 3B sigue mejor lo último que lee.
# Sin ejemplos con nombres propios: el modelo los copia literal en respuestas que no tienen nada que ver.
RULES = """REGLAS OBLIGATORIAS:
1. Para preguntas sobre la historia de Las Varillas, llamá primero a la herramienta de búsqueda con palabras clave concretas (nombres, fechas, lugares).
2. Respondé solo con datos que aparecen en el resultado de la herramienta. No agregues datos, fechas, profesiones, parentescos ni suposiciones propias.
3. Respondé la pregunta actual de forma directa, en 2 a 4 oraciones. No repitas respuestas anteriores.
4. Si los documentos muestran varias teorías o fechas sobre lo preguntado, presentalas todas, cada una con su fuente. No elijas cuál es la correcta: los documentos presentan un debate abierto.
5. Si el resultado trae un AVISO, seguilo: esa persona o dato no figura en los documentos y no hay que inventar relaciones. Si figura alguien con el mismo apellido, nombralo tal como aparece en el documento.
6. Si la pregunta no trata sobre la historia de Las Varillas, respondé que solo podés ayudar con ese tema.
7. Respondé siempre en español."""


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
        f"ÍNDICE DE DOCUMENTOS (solo títulos; el contenido se obtiene con la herramienta):\n{index_text}",
        RULES,
    ]
    return "\n\n".join(section for section in sections if section)
