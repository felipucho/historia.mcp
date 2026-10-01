# Prompt: auditoría de completitud (Taller MCP 2.2 + SOLID)

Copiá todo lo que está debajo de la línea en una sesión nueva de Claude Code abierta en la raíz de `historia.mcp`.

---

Sos un auditor y también un docente. Tu tarea es verificar que el proyecto `historia.mcp` cumple **todo** lo que piden dos documentos de referencia: el plan "Taller MCP 2.2: Arquitectura Web y Agentes Interactivos" y la guía "Principios SOLID en Python con clases y métodos abstractos". No modifiques código. Solo leé, ejecutá comandos de verificación y entregá un informe.

El proyecto se va a **exponer frente a una clase**. Por eso, mientras verificás, explicá el código: qué hace, cómo lo hace y por qué está hecho así. La explicación tiene que servirme para presentarlo y para responder preguntas.

## Reglas de trabajo

1. Leé primero `CLAUDE.md` de la raíz. Ahí están documentadas las decisiones de diseño que se apartan del plan a propósito.
2. Para ubicar código usá el índice de codebase-memory (`search_graph`, `trace_path`, `get_code_snippet`, `get_architecture`). Llamá `check_index_coverage` sobre cada archivo que uses como evidencia. Grep solo para literales, configuración y archivos que no son código.
3. Cada ítem necesita evidencia concreta: `ruta:línea`, salida de un comando o captura del navegador. Sin evidencia, el ítem queda como "Sin verificar", nunca como "Cumple".
4. Ignorá el código legacy de la raíz (`server.py`, `client.py`, `web.py`, `index.html`). El plan se evalúa contra `backend/` y `frontend/`. Mencioná el legacy solo si un ítem únicamente se cumple ahí.
5. Clasificá cada ítem con uno de estos estados:
   - **Cumple**: está implementado como pide el documento.
   - **Equivalente**: se implementó distinto, la diferencia está justificada en `CLAUDE.md` o en un comentario del código, y el objetivo del requisito se logra igual. Citá la justificación.
   - **Parcial**: falta una parte. Decí cuál.
   - **Falta**: no está.
   - **Sin verificar**: no pudiste comprobarlo (por ejemplo, Ollama no está corriendo). Decí qué hace falta para verificarlo.

## Cómo explicar el código

Después de la tabla de cada sección (A1 a A6, B1 a B7), agregá un bloque **"Para exponer"** con:

1. **Qué hace**: dos o tres oraciones en lenguaje simple, para alguien que sabe Python pero no conoce el proyecto.
2. **Dónde está**: los archivos y funciones clave, con `ruta:línea`.
3. **Fragmento clave**: el trozo de código más representativo, de 15 líneas como máximo, copiado del proyecto (no inventado). Comentá línea por línea lo que no sea obvio.
4. **Por qué así**: la decisión de diseño detrás y qué problema evita. Si se aparta del plan del taller, explicá qué ganó el proyecto con ese cambio.
5. **Conexión con la teoría**: qué parte del plan o qué principio SOLID ilustra.
6. **Preguntas probables**: dos o tres preguntas que puede hacer el público, con su respuesta corta.

Explicá en este orden, porque sigue el camino de un mensaje: datos (`fundacion.json`, `store/`), servidor MCP, contratos abstractos (`llm/provider.py`, `tools/registry.py`), proveedores concretos, agente, API (REST y WebSocket), composición (`main.py`), frontend. Usá términos técnicos exactos, pero definí cada uno la primera vez que aparece (MCP, stdio, tool call, lifespan, WebSocket, system prompt, ABC, inyección de dependencias).

## Desvíos intencionales conocidos (verificá que el equivalente exista, no los marques como "Falta")

