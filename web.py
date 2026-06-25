import json
import os
import sys
import webbrowser
import urllib.request
import urllib.error
from http.server import BaseHTTPRequestHandler, ThreadingHTTPServer

# ╔══════════════════════════════════════════════════════╗
# ║   🌐 Servidor Web - Historia de Las Varillas 🌐      ║
# ║      Chat estilo ChatGPT (solo librería estándar)     ║
# ╚══════════════════════════════════════════════════════╝

# Forzar salida UTF-8 en consolas Windows (evita UnicodeEncodeError con emojis)
for _stream in (sys.stdout, sys.stderr):
    try:
        _stream.reconfigure(encoding="utf-8")
    except Exception:
        pass

# ─── Configuración ─────────────────────────────────────────────────────────────
BASE_DIR      = os.path.dirname(os.path.abspath(__file__))
DATA_FILE     = os.path.join(BASE_DIR, "fundacion.json")
IA_CONFIG_DIR = os.path.join(BASE_DIR, "ia_config")
INDEX_HTML    = os.path.join(BASE_DIR, "index.html")

HOST = "127.0.0.1"
PORT = 8000

OLLAMA_URL = "http://localhost:11434"


def leer_archivo_ia(nombre_archivo, default=""):
    """Lee un archivo de configuración de texto si existe."""
    ruta = os.path.join(IA_CONFIG_DIR, nombre_archivo)
    if os.path.exists(ruta):
        with open(ruta, "r", encoding="utf-8") as f:
            return f.read().strip()
    return default


OLLAMA_MODEL = leer_archivo_ia("model.txt", "llama3:latest")
NOMBRE_BOT   = leer_archivo_ia("nombre.txt", "Asistente Histórico")


# ─── Datos y búsqueda (misma lógica del servidor MCP) ───────────────────────────

def cargar_fragmentos():
    """Carga el arreglo de fragmentos de fundacion.json."""
    with open(DATA_FILE, "r", encoding="utf-8") as f:
        return json.load(f)


def construir_indice(fragmentos):
    """Devuelve el índice (IDs, títulos y tags) para inyectar en el system prompt."""
    lineas = []
    for frag in fragmentos:
        tags = ", ".join(frag.get("tags", []))
        lineas.append(f"ID: {frag['id']} | Título: {frag['titulo']} | Tags: {tags}")
    return "\n".join(lineas)


def buscar_fragmentos(fragmentos, tema):
    """
    Búsqueda fuzzy simple: pasa todo a minúsculas y verifica si alguna palabra
    de la consulta coincide con el título, contenido o tags del fragmento.
    Si no hay coincidencias, devuelve todos los fragmentos (fallback).
    """
    tema = (tema or "").strip().lower()
    if not tema:
        return fragmentos

    palabras = tema.split()
    encontrados = []
    for frag in fragmentos:
        texto = " ".join([
            frag.get("titulo", ""),
            frag.get("contenido", ""),
            " ".join(frag.get("tags", [])),
        ]).lower()
        if any(p in texto for p in palabras):
            encontrados.append(frag)

    return encontrados or fragmentos


def formatear_fragmentos(frags):
    """Da formato legible a los fragmentos para enviarlos como contexto."""
    partes = []
    for frag in frags:
        tags = ", ".join(frag.get("tags", []))
        meta = frag.get("metadata", {})
        partes.append(
            f"[{frag['id']}] {frag['titulo']}\n"
            f"{frag['contenido']}\n"
            f"Tags: {tags}\n"
            f"Criterio: {meta.get('criterio_historiografico', '-')} | "
            f"Fecha clave: {meta.get('fecha_clave', '-')} | "
            f"Fuente: {meta.get('fuente', '-')}"
        )
    return "\n\n---\n\n".join(partes)


def construir_system_prompt(indice):
    """Arma el system prompt dinámico con la personalidad y el índice inyectado."""
    personalidad  = leer_archivo_ia("personalidad.txt", "Eres una IA amable.")
    instrucciones = leer_archivo_ia("instrucciones.txt", "")
    conocimiento  = leer_archivo_ia("conocimiento.txt", "")
    return (
        f"Tu nombre es {NOMBRE_BOT}.\n\n"
        f"Personalidad:\n{personalidad}\n\n"
        f"Instrucciones:\n{instrucciones}\n\n"
        f"Conocimiento adicional y contexto:\n{conocimiento}\n\n"
        f"ÍNDICE DE LA BIBLIOTECA HISTÓRICA:\n{indice}\n\n"
        f"Usá los fragmentos relevantes para responder con precisión."
    )


# ─── Ollama (vía urllib, sin dependencias externas) ─────────────────────────────

def verificar_ollama():
    """Verifica si Ollama está corriendo."""
    try:
        with urllib.request.urlopen(f"{OLLAMA_URL}/api/tags", timeout=5) as r:
            return r.status == 200
    except Exception:
        return False


def llamar_ollama(prompt):
    """Envía un prompt a Ollama y devuelve la respuesta."""
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    try:
        # 240s para prompts largos con contexto extendido
        with urllib.request.urlopen(req, timeout=240) as r:
            data = json.loads(r.read().decode("utf-8"))
            return data.get("response", "").strip() or "Sin respuesta del modelo."
    except TimeoutError:
        return "⏱️ Ollama tardó demasiado en responder. Probá con una pregunta más corta."
    except urllib.error.URLError:
        return f"❌ No se puede conectar a Ollama en {OLLAMA_URL}. ¿Está corriendo? (ollama serve)"
    except Exception as e:
        return f"💥 Error llamando a Ollama: {str(e)}"


