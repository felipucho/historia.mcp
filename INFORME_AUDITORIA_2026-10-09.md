# Auditoría historia.mcp, corrida del 2026-10-09

Alcance: `backend/` y `frontend/`. El legacy de la raíz no se evaluó. La auditoría no modificó código; después se aplicó la refactorización de la sección 10. El informe previo del 2026-10-01 (`INFORME_AUDITORIA.md`) no se tocó; esta corrida lo reemplaza para la exposición. Los números de línea citados en las secciones 2 a 9 corresponden al código auditado (commit `0345084`); los de las secciones 10 y 11, al commit `ad09251`. La rama `solid-comentarios` agrega comentarios y corre esas líneas, sin cambiar código.

## 1. Resumen

- **Cumple o equivale a lo pedido:** casi todo el taller (A1 a A6) y los principios SOLID (B1 a B7). Las diferencias con el plan están documentadas en `CLAUDE.md` (ver sección 5).
- **Verificado en vivo:** tests (118 pasan), lint, build, mypy, arranque del backend, scroll del índice en el navegador, error del chat cuando Ollama no responde, y la tool MCP llamada directamente.
- **Verificado después (sección 10):** el agente llamando a la tool en vivo con `llama3.2:3b` (A6.3). Durante la auditoría Ollama no estaba corriendo; después se levantó. La evaluación (`evals`) dio 17/18: ver sección 11.
- **Riesgo para la exposición:** A6.3 es la demo principal. Sin Ollama no se puede mostrar en vivo; con Ollama levantado, la demo local funciona. El informe previo registra además que el modelo en la nube no llamó a la tool en una de dos pruebas.
- **Discrepancia con el informe previo:** el previo dice "ruff sin avisos". Hoy `ruff check backend` reporta 12 `I001` (imports sin ordenar). Se corrigieron después con `ruff check backend --fix`.

## 2. Ejecución

| Comando | Resultado |
|---|---|
| `pytest` (desde `backend/`) | 118 passed en la auditoría; 136 passed después de la refactorización |
| `npm --prefix frontend run lint` | exit 0 |
| `npm --prefix frontend run build` | OK. JS 242 kB (76 kB gzip) |
| `mypy .` (`backend/mypy.ini`) | Success, 30 archivos en la auditoría; 37 después de la refactorización |
| `ruff check backend` | 12 `I001` en la auditoría. Aplicado `--fix`: sin avisos |
| Instanciar `LLMProvider()` y `ToolRegistry()` | `TypeError` en ambos (los contratos son ABC) |
| `preview_start backend` | Arranca en 8000. Logs: `store_loaded` (3 docs), `ollama_unavailable_at_startup` (esperado), `mcp_connected` (tool `consultar_fundacion_las_varillas`), `cloud_llm_configured` |
| `preview_start frontend` y navegador | Carga `/api/fundacion` y `/api/modelos` con 200 |
| Clic en "1904" del índice (JS) | `main.scrollTop` pasa a 953. El artículo queda a 32 px del tope del lector y recibe el foco |
| Pregunta "¿Cuándo llegó el tren?" en el chat | Responde: "El modelo de lenguaje no está disponible. Verificá que Ollama esté corriendo." Log: `turn_llm_unavailable` |
| Tool MCP directa (`python -m mcp_server` por stdio) | `ferrocarril 1900` devuelve `debates_origen_01`. `Dabbene` con pregunta "¿Quién es Lorenzo Dabbene?" devuelve `AVISO: «Lorenzo Dabbene» no aparece…` y luego el doc 1903 (Valter Dabbene). `xyzzy` devuelve AVISO más el índice |
| `curl 127.0.0.1:11434/api/tags` | Sin respuesta. Ollama apagado |
| Evals (`python -m evals.eval_agent --reps 1`) | No ejecutados en la auditoría. Después: ver sección 11 |
| Captura de pantalla del navegador | Falló por timeout de render. La verificación del scroll fue por DOM |
| `git status` | Aparece `M .gitignore` que no toqué. Revisar antes de commitear |

Notas: el `ws_disconnected` que aparece al cargar la página viene del `StrictMode` de React en desarrollo (`frontend/src/main.jsx:7`), que monta dos veces. Los servidores de preview se detuvieron al terminar.

