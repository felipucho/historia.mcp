import asyncio
import json
import os
import sys
import requests
from mcp import ClientSession, StdioServerParameters
from mcp.client.stdio import stdio_client

# ─── Configuración ────────────────────────────────────────────────────────────

BASE_DIR    = os.path.dirname(os.path.abspath(__file__))
PYTHON_PATH = sys.executable
SERVER_SCRIPT = os.path.join(BASE_DIR, "server.py")

# ─── Configuración de la IA ──────────────────────────────────────────────────
IA_CONFIG_DIR = os.path.join(BASE_DIR, "ia_config")

def leer_archivo_ia(nombre_archivo, default=""):
    """Lee un archivo de configuración de texto si existe."""
    ruta = os.path.join(IA_CONFIG_DIR, nombre_archivo)
    if os.path.exists(ruta):
        with open(ruta, "r", encoding="utf-8") as f:
            return f.read().strip()
    return default

OLLAMA_URL  = "http://localhost:11434"
OLLAMA_MODEL = leer_archivo_ia("model.txt", "llama3:latest")

# ─── Helpers ──────────────────────────────────────────────────────────────────

def verificar_ollama() -> bool:
    """Verifica si Ollama está corriendo."""
    try:
        response = requests.get(f"{OLLAMA_URL}/api/tags", timeout=5)
        return response.status_code == 200
    except:
        return False

def llamar_ollama(prompt: str) -> str:
    """
    Envía un prompt a Ollama y devuelve la respuesta.
    """
    payload = {
        "model": OLLAMA_MODEL,
        "prompt": prompt,
        "stream": False,
    }
    
    try:
        response = requests.post(
            f"{OLLAMA_URL}/api/generate",
            json=payload,
            timeout=240  # 4 minutos para prompts largos con contexto extendido
        )
        response.raise_for_status()
        data = response.json()
        return data.get("response", "").strip()
        
    except requests.exceptions.Timeout:
        return "⏱️ Ollama tardó demasiado. Intenta con un prompt más corto."
    except requests.exceptions.ConnectionError:
        return f"❌ No se puede conectar a Ollama en {OLLAMA_URL}"
    except Exception as e:
        return f"💥 Error: {str(e)}"


# ─── Lógica principal ────────────────────────────────────────────────────────

async def main():
    print("=== Cliente MCP - Historia de Las Varillas ===\n")

    # 0. Verificar que Ollama esté disponible
    print("Verificando Ollama...")
    if not verificar_ollama():
        print(f"❌ ERROR: Ollama no está disponible en {OLLAMA_URL}")
        print("   Asegúrate de que Ollama está corriendo: ollama serve")
        return

    print(f"✅ Ollama disponible. Modelo: {OLLAMA_MODEL}\n")

    # 1. Conectar con el servidor MCP (lo lanza automáticamente via stdio)
    server_params = StdioServerParameters(
        command=PYTHON_PATH,
        args=[SERVER_SCRIPT],
    )

    async with stdio_client(server_params) as (read, write):
        async with ClientSession(read, write) as session:
            await session.initialize()

            # 2. Obtener herramientas disponibles del servidor
            tools_result = await session.list_tools()
            tools_mcp = tools_result.tools

            print(f"Herramientas disponibles: {[t.name for t in tools_mcp]}\n")

            # 3. Inyección de Índice: cargar el índice de la biblioteca al iniciar
            print("[Cargando índice de la biblioteca...]")
            indice_biblioteca = ""
            try:
                resultado_indice = await session.call_tool(
                    "consultar_fundacion_las_varillas", arguments={"tema": ""}
                )
                if resultado_indice.content:
                    indice_biblioteca = resultado_indice.content[0].text
                    print(f"✅ Índice cargado:\n{indice_biblioteca}\n")
            except Exception as e:
                print(f"⚠️ No se pudo cargar el índice: {e}\n")

            # 4. Inicializar historial de conversación con system prompt dinámico
            nombre = leer_archivo_ia("nombre.txt", "Asistente Histórico")
            personalidad = leer_archivo_ia("personalidad.txt", "Eres una IA amable.")
            instrucciones = leer_archivo_ia("instrucciones.txt", "")
            conocimiento = leer_archivo_ia("conocimiento.txt", "")

            indice_texto = f"\n\nÍNDICE DE LA BIBLIOTECA HISTÓRICA:\n{indice_biblioteca}" if indice_biblioteca else ""
            system_prompt = (
                f"Tu nombre es {nombre}.\n\n"
                f"Personalidad:\n{personalidad}\n\n"
                f"Instrucciones:\n{instrucciones}\n\n"
                f"Conocimiento adicional y contexto:\n{conocimiento}"
                f"{indice_texto}\n\n"
                f"Usá la herramienta de búsqueda con el ID o las palabras clave correspondientes para obtener detalles de cada fragmento."
            )

            # 5. Bucle de conversación
            while True:
                pregunta = input("Vos: ").strip()
                if pregunta.lower() in ("salir", "exit", "quit"):
                    print("¡Hasta luego!")
                    break
                if not pregunta:
                    continue

                # 6. Búsqueda inteligente: buscar fragmentos relevantes para la pregunta
                print(f"\n[Buscando información sobre: '{pregunta}'...]")

                datos_json = None
                try:
                    resultado = await session.call_tool(
                        "consultar_fundacion_las_varillas", arguments={"tema": pregunta}
                    )
                    if resultado.content:
                        datos_json = resultado.content[0].text
                except Exception as e:
                    print(f"⚠️ No se pudo acceder a los datos: {e}")

                # 7. Construir prompt con contexto
                if datos_json:
                    prompt = f"""{system_prompt}

FRAGMENTOS RELEVANTES DE LA BIBLIOTECA:
{datos_json}

---

Usuario: {pregunta}

Responde basándote en los fragmentos proporcionados. Si la pregunta no está relacionada con Las Varillas o con los datos disponibles, indicá que no tenés información al respecto.

Asistente:"""
                else:
                    prompt = f"""{system_prompt}

---

Usuario: {pregunta}

Asistente:"""

                # 8. Llamar a Ollama con el contexto
                respuesta = llamar_ollama(prompt)
                print(f"\nIA: {respuesta}\n")


if __name__ == "__main__":
    asyncio.run(main())