def armar_prompt(pregunta):
    """Construye el prompt completo: índice + fragmentos relevantes + pregunta."""
    fragmentos    = cargar_fragmentos()
    indice        = construir_indice(fragmentos)
    system_prompt = construir_system_prompt(indice)
    relevantes    = buscar_fragmentos(fragmentos, pregunta)
    contexto      = formatear_fragmentos(relevantes)

    return f"""{system_prompt}

FRAGMENTOS RELEVANTES DE LA BIBLIOTECA:
{contexto}

---

Usuario: {pregunta}

Responde basándote en los fragmentos proporcionados. Si la pregunta no está relacionada con Las Varillas o con los datos disponibles, indicá que no tenés información al respecto.

Asistente:"""


def responder(pregunta):
    """Pipeline sin streaming (respuesta completa de una sola vez)."""
    if not verificar_ollama():
        return f"❌ No se puede conectar a Ollama en {OLLAMA_URL}. Iniciá 'ollama serve' y recargá."
    return llamar_ollama(armar_prompt(pregunta))


def stream_ollama(prompt):
    """
    Generador: hace streaming token-a-token desde Ollama (stream=true).
    Ollama emite NDJSON (una línea JSON por token); cedemos cada trozo de texto.
    """
    payload = json.dumps({
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": True,
    }).encode("utf-8")

    req = urllib.request.Request(
        f"{OLLAMA_URL}/api/generate",
        data=payload,
        headers={"Content-Type": "application/json"},
        method="POST",
    )

    with urllib.request.urlopen(req, timeout=240) as r:
        for linea in r:
            linea = linea.strip()
            if not linea:
                continue
            try:
                data = json.loads(linea.decode("utf-8"))
            except Exception:
                continue
            trozo = data.get("response", "")
            if trozo:
                yield trozo
            if data.get("done"):
                break


# ─── Servidor HTTP ──────────────────────────────────────────────────────────────

class Handler(BaseHTTPRequestHandler):

    def _send(self, code, content, content_type="text/html; charset=utf-8"):
        body = content if isinstance(content, bytes) else content.encode("utf-8")
        self.send_response(code)
        self.send_header("Content-Type", content_type)
        self.send_header("Content-Length", str(len(body)))
        self.end_headers()
        self.wfile.write(body)

    def do_GET(self):
        if self.path in ("/", "/index.html"):
            try:
                with open(INDEX_HTML, "r", encoding="utf-8") as f:
                    html = f.read().replace("__BOT_NAME__", NOMBRE_BOT)
                self._send(200, html)
            except FileNotFoundError:
                self._send(500, "Falta index.html", "text/plain; charset=utf-8")
        else:
            self._send(404, "No encontrado", "text/plain; charset=utf-8")

    def _sse(self, obj):
        """Escribe un evento Server-Sent Event y fuerza el envío inmediato."""
        self.wfile.write(f"data: {json.dumps(obj)}\n\n".encode("utf-8"))
        self.wfile.flush()

    def do_POST(self):
        if self.path == "/api/chat":
            length = int(self.headers.get("Content-Length", 0))
            raw = self.rfile.read(length) if length else b"{}"
            try:
                data = json.loads(raw.decode("utf-8"))
                pregunta = (data.get("message") or "").strip()
            except Exception:
                pregunta = ""

            if not pregunta:
                self._send(400, json.dumps({"error": "Mensaje vacío"}),
                           "application/json; charset=utf-8")
                return

            # Respuesta en streaming vía Server-Sent Events (token a token)
            self.send_response(200)
            self.send_header("Content-Type", "text/event-stream; charset=utf-8")
            self.send_header("Cache-Control", "no-cache")
            self.end_headers()

            if not verificar_ollama():
                self._sse({"error": f"❌ No se puede conectar a Ollama en {OLLAMA_URL}. Iniciá 'ollama serve' y recargá."})
                self._sse({"done": True})
                return

            try:
                for trozo in stream_ollama(armar_prompt(pregunta)):
                    self._sse({"delta": trozo})
                self._sse({"done": True})
            except TimeoutError:
                self._sse({"error": "⏱️ Ollama tardó demasiado en responder."})
                self._sse({"done": True})
            except urllib.error.URLError:
                self._sse({"error": f"❌ Se perdió la conexión con Ollama en {OLLAMA_URL}."})
                self._sse({"done": True})
            except (BrokenPipeError, ConnectionResetError):
                pass  # el cliente cerró la pestaña a mitad del stream
            except Exception as e:
                self._sse({"error": f"💥 Error: {str(e)}"})
                self._sse({"done": True})
        else:
            self._send(404, json.dumps({"error": "Ruta no encontrada"}),
                       "application/json; charset=utf-8")

    def log_message(self, fmt, *args):
        sys.stderr.write("[WEB] " + (fmt % args) + "\n")


def main():
    print("=== Servidor Web - Historia de Las Varillas ===")
    print(f"Modelo Ollama: {OLLAMA_MODEL}")
    if not verificar_ollama():
        print(f"⚠️  Ollama no responde en {OLLAMA_URL}. Iniciá 'ollama serve' antes de chatear.")
    else:
        print("✅ Ollama disponible.")

    url = f"http://{HOST}:{PORT}"
    print(f"🌐 Abrí {url} en tu navegador (Ctrl+C para detener).")
    try:
        webbrowser.open(url)
    except Exception:
        pass

    server = ThreadingHTTPServer((HOST, PORT), Handler)
    try:
        server.serve_forever()
    except KeyboardInterrupt:
        print("\n¡Hasta luego!")
        server.shutdown()


if __name__ == "__main__":
    main()