## 3. Parte A: Taller MCP 2.2

Estados: **C** Cumple, **E** Equivalente (desvío justificado en `CLAUDE.md`), **P** Parcial, **F** Falta, **SV** Sin verificar.

### A1. Arquitectura y flujo de un mensaje

| # | Requisito | Estado | Evidencia | Nota |
|---|---|---|---|---|
| 1 | Cuatro capas: React, FastAPI, Ollama, MCP | C | `frontend/src/App.jsx`, `backend/main.py:45-123`, `backend/llm/ollama.py`, `backend/mcp_server.py` | |
| 2 | Frontend pide `/api/fundacion` al montar | C | `frontend/src/App.jsx:86-94` | |
| 3 | `/api/fundacion` devuelve `raw` y `full_text`; 404 si falta el archivo | E | `backend/api/rest.py:23-25`; `backend/main.py:47-50` | No hay 404: el backend no arranca (fail-fast). Justificado en `CLAUDE.md` |
| 4 | Chat por WebSocket `/ws/chat` | C | `backend/api/ws.py:167` | |
| 5 | Tools MCP convertidas a formato Ollama | C | `backend/llm/ollama.py:104`; `backend/tools/registry.py:29` | `ToolSpec.parameters` toma `inputSchema` |
| 6 | Agente envía contexto y tools al modelo | C | `backend/agents/historian.py:107-113` | |
| 7 | Tool ejecutada por stdio | C | `backend/tools/registry.py:80-98`; `backend/main.py:70-82` | |
| 8 | Límite de 5 iteraciones | C | `backend/config.py:47` (`le=5`); `historian.py:110,135-136`; `ws.py:155-156` (evento `max_iterations`) | Verificado por código, no en vivo |
| 9 | Estados "Pensando..." y "Consultando base histórica..." | E | `backend/api/ws.py:126-127` manda `thinking`/`tool_call`. Los textos están en `frontend/src/components/ChatDrawer.jsx:7-9` | El texto lo arma el frontend |
| 10 | Respuesta final `response`, errores `error` | C | `backend/api/ws.py:78-92`, `137-164` | |
| 11 | Fallback para tool calls escritas como JSON | C | `backend/llm/ollama.py:110`, `202` (`_parse_text_tool_call`) | |
| 12 | Contexto conversacional entre preguntas | E | `backend/agents/historian.py:42-61` (pares pregunta/respuesta, ventana de 6 turnos) | Los resultados de tools no se guardan. Justificado en `CLAUDE.md` |

### A2. Stack tecnológico

| Tecnología | Declarada en | Estado | Nota |
|---|---|---|---|
| Python | `.venv/` (raíz) | C | |
| FastAPI 0.141.1 | `backend/requirements.txt:1` | C | `main.py:14` |
| Uvicorn 0.53.0 | `requirements.txt:2` | C | `main.py:155` |
| Pydantic 2.13.5 | `requirements.txt:5` | C | Modelos de contrato en `llm/provider.py`, `api/ws.py` |
| MCP SDK 2.2.0 | `requirements.txt:4` | C | `MCPServer` en `mcp_server.py:12` |
| Ollama + `llama3.2` | `config.py:25` (default); `.env` | C | La UI muestra "Local · llama3.2:3b" |
| Requests | no está | E | Reemplazado por `httpx==0.28.1` (`requirements.txt:3`) para soportar async |
| python-multipart | no está | E | No hay formularios ni uploads |
| React 19.2.8 | `frontend/package.json` | C | |
| Vite 8.3 | `frontend/package.json` | C | `vite.config.js` |
| Axios | no está | E | `fetch` nativo: `services/api.js:3,16` |
| Tailwind CSS 4.3.3 | `package.json` | E | Plugin `@tailwindcss/vite` (`vite.config.js:1,7`). Sin `tailwind.config.js` |
| PostCSS y Autoprefixer | no están | E | Tailwind 4 incluye ambos |
| Lucide React 1.47 | `package.json` | C | `ChatDrawer.jsx:1`, `App.jsx:1` |
| WebSocket API | navegador | C | `services/ws.js`, `hooks/useWebSocket.js` |

### A3. Backend, paso por paso