- Servidor MCP en `backend/mcp_server.py` con el SDK MCP 2.x de bajo nivel, sin `FastMCP`.
- La tool `consultar_fundacion_las_varillas` no tiene "modo índice" con `tema` vacío. El índice va en el system prompt (`render_index` dentro de `build_system_prompt`).
- Cliente HTTP async en vez de `requests` sincrónico. Verificá que no haya llamadas bloqueantes dentro del event loop.
- CORS con orígenes explícitos (`CORS_ORIGINS`), no `"*"`. Validación manual de `Origin` en el WebSocket.
- uvicorn en `127.0.0.1`, no `0.0.0.0`.
- `Conversation` guarda solo pares (pregunta, respuesta final), no los mensajes `role=tool`.
- Proveedor por mensaje (`ChatIn.provider`): local (Ollama) o nube (Groq). El plan solo pide Ollama.
- Streaming con `DeltaEvent`, además del `ResponseEvent` final.
- Configuración por `.env` y `backend/config.py`, en vez de constantes en `main.py`.

Si encontrás otro desvío sin justificación escrita, clasificalo como "Parcial" o "Falta" y explicá el riesgo.

## Parte A: Taller MCP 2.2

### A1. Arquitectura y flujo de un mensaje
1. Existen las cuatro capas: frontend React, backend FastAPI, Ollama local, servidor MCP.
2. Carga inicial: el frontend pide `GET /api/fundacion` al montar.
3. `GET /api/fundacion` devuelve los documentos (`raw`) y el texto completo (`full_text`, formato `## titulo\ncontenido`). Devuelve 404 si falta el archivo de datos.
4. El chat viaja por WebSocket en `/ws/chat`.
5. Las tools del servidor MCP se convierten al formato de Ollama: `type: "function"`, `name`, `description`, `parameters` tomado de `inputSchema`.
6. El agente manda contexto + lista de tools al modelo.
7. Si el modelo pide la tool, el backend la ejecuta contra el servidor MCP por **stdio** y devuelve el resultado al modelo para otra iteración.
8. El bucle de razonamiento tiene un límite de 5 iteraciones. Verificá qué pasa al llegar al límite.
9. Durante el bucle se mandan estados parciales por el WebSocket: "Pensando..." y "Consultando base histórica..." (o equivalentes). Anotá los textos reales.
10. La respuesta final llega con tipo `response`. Los errores llegan con tipo `error`.
11. Hay fallback para tool calls que el modelo escribe como JSON dentro del texto.
12. Se conserva el contexto conversacional entre preguntas de la misma conexión.

### A2. Stack tecnológico
Para cada tecnología, indicá dónde se declara (`requirements*.txt`, `frontend/package.json`) y dónde se usa:
Python, FastAPI, Uvicorn, Pydantic, MCP SDK, Ollama (`llama3.2`), Requests o su reemplazo, `python-multipart`, React, Vite, Axios, Tailwind CSS, PostCSS, Autoprefixer, Lucide React, WebSocket API del navegador.
Si una librería falta, decí si hay un reemplazo y si está justificado.

### A3. Backend, paso por paso
1. Carpeta `backend/`, venv y `requirements.txt` con al menos `mcp`, `fastapi`, `uvicorn`, `pydantic`.
2. `fundacion.json` con documentos de campos `id`, `titulo`, `contenido`, `tags`, `metadata.criterio`.
3. Servidor MCP:
   - Expone `consultar_fundacion_las_varillas(tema)`.
   - Busca por ID exacto y por palabra clave en título, contenido y tags.
   - Devuelve un mensaje claro cuando no encuentra resultados.
   - Maneja el archivo de datos inexistente sin romperse.
   - Cada documento devuelto incluye título, criterio y contenido.
   - Corre como script (`python -m mcp_server`).
4. Orquestador `main.py`:
   - `lifespan` conecta al servidor MCP al arrancar y lo cierra al apagar.
   - Lista las tools al arrancar.
   - Inyecta el índice de documentos en el system prompt.
   - El system prompt define al historiador de Las Varillas y obliga a llamar a la tool ante dudas fuera del índice.
   - Middleware CORS configurado.
   - Logging con nivel INFO.
   - Al arrancar imprime una confirmación del tipo "MCP Conectado y Listo" (entregable 1).
   - Se lanza con `python main.py` en el puerto 8000.
