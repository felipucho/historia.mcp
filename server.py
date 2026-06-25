import sys
import os
import json
import requests

# 🩹 Inyectamos el venv con múltiples estrategias~
def _find_and_inject_venv():
    candidates = []

    # Estrategia 1: relativo al script
    if getattr(sys, 'frozen', False):
        script_dir = os.path.dirname(sys.executable)
    else:
        script_dir = os.path.dirname(os.path.abspath(__file__))

    candidates.append(os.path.join(script_dir, "venv", "Lib", "site-packages"))

    # Estrategia 2: directorio de trabajo actual
    cwd = os.getcwd()
    candidates.append(os.path.join(cwd, "venv", "Lib", "site-packages"))

    # Estrategia 3: ruta hardcodeada (fallback)
    candidates.append(r"c:\Users\felipe\Downloads\historia-mcp\venv\Lib\site-packages")

    for path in candidates:
        if os.path.exists(path) and path not in sys.path:
            sys.path.insert(0, path)
            return path
    return None

_injected = _find_and_inject_venv()

# Intentamos importar MCP
try:
    from mcp.server.fastmcp import FastMCP
except ModuleNotFoundError:
    import traceback
    sys.stderr.write(f"[ERROR] No se pudo importar mcp.\n")
    sys.stderr.write(f"  __file__  = {os.path.abspath(__file__)}\n")
    sys.stderr.write(f"  cwd       = {os.getcwd()}\n")
    sys.stderr.write(f"  venv path = {_injected}\n")
    sys.stderr.write(f"  sys.path  = {sys.path}\n")
    raise

# ╔══════════════════════════════════════════════════════╗
# ║   ✨ Servidor MCP - Historia de Las Varillas ✨      ║
# ║        🌸 Proyecto Las Varillas  🌸                  ║
# ╚══════════════════════════════════════════════════════╝

BASE_DIR  = os.path.dirname(os.path.abspath(__file__))
DATA_FILE = os.path.join(BASE_DIR, "fundacion.json")
OLLAMA_MODEL = "llama3:latest"  # Modelo disponible en Ollama
OLLAMA_URL = "http://localhost:11434"

def log(msg: str):
    """Escribe logs a stderr para no romper el protocolo stdio de MCP."""
    sys.stderr.write(f"[SERVER] {msg}\n")
    sys.stderr.flush()

mcp = FastMCP("HistoriaVarillas")

# ─────────────────────────────────────────────
# 📜 TOOL: Historia local
# ─────────────────────────────────────────────
@mcp.tool()
def consultar_fundacion_las_varillas(tema: str = "") -> str:
    """
    Consulta información histórica sobre la fundación de Las Varillas.
    Si 'tema' está vacío, devuelve el índice de documentos (IDs, títulos y tags).
    Si 'tema' tiene contenido, busca fragmentos que coincidan con esas palabras clave.
    """
    log(f"Llamada a herramienta: consultar_fundacion_las_varillas | tema='{tema}'")
    try:
        with open(DATA_FILE, "r", encoding="utf-8") as f:
            fragmentos = json.load(f)

        # Modo Índice: devolver solo IDs, títulos y tags
        if not tema.strip():
            log("Modo índice: devolviendo lista de fragmentos")
            lineas = []
            for frag in fragmentos:
                tags_str = ", ".join(frag.get("tags", []))
                lineas.append(
                    f"ID: {frag['id']} | Título: {frag['titulo']} | Tags: {tags_str}"
                )
            return "\n".join(lineas)

        # Búsqueda por palabras clave (fuzzy simple en minúsculas)
        palabras = tema.lower().split()
        resultados = []
        for frag in fragmentos:
            texto_busqueda = " ".join([
                frag.get("titulo", ""),
                frag.get("contenido", ""),
                " ".join(frag.get("tags", [])),
            ]).lower()
            if any(p in texto_busqueda for p in palabras):
                resultados.append(frag)

        if not resultados:
            log(f"Sin resultados para tema='{tema}'")
            return f"No encontré fragmentos relacionados con '{tema}'."

        log(f"Encontrados {len(resultados)} fragmento(s) para tema='{tema}'")
        partes = []
        for frag in resultados:
            tags_str = ", ".join(frag.get("tags", []))
            meta = frag.get("metadata", {})
            partes.append(
                f"📄 [{frag['id']}] {frag['titulo']}\n"
                f"📝 {frag['contenido']}\n"
                f"🏷️  Tags: {tags_str}\n"
                f"📌 Criterio: {meta.get('criterio_historiografico', '-')} | "
                f"Fecha clave: {meta.get('fecha_clave', '-')} | "
                f"Fuente: {meta.get('fuente', '-')}"
            )
        return "\n\n---\n\n".join(partes)

    except FileNotFoundError:
        log(f"Error: Archivo no encontrado - {DATA_FILE}")
        return f"😿 ¡No encontré el archivo! Buscaba en: {DATA_FILE}"
    except json.JSONDecodeError:
        log("Error: fundacion.json está malformado")
        return "😵 ¡El fundacion.json está malformado!"
    except Exception as e:
        log(f"Error inesperado leyendo fundación: {str(e)}")
        return f"💥 Error inesperado: {str(e)}"


# ─────────────────────────────────────────────
# 🤖 TOOL: Ollama
# ─────────────────────────────────────────────
@mcp.tool()
def preguntar_a_ollama(prompt: str) -> str:
    """
    Usa un modelo local de Ollama para responder preguntas.
    """
    log(f"Llamada a herramienta: preguntar_a_ollama con prompt: {prompt[:50]}...")
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json={
                "model": OLLAMA_MODEL,
                "prompt": prompt,
                "stream": False
            },
            timeout=120
        )
        response.raise_for_status()

        data = response.json()
        log("Respuesta recibida de Ollama exitosamente.")
        return data.get("response", "Sin respuesta del modelo")

    except requests.exceptions.Timeout:
        log(f"Timeout esperando respuesta de Ollama después de 120s")
        return "⏱️ Ollama tardó demasiado en responder. Intenta con un prompt más corto."
    except requests.exceptions.ConnectionError:
        log(f"No se pudo conectar a Ollama en {OLLAMA_URL}")
        return f"❌ No se puede conectar a Ollama en {OLLAMA_URL}. ¿Está corriendo?"
    except Exception as e:
        log(f"Error llamando a Ollama: {str(e)}")
        return f"💥 Error llamando a Ollama: {str(e)}"


# ─────────────────────────────────────────────
# 🚀 RUN
# ─────────────────────────────────────────────
if __name__ == "__main__":
    log("Iniciando servidor MCP en modo stdio...")
    log(f"Usando modelo: {OLLAMA_MODEL}")
    log(f"Conectando a: {OLLAMA_URL}")
    mcp.run(transport="stdio")