| # | Requisito | Estado | Evidencia | Nota |
|---|---|---|---|---|
| 1 | `backend/` con venv y `requirements.txt` | C | `backend/requirements.txt` | Tiene `mcp`, `fastapi`, `uvicorn`, `pydantic` |
| 2 | `fundacion.json` con `metadata.criterio` | E | `fundacion.json` (3 docs); `store/history.py:14-26` | Los campos son `criterio_historiografico`, `fecha_clave`, `fuente` |
| 3a | Tool `consultar_fundacion_las_varillas(tema)` | C | `backend/mcp_server.py:67-75` | |
| 3b | Busca por ID exacto y por palabra clave | C | `store/history.py:145-168` | Pesos: tags 3, título 2, contenido 1 |
| 3c | Mensaje claro si no hay resultados | C | `mcp_server.py:98-99` | Devuelve el índice |
| 3d | Archivo inexistente sin romperse | E | `mcp_server.py:108-112` (`exit(1)`) | Fail-fast, justificado |
| 3e | Cada documento incluye título, criterio y contenido | C | `store/history.py:206-215` | También incluye fuente y fecha |
| 3f | Corre como script `python -m mcp_server` | C | `mcp_server.py:120-121` | Probado directo por stdio |
| 4a | `lifespan` conecta y desconecta | C | `main.py:45-123` | |
| 4b | Lista tools al arrancar | C | Log `mcp_connected` con `tools` | Verificado en logs |
| 4c | Índice inyectado en system prompt | C | `backend/agents/prompt.py:40`; `main.py:99` | |
| 4d | System prompt obliga a usar la tool | C | `agents/prompt.py:10-17` (reglas 1 y 6) | Solo verificable en vivo (A6.3) |
| 4e | Middleware CORS | C | `main.py:136` | Orígenes explícitos. Solo GET. Sin `*` |
| 4f | Logging con nivel INFO | E | `config.py:18` (default `INFO`); `logging_config.py` | Formato JSON, no texto plano |
| 4g | Confirmación al arrancar "MCP Conectado y Listo" | E | Logs `mcp_connected` y "Application startup complete" | El mensaje es otro. Lo verificamos en logs |
| 4h | Se lanza con `python main.py` en 8000 | E | `main.py:155-161`; `config.py:16-17` | Escucha en `127.0.0.1`, no en `0.0.0.0` |
| 5 | Maneja `WebSocketDisconnect` y errores | C | `ws.py:193-218`; `ws.py:160-162` | Los errores se envían al cliente |

### A4. Frontend, paso por paso

| # | Requisito | Estado | Evidencia | Nota |
|---|---|---|---|---|
| 1 | Proyecto Vite + React en `frontend/` | C | `frontend/package.json` | |
| 2 | `axios` y `lucide-react` usados | E | `lucide-react`: C. `axios`: reemplazado por `fetch` | |
| 3 | Tailwind escanea el código; fuentes Inter y Outfit | E | `index.css:4-7` define fuentes del sistema (`--font-sans`, `--font-display`) | Tailwind 4 detecta clases solo. Sin Inter ni Outfit |
| 4 | `index.css`: fondo `#0f172a`, gradientes, `.glass`, scrollbar | E | `index.css:14-31`: `bg-slate-900` (= `#0f172a`), gradientes radiales, `@utility glass` con blur 12px, `thin-scrollbar` | Sin Google Fonts (justificado) |
| 5a | Pide `/api/fundacion` al montar | C | `App.jsx:86-94` | |
| 5b | Reintenta el WebSocket a los 3 s | E | `services/ws.js:21-28` (backoff exponencial con jitter, 0.5 s a 30 s); `hooks/useWebSocket.js:46` | Mejora sobre 3 s fijos. Justificado |
| 5c | Mensaje de bienvenida | C | `App.jsx:14-16` | |
| 5d | Sidebar con scroll suave al documento | C | `App.jsx:124-131` (`scrollIntoView`, respeta `prefers-reduced-motion`) | Verificado en navegador |
| 5e | Botón para mostrar u ocultar sidebar | C | `App.jsx:152-160` | |
| 5f | Cabecera "Las Varillas Digital" y botón "Consultar agente" | C | `App.jsx:162-175` | Mayúscula distinta en "agente" |
| 5g | Lector con `id` como ancla y `scroll-mt` | C | `components/Reader.jsx:23` (`scroll-mt-8`) | |
| 5h | Título del debate y pie con año | C | `Reader.jsx:7`, `42` | Verificado el texto |
| 5i | Drawer con "Asistente Varillas", en línea, cerrar | C | `ChatDrawer.jsx:198`; "EN LÍNEA" y "Cerrar chat" en el DOM | |
| 5j | Burbujas distintas para usuario y asistente | C | `ChatDrawer.jsx:101-121` | También hay burbuja de error |
| 5k | Spinner `Loader2` con el estado | C | `ChatDrawer.jsx:224-227` | |
| 5l | Enter envía, Shift+Enter nueva línea | C | `ChatDrawer.jsx:242` | Enter envió el mensaje en el navegador |
| 5m | Enviar deshabilitado si carga o está vacío | C | `ChatDrawer.jsx:172` (`canSend`) | |
| 5n | Aviso si el servidor no está conectado | C | `App.jsx:112-122` (`offline`); reducer en `App.jsx:70-71` | |
| 5o | Backdrop con blur al abrir el chat | C | `ChatDrawer.jsx:182` (`bg-black/60 backdrop-blur-sm`) | |
| 5p | Autoscroll al último mensaje | C | `ChatDrawer.jsx:158` | |