5. Manejo de `WebSocketDisconnect` y de excepciones dentro del WebSocket: el error se manda al cliente.

### A4. Frontend, paso por paso
1. Proyecto Vite + React en `frontend/`.
2. Dependencias `axios` y `lucide-react` instaladas y usadas.
3. Tailwind configurado: `content` escanea `index.html` y `src/**/*.{js,ts,jsx,tsx}`; fuentes `Inter` (sans) y `Outfit` (display).
4. `src/index.css`: directivas de Tailwind, Google Fonts, fondo oscuro `#0f172a` con gradientes radiales, clase `.glass` (blur 12px, borde translúcido) y `.custom-scrollbar`.
5. Componente principal:
   - Pide `/api/fundacion` al montar.
   - Abre el WebSocket y **reintenta a los 3 s** si se cierra.
   - Mensaje de bienvenida del asistente.
   - Sidebar con el índice. Al hacer clic hace `scrollIntoView({ behavior: 'smooth' })` hasta el documento.
   - Botón para mostrar u ocultar el sidebar.
   - Cabecera "Las Varillas Digital" y botón "Consultar Agente".
   - Lector central con todos los documentos. Cada uno tiene `id` como ancla y margen de scroll (`scroll-mt`).
   - Título "Debate sobre la fundación de Las Varillas" y pie con año dinámico.
   - Drawer derecho de chat con cabecera "Asistente Varillas", indicador en línea y botón de cierre.
   - Burbujas distintas para usuario y asistente.
   - Spinner (`Loader2`) con el texto de estado del agente.
   - `textarea`: Enter envía, Shift+Enter hace salto de línea.
   - Botón de enviar deshabilitado si está cargando o el input está vacío.
   - Aviso si el servidor no está conectado al enviar.
   - Backdrop con blur cuando el chat está abierto.
   - Autoscroll al último mensaje.
   - Si el componente está dividido en varios archivos, está bien; indicá dónde quedó cada parte.

### A5. Puesta en marcha
1. `.claude/launch.json` define `backend` y `frontend`.
2. Ejecutá `pytest` desde `backend/`. Reportá cantidad de tests y fallos.
3. Ejecutá `npm --prefix frontend run lint` y `npm --prefix frontend run build`. Reportá errores.
4. Si Ollama está corriendo con `llama3.2`, levantá ambos servidores con `preview_start` y probá la app en el navegador. Si no está, marcá A6 como "Sin verificar" y decí cómo verificarlo.

### A6. Entregables del estudiante
1. **Orquestador**: la consola del backend muestra la confirmación de conexión al arrancar. Mostrá la línea de log.
2. **Navegación fluida**: clic en un ítem del sidebar hace scroll suave al documento exacto. Probalo en el navegador.
3. **Agente historiador**: preguntá "¿Quién es Lorenzo Dabbene?" y "¿Cuándo llegó el tren?". Verificá en los logs que el agente llamó a la tool MCP por su cuenta y que la respuesta usa los datos devueltos. Después hacé una repregunta que dependa de la anterior (por ejemplo "¿Y en qué año fue eso?") para comprobar que no pierde el contexto.

## Parte B: SOLID y clases abstractas

Evaluá cada principio sobre `backend/`. Para cada uno, dá evidencia a favor, violaciones encontradas y gravedad (alta, media, baja).

### B1. SRP (responsabilidad única)
- Cada módulo tiene una sola razón para cambiar: `store/history.py` (datos), `llm/*` (proveedores), `tools/registry.py` (tools), `agents/historian.py` (razonamiento), `api/*` (transporte), `main.py` (solo composición).
- Buscá clases o funciones que mezclen responsabilidades: por ejemplo, el agente sabiendo de WebSocket, o la API con lógica de agente.
- Señalá funciones muy largas o con complejidad alta.