### A5. Puesta en marcha

| # | Requisito | Estado | Evidencia |
|---|---|---|---|
| 1 | `.claude/launch.json` define backend y frontend | C | `.claude/launch.json` |
| 2 | `pytest` desde `backend/` | C | 118 passed |
| 3 | Lint y build sin errores | C | lint exit 0; build OK |
| 4 | Ollama corriendo y prueba en navegador | P | Ambos servidores levantan. Con Ollama, el agente responde por WebSocket (sección 10). Falta la captura visual del chat: el panel del navegador no se mostró |
| 5 | Evals con Ollama real | P | 17/18 con `llama3.2:3b`. Un fallo por el término «supuestamente» (regex prohibida). Ver sección 11 |

### A6. Entregables del estudiante

| # | Requisito | Estado | Evidencia |
|---|---|---|---|
| 1 | Consola muestra conexión al arrancar | E | Log `mcp_connected` y `Application startup complete`. Formato JSON |
| 2 | Clic en el índice hace scroll suave al documento exacto | C | Clic en "1904": el artículo queda a 32 px del tope y recibe el foco. Verificado por DOM |
| 3a | "¿Quién es Lorenzo Dabbene?" llama la tool y usa datos | C | Verificado con `llama3.2:3b`: llama la tool con "Lorenzo Dabbene", recibe el AVISO y responde con el documento de Valter Dabbene (fuente `debates_origen_02`) |
| 3b | "¿Cuándo llegó el tren?" llama la tool y usa datos | C | Verificado con `llama3.2:3b`: llama la tool con "ferrocarril 1900" y responde con la fecha del 24 de diciembre de 1900 (fuente `debates_origen_01`) |
| 3c | Repregunta conserva contexto | P | Verificado: un segundo turno en el mismo socket llama la tool y presenta las tres teorías con sus fuentes. El contexto entre turnos está cubierto por tests con `FakeLLM` (`tests/test_historian_agent.py`); la prueba en vivo no dependió de la respuesta anterior |

Lo que sí se vio en vivo: sin Ollama, el chat muestra un error claro en lugar de quedarse colgado. Con Ollama levantado, los casos de A6.3 también se vieron en vivo (sección 10).

## 4. Parte B: SOLID y clases abstractas

Gravedad: **alta**, **media**, **baja**.

### B1. SRP (responsabilidad única)

- **A favor:** cada módulo tiene una razón de cambio: `store/history.py` (datos), `llm/*` (proveedores), `tools/*` (tools), `agents/historian.py` (razonamiento), `api/*` (transporte), `main.py` (composición).
- **Violación media:** `tools/registry.py` (170 líneas) mezcla conexión, reintentos con backoff, chequeo de vida y llamadas a tools. **Resuelto** (sección 10): la supervisión está en `tools/mcp_supervisor.py`.
- **Violación baja:** `api/ws.py:_run_turn` tiene siete ramas `except` que traducen excepciones a eventos. Es transporte, así que se acepta.
- **Violación baja:** `main.py` define el parche de `openapi` y el texto de descripción del WebSocket. No es lógica de negocio.

### B2. OCP (abierto/cerrado)

- **A favor:** agregar una tool solo requiere declararla en `mcp_server.py`. `HistorianAgent` recibe `Mapping[str, LLMProvider]`, así que no tiene `if` por proveedor.
- **Violación media:** agregar un proveedor exige tocar cuatro lugares: `Literal["local", "cloud"]` en `api/ws.py:39`, el `Literal` de `Modelo.id` en `api/rest.py:29`, el diccionario de `main.py:103-106` y los íconos del selector en `ChatDrawer.jsx`. **Resuelto** (sección 10): `ProviderId` es ahora la única lista. Agregar un proveedor toca el enum, `main.py` y `frontend/src/config/providers.js`.

### B3. LSP (sustitución de Liskov)

- **A favor:** `OllamaClient`, `OpenAICompatClient` y `FakeLLM` tienen las mismas firmas que `LLMProvider` (`chat`, `chat_stream`, `health`). `McpToolRegistry` y `FakeTools` tienen las mismas firmas que `ToolRegistry` (`specs`, `call`).
- **Sin excepciones nuevas:** los errores de los proveedores son subclases de `LLMError`, y `ws.py` los trata por tipo.
- **Sin `NotImplementedError`:** todas las subclases implementan los métodos abstractos.

### B4. ISP (segregación de interfaces)

- **A favor:** `ToolRegistry` tiene solo dos métodos abstractos (`specs`, `call`). `LLMProvider` tiene dos abstractos (`chat`, `health`). `chat_stream`, `warm_up` y `aclose` son opcionales con implementación por defecto.
- **Aceptable:** `FakeLLM.health()` devuelve `None` sin hacer nada. Es un doble de prueba.

### B5. DIP (inversión de dependencias)

- **A favor:** `HistorianAgent` depende solo de `llm.provider` y `tools.base` (abstracciones). `main.py` es el único lugar que instancia clases concretas.
- **Excepción baja:** `api/ws.py` importa `agents.historian.HistorianAgent` (clase concreta) y `store.history.rendered_ids`. `api/rest.py` importa `HistoryStore`. `CLAUDE.md` lo documenta como diseño para leer el corpus sin MCP.
- **Tests con fakes:** `FakeLLM` y `FakeTools` en `tests/conftest.py` reemplazan los servicios reales. Confirma que la dependencia está invertida.

### B6. Clases abstractas y tipado

- **Verificado:** instanciar `LLMProvider()` y `ToolRegistry()` lanza `TypeError`.
- **Sin propiedades abstractas:** no hay `@property` + `@abstractmethod`. No hace falta.
- **`Protocol` ya usado:** `StatusCallback` en `agents/historian.py:17-19`.
- **Protocol no conviene en los contratos:** `LLMProvider` y `ToolRegistry` tienen implementaciones por defecto. Con `Protocol` no las heredarían.
- **mypy:** `Success: no issues found in 30 source files` con `backend/mypy.ini`.
- **Linter:** `ruff` reportaba 12 `I001` (imports sin ordenar); corregidos con `--fix`. `pylint` y `flake8` no están instalados.

### B7. Pragmatismo

- **Abstracciones justificadas:** `LLMProvider` tiene tres implementaciones (Ollama, Groq y fake). `ToolRegistry` tiene dos (MCP y fake).
- **Complejidad a explicar:** `store/history.py` tiene búsqueda con tolerancia a un typo (Levenshtein ≤ 1), listas de stopwords y detección de nombres propios. Es mucho para un corpus de 3 documentos. Se justifica por el modelo de 3B, pero conviene tenerlo listo para la pregunta.
- **Decisiones documentadas:** `CLAUDE.md` explica cada desvío. Los docstrings también.

## 5. Desvíos documentados (no son faltantes)

Los desvíos sin justificación no aparecieron. Todos los de la lista del prompt están en `CLAUDE.md`: MCP con `MCPServer`, sin modo índice, `httpx`, CORS explícito, `127.0.0.1`, pares en `Conversation`, proveedor por mensaje, streaming, configuración por `.env`, fail-fast, logs JSON, sin `python-multipart`, y el frontend con `fetch`, Tailwind 4, fuentes del sistema, backoff y `thin-scrollbar`.