### B2. OCP (abierto/cerrado)
- Agregar un proveedor LLM nuevo no exige modificar `HistorianAgent`. Buscá `if`/`elif` sobre el tipo de proveedor fuera de la composición.
- Agregar una tool nueva solo requiere declararla en `mcp_server.py`.

### B3. LSP (sustitución de Liskov)
- `OllamaClient`, `OpenAICompatClient` y `FakeLLM` son intercambiables donde se espera `LLMProvider`.
- Las firmas de las subclases coinciden con la base: mismos parámetros, tipos de retorno compatibles, sin precondiciones más estrictas ni excepciones nuevas que el llamador no espera.
- Ninguna subclase deja un método del contrato con `NotImplementedError` o con comportamiento vacío que rompa a los llamadores.
- Lo mismo para `ToolRegistry`, `McpToolRegistry` y `FakeTools`.

### B4. ISP (segregación de interfaces)
- `LLMProvider` y `ToolRegistry` no obligan a implementar métodos que algunas clases no usan.
- Señalá métodos implementados solo para cumplir el contrato (por ejemplo, devuelven un valor fijo sin hacer nada) y decí si eso es aceptable.

### B5. DIP (inversión de dependencias)
- `HistorianAgent` depende de abstracciones (`LLMProvider`, `ToolRegistry`) recibidas por constructor, no de clases concretas.
- `main.py` es la raíz de composición: es el único lugar que instancia clases concretas.
- La capa `api/` recibe sus dependencias por `app.state` o inyección, sin importar implementaciones concretas.
- Verificá con `trace_path` que no haya imports de módulos concretos desde módulos de alto nivel.
- Los tests usan fakes en lugar de servicios reales: eso confirma que las dependencias están invertidas.

### B6. Clases abstractas y tipado
- Los contratos usan `abc.ABC` y `@abstractmethod`. Comprobá que instanciar la clase base lanza `TypeError`.
- Si hay propiedades abstractas, usan `@property` encima de `@abstractmethod`.
- Indicá si algún contrato estaría mejor como `typing.Protocol` (duck typing con chequeo estático) y por qué.
- Hay type hints en las firmas públicas. Si `mypy` está instalado, corrélo sobre `backend/` y reportá errores. Si no está, decilo; no lo instales sin preguntar.
- Si `pylint`, `flake8` o `ruff` están instalados, corrélos y resumí los avisos relacionados con diseño (clases largas, demasiados argumentos, acoplamiento).

### B7. Pragmatismo
- Señalá abstracciones que no aportan nada (una sola implementación y sin uso en tests) o sobreingeniería.
- Verificá que las decisiones de diseño estén documentadas (`CLAUDE.md`, docstrings).

## Formato del informe

1. **Resumen**: tres líneas como máximo. Cuántos ítems cumplen, cuántos faltan, y el riesgo principal.
2. **Panorama general para exponer**: un diagrama ASCII del recorrido de un mensaje (navegador, WebSocket, agente, LLM, MCP, datos) y una explicación de un párrafo de cada capa.
3. **Por sección** (A1 a A6, B1 a B7): la tabla con columnas `#`, `Requisito`, `Estado`, `Evidencia`, `Nota`, seguida del bloque "Para exponer".
4. **Faltantes priorizados**: lista ordenada por impacto. Para cada uno, el arreglo propuesto y los archivos que tocaría.
5. **Comandos ejecutados** con su resultado resumido (no pegues logs completos).
6. **Guion de exposición**: un orden sugerido de diapositivas o temas para unos 15 minutos, con el tiempo de cada parte, qué mostrar en pantalla (archivo o demo en el navegador) y la idea principal de cada una. Incluí una demo en vivo: preguntar "¿Cuándo llegó el tren?" y mostrar en los logs la llamada a la tool MCP.
7. **Glosario**: cada término técnico usado, con una definición de una línea.

Terminá el informe ahí. No implementes ningún arreglo hasta que yo apruebe la lista de faltantes.