## 6. Faltantes priorizados

Estado después de la refactorización del 2026-10-09 (detalle en la sección 10). Se aplicó todo lo que esta lista pedía.

1. **Verificar el agente en vivo (A6.3).** Resuelto con `llama3.2:3b` local. Queda sin probar el proveedor Nube: enviaría la pregunta a Groq y requiere autorización.
2. **Ruff `I001`.** Resuelto con `ruff check backend --fix`.
3. **Lista de proveedores repetida (OCP).** Resuelto: `ProviderId` en `backend/llm/catalog.py` y `PROVIDERS` en `frontend/src/config/providers.js`.
4. **Separar supervisión MCP de llamadas (SRP).** Resuelto: `backend/tools/mcp_supervisor.py` (`McpSupervisor`) y `backend/tools/registry.py` (`McpToolRegistry`). `test_mcp_registry.py` sigue pasando con las mismas aserciones.
5. **Imports concretos en `api/` (DIP).** No se cambió. Es una decisión documentada en `CLAUDE.md`: con un solo consumidor, un `Protocol` no quitaría el acoplamiento a las excepciones del agente.

## 7. Para exponer (resumen por bloque)

- **Datos y MCP:** `fundacion.json` tiene tres documentos sobre el año de fundación (1900, 1903, 1904). `HistoryStore` los valida con Pydantic y busca por tokens. `mcp_server.py` expone una sola tool por stdio. Pregunta típica: "¿Por qué stdio?" Respuesta: el backend lanza el servidor como subproceso y no necesita red.
- **Contratos abstractos:** `LLMProvider` y `ToolRegistry` son ABC. Demo: `LLMProvider()` lanza `TypeError`. Pregunta típica: "¿Por qué no Protocol?" Respuesta: los contratos tienen implementaciones por defecto.
- **Agente:** `HistorianAgent.run` alterna modelo y tools hasta 5 veces. Nunca consulta al modelo sin tools. Pregunta típica: "¿Qué pasa si el modelo inventa?" Respuesta: el prompt obliga a usar la tool, y el aviso de nombres faltantes viene del backend, no del modelo.
- **API:** `api/ws.py` valida el origen, limita conexiones y mensajes, y traduce excepciones a eventos. Pregunta típica: "¿Por qué no CORS?" Respuesta: Starlette no aplica CORS a WebSocket, así que se valida `Origin` a mano.
- **Composición:** `main.py` es el único lugar donde se crean los objetos. Pregunta típica: "¿Dónde se cambia el modelo?" Respuesta: en `.env` y en el selector del chat.
- **Frontend:** `state/chatReducer.js` tiene el reducer de chat (con pruebas). `services/ws.js` reconecta con backoff y jitter. Pregunta típica: "¿Por qué no Axios?" Respuesta: son dos GET simples y `fetch` alcanza.

## 8. Guion de exposición (unos 15 minutos)

| Tiempo | Tema | Mostrar | Idea principal |
|---|---|---|---|
| 0:00 a 2:00 | Problema | La página principal | Un chat que responde solo con documentos, sin inventar |
| 2:00 a 4:00 | Datos y MCP | `fundacion.json`, `mcp_server.py` y la demo de tool directa | El modelo no conoce la historia, la consulta por tool |
| 4:00 a 7:00 | Contratos abstractos | `llm/provider.py`, `tools/base.py`, demo del `TypeError` | Depender de abstracciones permite cambiar de modelo |
| 7:00 a 9:00 | Agente | `agents/historian.py` (loop) y `agents/prompt.py` (reglas) | El loop alterna modelo y tools |
| 9:00 a 11:00 | API | `api/ws.py` (origen, límites, eventos) | Transporte separado de la lógica |
| 11:00 a 13:00 | Composición | `main.py` (lifespan) y los logs | Un solo lugar arma los objetos |
| 13:00 a 15:00 | Demo en vivo | Clic en el índice y pregunta "¿Cuándo llegó el tren?" | Requiere Ollama. Si no está, mostrar el error y el `AVISO` de "Lorenzo Dabbene" con la tool directa |

## 9. Glosario

- **MCP (Model Context Protocol):** protocolo estándar para que un modelo use herramientas externas.
- **Tool / tool call:** función que el modelo pide ejecutar; el resultado vuelve al modelo.
- **stdio:** comunicación por entrada y salida estándar entre procesos.
- **Lifespan:** código que corre al arrancar y apagar la aplicación FastAPI.
- **WebSocket:** conexión bidireccional persistente entre navegador y servidor.
- **System prompt:** instrucciones fijas que el modelo recibe antes de cada pregunta.
- **ABC (Abstract Base Class):** clase base que no se puede instanciar y obliga a implementar métodos.
- **Protocol:** contrato de tipos con chequeo estático, sin herencia explícita.
- **Inyección de dependencias:** recibir las dependencias por parámetro en vez de crearlas adentro.
- **Fail-fast:** detenerse al primer error de configuración en vez de seguir con datos inválidos.
- **CORS / CSWSH:** control de origen. CSWSH es el secuestro de WebSocket entre sitios.
- **Backoff y jitter:** esperar más en cada reintento, con un componente aleatorio para no sincronizar clientes.
- **Streaming:** envío del texto de la respuesta a medida que el modelo lo genera.
- **Pydantic:** validación de datos con tipos de Python.

## 10. Cambios aplicados después de la auditoría

Se aplicó la refactorización pedida: los puntos de SOLID con puntaje más bajo (R1 a R3) y los hallazgos de prioridad baja. No se borró ninguna prueba existente. Se agregaron 18 pruebas de backend y 17 de frontend.

| Hallazgo | Estado | Cambio | Archivos |
|---|---|---|---|
| H1 Lista de proveedores repetida | Resuelto | `ProviderId` (StrEnum) y `catalogo_proveedores`. `/api/modelos` sale de `app.state.proveedores`. El frontend tiene un solo mapa de presentación | `backend/llm/catalog.py`, `backend/api/rest.py`, `backend/api/ws.py`, `backend/main.py`, `frontend/src/config/providers.js` |
| H2 `McpToolRegistry` con varias responsabilidades | Resuelto | `McpSupervisor` (conexión, backoff, cierre) y `McpToolRegistry` (descubrimiento y llamadas). Se mantiene la regla de anyio: la sesión se abre y se cierra en la tarea supervisora | `backend/tools/mcp_supervisor.py`, `backend/tools/registry.py` |
| H3 `App.jsx` con reducer y navegación | Resuelto | `chatReducer` en `state/chatReducer.js`; navegación en `hooks/useDocNavigation.js`. `App` queda como contenedor, con la carga de datos | `frontend/src/state/chatReducer.js`, `frontend/src/hooks/useDocNavigation.js`, `frontend/src/App.jsx` |
| H4 `AnswerText` dentro del drawer | Resuelto | Parser en `lib/markdown.js` (sin React, con pruebas) y componente en `components/AnswerText.jsx` | `frontend/src/lib/markdown.js`, `frontend/src/components/AnswerText.jsx` |
| H5 Formato para el modelo en `store/` | Resuelto | `render_index`, `render_documents` y `rendered_ids` pasan a `store/render.py` | `backend/store/render.py`, `backend/store/history.py` |
| H6 Marcador AVISO sin constante | Resuelto | `AVISO_PREFIJO` en `mcp_meta.py`, usado por la tool y por la regla 5 del prompt. Una prueba lo verifica | `backend/mcp_meta.py`, `backend/mcp_server.py`, `backend/agents/prompt.py`, `backend/tests/test_prompt.py` |
| H7 Cadena de siete `except` | Parcial | Se conserva la cadena: cada rama registra un log distinto. Una prueba fija el mapeo y el orden (`LLMUnavailable` antes que `LLMError`) | `backend/tests/test_ws.py` |
| H8 Conversión de tool calls duplicada | Parcial | `tool_call_from_wire` compartido. Los `_errors()` de cada proveedor siguen separados porque sus mensajes son distintos | `backend/llm/wire.py`, `backend/tests/test_wire.py` |
| H9 Transporte con clases concretas | No aplicado | Un `Protocol` no quitaría el import de las excepciones del agente. `CLAUDE.md` documenta la decisión | — |
| H10 `health()` de OpenAI-compatible | Resuelto | El contrato dice que `health` puede limitarse a validar configuración, y la implementación lo documenta | `backend/llm/provider.py`, `backend/llm/openai_compat.py` |
| H11 `ChatDrawer` con 16 props | Resuelto | Props agrupadas en `chat` (estado) y `actions` (callbacks) | `frontend/src/components/ChatDrawer.jsx`, `frontend/src/App.jsx` |
| H12 Constante importada del transporte | Resuelto | `MAX_TEXT_CHARS` y `MOBILE_QUERY` en `frontend/src/constants.js` | `frontend/src/constants.js`, `frontend/src/services/ws.js` |
| H13 Frontend sin pruebas | Resuelto | `node --test`, sin dependencias nuevas: 12 pruebas del reducer y 5 del parser. Script `npm --prefix frontend test` | `frontend/src/state/chatReducer.test.js`, `frontend/src/lib/markdown.test.js`, `frontend/package.json` |
| Ruff `I001` | Resuelto | `ruff check backend --fix`: 17 avisos (12 `I001` y 5 imports sin uso que quedaron por la refactorización) | `backend/` |

`CLAUDE.md` se actualizó donde cambiaron las ubicaciones: supervisor, catálogo, `store/render.py` y el comando de test del frontend.

## 11. Verificación después de la refactorización

| Comando o prueba | Resultado |
|---|---|
| `pytest` (desde `backend/`) | 136 passed |
| `ruff check backend` | All checks passed |
| `mypy .` (`backend/mypy.ini`) | Success, 37 archivos |
| `npm --prefix frontend test` | 17 pass, 0 fail |
| `npm --prefix frontend run lint` | exit 0 |
| `npm --prefix frontend run build` | OK. JS 242 kB (76 kB gzip) |
| Backend en vivo (`preview_start backend`) | Arranca. Log `mcp_connected` con `consultar_fundacion_las_varillas`. `/api/modelos` devuelve `local` y `cloud` como disponibles. `/api/fundacion` devuelve 3 documentos |
| A6.3 en vivo con `llama3.2:3b` | Tabla A6, casos 3a, 3b y 3c |
| `python -m evals.eval_agent --reps 1` | 17/18 OK con `llama3.2:3b`, temperatura 0.1. Único fallo: «Contame la historia de Las Varillas», donde la respuesta usó «supuestamente», término que la regex del escenario prohíbe. El prompt no cambió. No se comparó contra la línea base previa a la refactorización: con una sola repetición no se mide la variación del modelo |
| Página en el navegador | Carga el drawer y el selector con dos modelos. Sin errores de JavaScript. Los errores `WebSocket connection failed` de la consola vienen del `StrictMode` de React en desarrollo: abre dos sockets por carga, y el backend registra dos `ws_connected` |

**Pendiente:**
- Proveedor Nube (Groq) en vivo: requiere autorización, porque envía la pregunta a Groq.
- Captura visual del chat con las respuestas renderizadas: el panel del navegador no se mostró. El render de `AnswerText` está cubierto por pruebas del parser y por el build, no por una captura.
- Refactorización commiteada en `ad09251`; auditoría rehecha en `f9e3b3b`.

## 12. Comentarios SOLID en el código (rama `solid-comentarios`)

Para la exposición, cada lugar donde se aplica un principio lleva un comentario con el marcador `SOLID-S`, `SOLID-O`, `SOLID-L`, `SOLID-I` o `SOLID-D`. Para listarlos: `git grep -n "SOLID-"`.

- Un commit por archivo y principio: 48 commits (S 23, O 10, L 6, I 2, D 7). Cada mensaje dice qué principio se aplica, qué dice el principio y el comentario agregado.
- Solo comentarios: 102 líneas agregadas, 0 borradas, 34 archivos. En cada commit de Python el AST queda igual.
- Verificación: `pytest` 136, `mypy`, `ruff`, `npm --prefix frontend test` 17, lint y build.
- Sin marcador, por estar parciales o no aplicados: H7 (cadena de `except`), H9 (transporte con clases concretas), el `switch` del reducer y `Bubble` (OCP parcial).
- Precisión sobre B5: `main.py` es la raíz de composición del backend, pero no el único lugar que instancia clases concretas: `mcp_server.py` y `evals/eval_agent.py` también crean `HistoryStore`.
