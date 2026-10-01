# Informe de auditoría: historia.mcp frente al Taller MCP 2.2 y la guía SOLID

Fecha: 2026-10-01. Alcance: `backend/` y `frontend/`. El código legacy de la raíz no se evaluó.

**Estado:** el informe se escribió en dos etapas. Los estados de las tablas son los de la **auditoría inicial**, salvo donde dice lo contrario. La sección "Correcciones aplicadas" (después del resumen) dice qué se arregló después y cómo quedó cada ítem. Los números de línea de las tablas corresponden al código auditado; tras las correcciones se movieron en `store/history.py`, `agents/historian.py`, `tools/registry.py`, `api/ws.py` y `llm/provider.py`.

## 1. Resumen

- Auditoría inicial: 110 ítems, **80 Cumple, 10 Equivalente, 14 Parcial, 2 Falta, 4 Sin verificar**. Después de las correcciones: 118 tests pasan, `ruff` y `mypy` sin avisos, lint y build sin errores.
- Corregido: pie con año dinámico, aviso falso por «fecha», desvíos documentados, contrato de tools separado del SDK MCP, tipado y estilo. Sigue pendiente: lista de proveedores repetida en la API y el frontend, y la verificación con `llama3.2` local.
- Riesgo principal para la clase: el modelo en la nube **una vez de dos no llamó a la tool** ("¿Quién es Lorenzo Dabbene?"). Se reescribió el prompt, pero **no se volvió a probar en vivo**. Ollama no estaba corriendo: el modelo local sigue sin verificar.

## Correcciones aplicadas

| # | Problema | Qué se hizo | Estado |
|---|---|---|---|
| 1 | Aviso falso «No hay registros de «fecha»» | `fecha fechas ano anos` en `_GENERIC_TERMS` (`store/history.py`) y test parametrizado en `tests/test_history_store.py` | Corregido, con test |
| 2 | La nube a veces no llama a la tool | Reglas 1 y 6 de `agents/prompt.py` reescritas: ante un nombre propio, una fecha o un lugar se llama primero a la herramienta | **Mitigado, no verificado en vivo.** `tool_choice="required"` no se aplicó: cambiaría el contrato de `LLMProvider` |
| 3 | Pie sin año dinámico | `<footer>` con `new Date().getFullYear()` en `Reader.jsx` | Corregido. El último artículo conserva su `min-h`, así que queda un hueco antes del pie |
| 4 | Sin 404 en `/api/fundacion` | Documentado como fail-fast en `CLAUDE.md` | Documentado (decisión de diseño) |
| 5 | Desvíos de frontend sin justificar | Párrafos en `CLAUDE.md`: `fetch`, Tailwind 4, fuentes del sistema, backoff, `thin-scrollbar`. Fondo cambiado a `bg-slate-900` | Corregido |
| 6 | Lista de proveedores repetida (OCP) | `LLMUnavailable` tiene `public`: cada proveedor decide si su mensaje se muestra tal cual. `ws.py` ya no pregunta `provider == "local"` | **Parcial.** Siguen repetidos `Literal["local","cloud"]` en `ws.py` y `rest.py`, y el mapa de `ChatDrawer.jsx` |
| 7 | Contrato de tools en el módulo del SDK (DIP) | Nuevo `tools/base.py` con `ToolRegistry`, `ToolError` y `ToolsUnavailable`; `historian.py`, `ws.py`, `main.py`, evals y tests importan de ahí | Corregido |
| 8 | Servidor MCP sin datos sale con `exit(1)` | Documentado en `CLAUDE.md` | Documentado |
| 9 | `FakeTools.call` lanzaba `KeyError` | Lanza `ToolError` | Corregido |
| 10 | Sin `mypy` ni `ruff` | Agregados a `requirements-dev.txt` (`mypy==2.3.1`, `ruff==0.16.9`) y `backend/mypy.ini` con plugin de pydantic. `StatusCallback` es un `Protocol` y `_detail` tiene tipo completo | Corregido: `mypy` 0 errores en 30 archivos, `ruff` 0 avisos |
| 11 | `python-multipart` | Documentado en `CLAUDE.md`: no hay formularios | Documentado |
| 12 | Verificar `llama3.2` local | — | **Pendiente**: hay que levantar `ollama serve` |

## 2. Panorama general para exponer

```
 Navegador (React + Vite :5173)
   │  GET /api/fundacion  ──────────────────────────────┐
   │  WS  /ws/chat  {"text", "provider"}                │ (proxy de Vite)
   ▼                                                    ▼
 api/ws.py  (valida Origin, límites, traduce errores)   api/rest.py ──► HistoryStore (lee directo)
   │  agent.run(conversation, text, on_status, on_delta)
   ▼
 agents/historian.py  HistorianAgent  ── bucle de hasta 5 iteraciones
   │                         │
   │ chat / chat_stream      │ tools.call(name, args, user_question)
   ▼                         ▼
 llm/provider.py (ABC)     tools/registry.py (ABC) ── McpToolRegistry
   ├─ OllamaClient  ──► Ollama :11434 (llama3.2)          │  stdio (JSON-RPC por stdin/stdout)
   └─ OpenAICompatClient ──► Groq /chat/completions       ▼
                                                     mcp_server.py (subproceso)
                                                          │
                                                          ▼
                                                     store/history.py ──► fundacion.json
 ◄── eventos: status(thinking/tool_call) · delta · response(+sources) · error
```

**Datos (`fundacion.json`, `store/history.py`).** Tres documentos con el debate sobre el año de fundación (1900, 1903, 1904). `HistoryStore` los valida con Pydantic al arrancar y ofrece una búsqueda por palabras: sin acentos, sin palabras vacías y tolerante a un error de tipeo. No sabe nada de MCP, de LLM ni de HTTP.

**Servidor MCP (`mcp_server.py`).** MCP (Model Context Protocol) es un protocolo estándar para que un programa ofrezca "herramientas" a un modelo de lenguaje. Este servidor corre como proceso hijo y habla por **stdio**: los mensajes JSON-RPC viajan por la entrada y la salida estándar del proceso. Expone una sola herramienta, `consultar_fundacion_las_varillas(tema)`.

**Contratos abstractos (`llm/provider.py`, `tools/registry.py`).** Son clases abstractas (ABC, *Abstract Base Class*): definen qué métodos debe tener un proveedor de LLM o un registro de herramientas, sin decir cómo. El agente solo conoce estos contratos.

**Proveedores concretos (`llm/ollama.py`, `llm/openai_compat.py`).** Traducen el contrato al formato de cada servicio: Ollama local o Groq en la nube. Usan `httpx` asíncrono, así que nunca bloquean el *event loop* (el bucle que atiende todas las conexiones en un solo hilo).

**Agente (`agents/historian.py`).** Hace el razonamiento: manda la conversación y la lista de herramientas al modelo. Si el modelo pide una herramienta (*tool call*), la ejecuta y le devuelve el resultado. Repite hasta tener una respuesta final, con un tope de 5 vueltas.

**API (`api/rest.py`, `api/ws.py`).** REST sirve el corpus para el lector. El WebSocket (canal bidireccional y persistente sobre HTTP) recibe preguntas y emite eventos de estado, pedazos de texto y la respuesta final. Esta capa solo transporta y traduce errores.

**Composición (`main.py`).** En el `lifespan` (función que FastAPI corre al arrancar y al apagar) crea todos los objetos concretos y los conecta. Es la raíz de composición: el único lugar que conoce las clases concretas.

**Frontend (`frontend/src`).** React con Tailwind. Tiene un índice lateral, un lector central con los documentos y un panel de chat que se conecta por WebSocket y se reconecta solo.

---

## 3. Parte A: Taller MCP 2.2

### A1. Arquitectura y flujo de un mensaje

| # | Requisito | Estado | Evidencia | Nota |
|---|---|---|---|---|
| 1 | Cuatro capas | Cumple | `frontend/`, `backend/main.py:134`, `llm/ollama.py:31`, `mcp_server.py:57` | Agrega una quinta opcional: Groq. |
| 2 | Frontend pide `/api/fundacion` al montar | Cumple | `frontend/src/App.jsx:86-94`, `services/api.js:2-12`; log `GET /api/fundacion 200` | |
| 3 | `raw` + `full_text` (`## titulo\ncontenido`); 404 sin archivo | Equivalente | `api/rest.py:14-25`, `store/history.py:129`; navegador: 3 docs, `full_text` empieza con `## Teoría de Fundación 1900…` | Sin archivo no hay 404: el `lifespan` lanza `HistoryStoreError` y el backend no arranca (`main.py:45-49`). Fail-fast, ahora documentado en `CLAUDE.md`. |
| 4 | Chat por WebSocket `/ws/chat` | Cumple | `api/ws.py:166`, `services/ws.js:6-9` | |
| 5 | Tools MCP a formato Ollama | Cumple | `tools/registry.py:29` (`input_schema` a `parameters`), `llm/ollama.py:103-104` (`{"type": "function", "function": …}`) | |
| 6 | Contexto + tools al modelo | Cumple | `agents/historian.py:102-108` | |
| 7 | Ejecuta la tool por stdio y reitera | Cumple | `main.py:69-76` (`StdioServerParameters`), `historian.py:117-129`; log `tool_call` + `tool_search` | |
| 8 | Límite de 5 iteraciones | Cumple | `historian.py:105`, `config.py:47` (`le=5`). Al llegar al límite lanza `MaxIterationsExceeded` (`historian.py:130-131`) y el WS manda `error` `max_iterations`: "No llegué a una respuesta final. Probá reformular la pregunta." (`ws.py:154-155`). Test `test_tope_de_iteraciones` | |
| 9 | Estados parciales | Cumple | Backend: `status` con `state` = `thinking` / `tool_call` (`historian.py:106,119`). Textos: "Enviando…", "Pensando…", "Consultando base histórica…" + el tema entre «» (`ChatDrawer.jsx:6-10,222-228`) | El texto lo pone el frontend; el backend manda códigos. |
| 10 | `response` y `error` | Cumple | `ws.py:72-87,134-162`; navegador: error "El modelo de lenguaje no está disponible. Verificá que Ollama esté corriendo." | |
| 11 | Fallback de tool call escrita como JSON | Cumple | `llm/ollama.py:202-225`; retención del stream en `ollama.py:87-89` | |
| 12 | Contexto entre preguntas | Cumple | `historian.py:37-56`; navegador: "¿Y quién defiende esa fecha?" se resolvió a 1900 | Guarda pares (pregunta, respuesta). Desvío documentado. |

**Para exponer**

1. **Qué hace.** Un mensaje sale del navegador por WebSocket, el agente le pregunta al modelo y el modelo decide si necesita buscar. Si busca, el backend llama al servidor MCP, le pasa el resultado al modelo y repite. Cuando el modelo contesta sin pedir herramientas, esa es la respuesta final.
2. **Dónde está.** `agents/historian.py:84-131` (`HistorianAgent.run`), `api/ws.py:117-163` (`_run_turn`).
3. **Fragmento clave** (`backend/agents/historian.py:105-122`):

```python
        for iteration in range(1, self._max_iterations + 1):
            await on_status("thinking", None)
            messages = conversation.with_pending(pending)
            response = await (llm.chat(messages, specs) if on_delta is None else llm.chat_stream(messages, specs, on_delta))
            if not response.tool_calls:
                answer = response.content.strip()
                if not answer:
                    logger.warning("empty_answer", extra={"iteration": iteration})
                    return EMPTY_ANSWER
                conversation.commit(question, Message(role="assistant", content=answer))
                logger.info("agent_answer", extra={"iteration": iteration, "chars": len(answer), "provider": provider})
                return answer
            pending.append(Message(role="assistant", content=response.content, tool_calls=response.tool_calls))
            for call in response.tool_calls:
                await on_status("tool_call", call.name, detail=_detail(call.arguments))
```

   - Línea 1: el tope de vueltas sale de la configuración (máximo 5).
   - Línea 2: `on_status` es un *callback*: el agente avisa "estoy pensando" sin saber que del otro lado hay un WebSocket.
   - Línea 4: con `on_delta` usa streaming; sin él (tests, evals) usa `chat` normal.
   - Líneas 5-12: sin tool calls, la respuesta es final. Solo ahí se guarda el turno en la conversación.
   - Línea 13: si pidió herramientas, el pedido del modelo queda en `pending` para la próxima vuelta.
4. **Por qué así.** El bucle no sabe de transporte ni de proveedor, así que lo usan igual el WebSocket, los tests y las evals. Se guardan solo los pares (pregunta, respuesta final): los resultados de tools son la mayoría de los tokens. Si se guardaran, el system prompt terminaría fuera de la ventana de contexto (`num_ctx`) del modelo de 3B.
5. **Conexión con la teoría.** Es el "bucle de razonamiento" del plan (pasos 6 a 8 del flujo) y es el patrón *ReAct*: razonar, actuar y observar.
6. **Preguntas probables.**
   - *¿Qué pasa si el modelo pide herramientas para siempre?* A la quinta vuelta se corta y el usuario recibe un error claro.
   - *¿Quién decide si se busca?* El modelo. El prompt le ordena buscar siempre (regla 1), pero en la auditoría el modelo en la nube una vez no lo hizo. Se reescribió el prompt; ver sección 5.
   - *¿Cómo recuerda la pregunta anterior?* `Conversation` guarda los últimos 6 pares por conexión.

### A2. Stack tecnológico

| # | Tecnología | Estado | Declarada | Usada | Nota |
|---|---|---|---|---|---|
| 1 | Python | Cumple | `.venv/` (raíz) | todo `backend/` | |
| 2 | FastAPI | Cumple | `requirements.txt` (0.141.1) | `main.py:134` | |
| 3 | Uvicorn | Cumple | `uvicorn[standard]` 0.53.0 | `main.py:154` | |
| 4 | Pydantic | Cumple | 2.13.5 + `pydantic-settings` | `store/history.py:14-26`, `api/ws.py:48-87`, `config.py` | |
| 5 | MCP SDK | Cumple | `mcp==2.2.0` | `mcp_server.py:12`, `tools/registry.py:9` | |
| 6 | Ollama (`llama3.2`) | Cumple | `config.py:25`; `/api/modelos` informó `llama3.2:3b` desde `.env` | `llm/ollama.py` | No estaba corriendo. |
| 7 | Requests o reemplazo | Equivalente | `httpx==0.28.1` | `ollama.py:53`, `openai_compat.py:50` | Desvío conocido: cliente async. No hay llamadas bloqueantes en el event loop. Las lecturas de archivos son solo al arrancar (`main.py:46,98`) y `get_fundacion` es `def` sincrónico, así que FastAPI lo corre en un *threadpool*. |
| 8 | `python-multipart` | Equivalente | — | — | No hay formularios ni uploads: no hace falta. Documentado en `CLAUDE.md`. |
| 9 | React | Cumple | `package.json` (^19.2.8) | `main.jsx` | |
| 10 | Vite | Cumple | ^8.3.0 | `vite.config.js` | |
| 11 | Axios | Parcial | — | `fetch` nativo en `services/api.js:3,16` | Reemplazo válido (sin dependencia extra, con `AbortController`). Documentado en `CLAUDE.md`. |
| 12 | Tailwind CSS | Equivalente | `tailwindcss` + `@tailwindcss/vite` ^4.3.3 | `index.css:1`, `vite.config.js:9` | Tailwind 4: sin `tailwind.config.js`. |
| 13 | PostCSS | Equivalente | — | — | Tailwind 4 con el plugin de Vite no lo necesita. Documentado en `CLAUDE.md`. |
| 14 | Autoprefixer | Equivalente | — | — | Tailwind 4 agrega los prefijos con Lightning CSS. Documentado en `CLAUDE.md`. |
| 15 | Lucide React | Cumple | ^1.47.0 | `App.jsx:1`, `ChatDrawer.jsx:1`, `Sidebar.jsx:1` | |
| 16 | WebSocket del navegador | Cumple | — | `hooks/useWebSocket.js:25` | |

**Para exponer**

1. **Qué hace.** El backend es Python async: FastAPI + Uvicorn, Pydantic para validar y `httpx` para hablar con los modelos. El frontend es React con Vite y Tailwind 4.
2. **Dónde está.** `backend/requirements.txt`, `backend/requirements-dev.txt`, `frontend/package.json`, `frontend/vite.config.js`.
3. **Fragmento clave** (`backend/requirements.txt:1-6`):

```
fastapi==0.141.1
uvicorn[standard]==0.53.0
httpx==0.28.1
mcp==2.2.0
pydantic==2.13.5
pydantic-settings==2.15.0
```

   - Versiones fijas (`==`): el proyecto se instala igual en cualquier máquina.
   - `httpx` reemplaza a `requests` porque tiene cliente asíncrono.
   - `pydantic-settings` lee el `.env` y lo valida.
4. **Por qué así.** `requests` es sincrónico. Dentro de un handler async congelaría el servidor entero mientras Ollama genera, que tarda segundos. `httpx.AsyncClient` libera el event loop mientras espera. Tailwind 4 trae su propio plugin de Vite, así que sobran PostCSS y Autoprefixer.
5. **Conexión con la teoría.** Sección "Stack tecnológico" del plan.
6. **Preguntas probables.**
   - *¿Por qué no Axios?* `fetch` ya viene en el navegador y cubre dos GET simples.
   - *¿Por qué no `requests`?* Bloquea el event loop. Con un servidor async, un usuario esperando al modelo frenaría a todos los demás.

### A3. Backend, paso por paso

| # | Requisito | Estado | Evidencia | Nota |
|---|---|---|---|---|
| 1 | `backend/`, venv, requirements con mcp/fastapi/uvicorn/pydantic | Cumple | `backend/requirements.txt` | El venv está en la raíz (`.venv/`), según `CLAUDE.md`. |
| 2 | `fundacion.json` con `id`, `titulo`, `contenido`, `tags`, `metadata.criterio` | Cumple | `fundacion.json:8`; schema en `store/history.py:14-26` | El campo se llama `criterio_historiografico`. Suma `fecha_clave` y `fuente`. |
| 3a | Expone `consultar_fundacion_las_varillas(tema)` | Cumple | `mcp_server.py:60-68`; log `mcp_connected tools: [consultar_fundacion_las_varillas]` | |
| 3b | Busca por ID exacto y por palabra en título, contenido y tags | Cumple | `store/history.py:163-179` | Pesos tags=3, título=2, contenido=1 (`:62`). |
| 3c | Mensaje claro sin resultados | Cumple | `mcp_server.py:91-92` | Devuelve el índice como guía. |
| 3d | Archivo de datos inexistente | Equivalente | `mcp_server.py:101-105`, `store/history.py:133-137` | No hay traceback: hay log `critical` y `exit(1)`. Pero el servidor no sigue corriendo. El backend sí: responde `tools_unavailable` y reintenta. Documentado en `CLAUDE.md`. |
| 3e | Cada documento con título, criterio y contenido | Cumple | `store/history.py:217-226` | Suma fuente y fecha clave. |
| 3f | Corre como script | Cumple | `mcp_server.py:113-114`; se lanza con `-m mcp_server` (`main.py:72`) | |
| 3g | Sin `FastMCP` (desvío conocido) | Equivalente | `mcp_server.py:12,58-60` | Ojo: usa `MCPServer` con `@server.tool`. Es la API de alto nivel del SDK 2.x, la sucesora de FastMCP, no la de bajo nivel. Aclarado en `CLAUDE.md`. |
| 4a | `lifespan` conecta MCP al arrancar y cierra al apagar | Cumple | `main.py:43-122`: `tools.connect()` en `:94`, `tools.aclose()` en `:119` | |
| 4b | Lista tools al arrancar | Cumple | `tools/registry.py:157` (`_fetch_tools`), log en `:152` | |
| 4c | Índice en el system prompt | Cumple | `main.py:98`, `agents/prompt.py:40` | Desvío conocido: la tool no tiene "modo índice". |
| 4d | Prompt de historiador que obliga a usar la tool | Cumple | `agents/prompt.py:10-17` (regla 1), persona desde `ia_config/*.txt` | En la demo el modelo en la nube no la cumplió 1 de 2 veces. |
| 4e | Middleware CORS | Equivalente | `main.py:135`, `config.py:19,61-66` | Orígenes explícitos y rechazo de `*`. Desvío conocido. |
| 4f | Logging INFO | Cumple | `config.py:18`, `logging_config.py:31-47` | Formato JSON (documentado). |
| 4g | Confirmación "MCP Conectado y Listo" | Equivalente | log `{"msg": "mcp_connected", "tools": ["consultar_fundacion_las_varillas"]}` (`registry.py:152`) | El texto es el código JSON `mcp_connected`. Logs JSON documentados en `CLAUDE.md`. |
| 4h | `python main.py` en el puerto 8000 | Cumple | `main.py:153-160`, `config.py:16-17`; log "Uvicorn running on http://127.0.0.1:8000" | `127.0.0.1` y no `0.0.0.0`: desvío conocido. |
| 5 | `WebSocketDisconnect` y excepciones van al cliente | Cumple | `ws.py:209-216` (desconexión, cancela el turno), `ws.py:135-161` (cada excepción pasa a `ErrorEvent`) | Tests `test_criterio_6_*`, `test_mcp_caido_*` |

**Para exponer (servidor MCP)**

1. **Qué hace.** Es un programa aparte que el backend lanza como subproceso. Ofrece una sola herramienta que busca en los documentos y devuelve texto listo para que lo lea el modelo.
2. **Dónde está.** `backend/mcp_server.py:57-95` (`build_server`), `store/history.py:156-179` (`search`), `store/history.py:217-226` (`render_documents`).
3. **Fragmento clave** (`backend/mcp_server.py:60-74`):

```python
    @server.tool(structured_output=False)
    def consultar_fundacion_las_varillas(
        tema: Annotated[
            str,
            Field(max_length=200, description="Palabras clave concretas: nombres, fechas o lugares (ej: 'fundación', 'ferrocarril 1900')"),
        ],
        ctx: Context,
    ) -> str:
        """Busca documentos en la biblioteca histórica de Las Varillas (fundación, ferrocarril, historiadores, fechas)."""
        # Sin modo índice: el índice ya va en el system prompt. Con tema vacío el modelo recibía solo
        # títulos y respondía "no tengo información" aunque los documentos tenían la respuesta.
        if not tema.strip():
            logger.info("tool_empty_tema")
            return "Falta 'tema'. Volvé a llamar la herramienta con palabras clave concretas (ej: 'fundación', 'ferrocarril')."
        user_question = _user_question(ctx)
```

   - Línea 1: el decorador registra la función como tool MCP. El SDK arma el `inputSchema` a partir de los type hints.
   - Líneas 3-6: `Annotated` + `Field` agregan validación (máximo 200 caracteres) y la descripción que lee el modelo.
   - Línea 7: `ctx` no lo ve el modelo. Lo inyecta el SDK y trae el `_meta` de la llamada.
   - Línea 9: el docstring es la descripción de la tool.
   - Línea 15: la pregunta original del usuario llega por `_meta`, no por los argumentos.
4. **Por qué así.** stdout es el canal del protocolo, así que todos los logs van a stderr (`mcp_server.py:100`). La pregunta original viaja por `_meta` para detectar nombres que el modelo recortó ("Lorenzo Dabbene" buscado como "Dabbene"), y la tool agrega un AVISO para que el modelo no le atribuya el documento a otra persona.
5. **Conexión con la teoría.** Sección "Servidor MCP" del plan. SRP: el servidor solo traduce entre MCP y `HistoryStore`.
6. **Preguntas probables.**
   - *¿Por qué stdio y no HTTP?* El servidor es local y lo lanza el backend: no abre puertos y muere con el padre.
   - *¿Cómo sabe el backend qué tools hay?* Pide `tools/list` al conectar: agregar una tool no toca `main.py`.
   - *¿Qué pasa si el subproceso muere?* El próximo mensaje lo detecta con `tools/list` (timeout de 3 s) y reconecta con backoff exponencial (`registry.py:86-96,133-152`).

**Para exponer (`main.py` y `lifespan`)**

1. **Qué hace.** Al arrancar, carga los datos, crea los clientes de Ollama y de Groq, lanza el servidor MCP, arma el system prompt y deja todo en `app.state`. Al apagar, cierra todo en orden.
2. **Dónde está.** `backend/main.py:43-122`.
3. **Fragmento clave** (`backend/main.py:69-81`):

```python
    tools = McpToolRegistry(
        StdioServerParameters(
            command=sys.executable,  # el python del venv activo: mismas dependencias que el backend
            args=["-m", "mcp_server"],
            cwd=BACKEND_DIR,
            # stdio_client filtra el entorno del padre: se pasa explícito lo que el hijo necesita.
            env={"DATA_FILE": str(settings.data_file), "LOG_LEVEL": settings.log_level},
        ),
        connect_timeout=settings.mcp_connect_timeout,
        call_timeout=settings.mcp_call_timeout,
        retry_base=settings.mcp_retry_base,
        retry_max=settings.mcp_retry_max,
    )
```

   - `sys.executable`: el subproceso usa el mismo Python del venv, así que no hay versiones mezcladas.
   - `env`: el SDK no hereda todo el entorno del padre. Solo pasa lo que el hijo necesita.
   - Los timeouts y reintentos salen de `.env`, no de constantes en el código.
4. **Por qué así.** `lifespan` es un *async context manager*: lo que está antes del `yield` corre al arrancar y lo que está en el `finally`, al apagar. Así nunca quedan procesos huérfanos. Si Ollama o MCP no responden al arrancar, el backend arranca igual y avisa por mensaje (`main.py:84-96`).
5. **Conexión con la teoría.** DIP: es la raíz de composición. Paso "Orquestador" del plan.
6. **Preguntas probables.**
   - *¿Por qué el backend arranca aunque Ollama esté caído?* Para que el lector y el modelo en la nube sigan funcionando. `OLLAMA_REQUIRED=true` cambia ese comportamiento.
   - *¿Dónde está la confirmación de conexión?* En el log JSON `mcp_connected`.

### A4. Frontend, paso por paso

| # | Requisito | Estado | Evidencia | Nota |
|---|---|---|---|---|
| 1 | Vite + React | Cumple | `frontend/package.json`, `vite.config.js:8-20` | |
| 2 | `axios` y `lucide-react` | Equivalente | lucide sí; axios no (`fetch`) | Ver A2.11. |
| 3 | Tailwind `content` + fuentes Inter/Outfit | Equivalente | `index.css:3-7` | Tailwind 4 detecta las clases solo. Las fuentes son del sistema; el comentario de `index.css:3` lo justifica: "Sin Google Fonts: evita una request a terceros". |
| 4a | Directivas Tailwind | Cumple | `index.css:1` (`@import "tailwindcss"`, sintaxis de la v4) | |
| 4b | Google Fonts | Equivalente | `index.css:3` | Justificado en comentario. |
| 4c | Fondo `#0f172a` con gradientes radiales | Cumple | `index.css:15-18` | Corregido: ahora `bg-slate-900` (`#0f172a`). Gradientes presentes. |
| 4d | `.glass` (blur 12px, borde translúcido) | Cumple | `index.css:22-26` | |
| 4e | `.custom-scrollbar` | Equivalente | `index.css:28-31` (`thin-scrollbar`) | Mismo objetivo con otro nombre. |
| 5a | Pide `/api/fundacion` al montar | Cumple | `App.jsx:86-94` | |
| 5b | WebSocket con reintento a los 3 s | Equivalente | `useWebSocket.js:36-47`, `services/ws.js:21-28` | Backoff exponencial con jitter (0,5 s a 30 s), justificado en el comentario de `ws.js:22-23`. No reintenta tras 1008. |
| 5c | Mensaje de bienvenida | Cumple | `App.jsx:15` | |
| 5d | Sidebar con `scrollIntoView({behavior:'smooth'})` | Cumple | `App.jsx:124-131`, `Sidebar.jsx:23`; navegador: tras el clic, `debates_origen_03` quedó a 32 px del borde, con foco | Respeta `prefers-reduced-motion`. |
| 5e | Botón mostrar/ocultar sidebar | Cumple | `App.jsx:152-160` | |
| 5f | "Las Varillas Digital" y "Consultar Agente" | Cumple | `App.jsx:162-164,174` | El botón dice "Consultar agente" (minúscula). |
| 5g | Lector con `id` como ancla y `scroll-mt` | Cumple | `Reader.jsx:23` | Medido: `scroll-margin-top: 32px`. |
| 5h | Título "Debate sobre la fundación…" | Cumple | `Reader.jsx:6-8` | |
| 5i | Pie con año dinámico | Cumple | `Reader.jsx:41-43` (`new Date().getFullYear()`) | Agregado en la corrección 3. En la auditoría inicial faltaba. |
| 5j | Drawer "Asistente Varillas", indicador en línea, cerrar | Cumple | `ChatDrawer.jsx:183-211`, estados en `:12-17` | También cierra con Escape. |
| 5k | Burbujas distintas | Cumple | `ChatDrawer.jsx:98-133` | Suma burbuja de error y etiqueta del proveedor. |
| 5l | `Loader2` con texto de estado | Cumple | `ChatDrawer.jsx:222-228` | |
| 5m | Enter envía, Shift+Enter salta línea | Cumple | `ChatDrawer.jsx:241-243` | También respeta IME (`isComposing`). |
| 5n | Enviar deshabilitado si carga o vacío | Cumple | `ChatDrawer.jsx:172,250` | También si está desconectado o pasa los 1000 caracteres. |
| 5o | Aviso si no hay conexión al enviar | Cumple | `App.jsx:114-117` (`offline`), estado "Reconectando…" (`ChatDrawer.jsx:15`) | El botón se deshabilita antes, así que el aviso casi nunca aparece. |
| 5p | Backdrop con blur | Cumple | `ChatDrawer.jsx:182` | |
| 5q | Autoscroll | Cumple | `ChatDrawer.jsx:157-159` | |
| 5r | Dónde quedó cada parte | Cumple | `App.jsx` (estado y reducer), `Sidebar.jsx`, `Reader.jsx`, `ChatDrawer.jsx`, `hooks/useWebSocket.js`, `services/api.js`, `services/ws.js` | |

**Para exponer**

1. **Qué hace.** Es una sola página con tres zonas: índice, lector y chat. El estado del chat vive en un *reducer*, una función pura que recibe el estado y un evento y devuelve el estado nuevo. Cada evento del WebSocket es una acción del reducer.
2. **Dónde está.** `App.jsx:32-75` (reducer), `hooks/useWebSocket.js` (conexión), `components/ChatDrawer.jsx` (chat).
3. **Fragmento clave** (`frontend/src/hooks/useWebSocket.js:36-47`):

```js
      socket.onclose = (close) => {
        // Un socket descartado (StrictMode, unmount) cierra tarde: no debe pisar la ref del socket vivo.
        if (socketRef.current === socket) socketRef.current = null
        if (disposed) return
        handlersRef.current.onClose?.()
        if (close.code === CLOSE_POLICY_VIOLATION) {
          setStatus('rejected') // origen no permitido: reintentar no lo arregla
          return
        }
        setStatus('reconnecting')
        timer = setTimeout(connect, reconnectDelay(attempt++))
      }
```

   - Línea 3: en desarrollo, StrictMode monta y desmonta dos veces. Sin este chequeo, un socket viejo borraría el nuevo.
   - Línea 4: si el componente se desmontó, no reconecta.
   - Líneas 6-8: el código 1008 significa "origen rechazado", y reintentar no lo arregla.
   - Línea 11: espera creciente con azar (*jitter*) en lugar de 3 s fijos.
4. **Por qué así.** Con 3 s fijos, si el backend se cae, todos los clientes reconectan en el mismo instante. El backoff con jitter los reparte. El texto del modelo se arma como nodos de React, nunca como HTML (`ChatDrawer.jsx:31-45`), porque la salida de un LLM no es confiable (XSS).
5. **Conexión con la teoría.** Sección "Frontend" del plan. SRP en el frontend: servicios (red), hook (conexión) y componentes (vista).
6. **Preguntas probables.**
   - *¿Por qué un proxy de Vite?* El navegador habla con un solo origen (`:5173`), y el header `Origin` llega intacto para que el backend lo valide.
   - *¿Qué es `scroll-mt`?* Es margen de scroll: deja 32 px libres arriba del documento al saltar.

### A5. Puesta en marcha

| # | Requisito | Estado | Evidencia | Nota |
|---|---|---|---|---|
| 1 | `launch.json` con `backend` y `frontend` | Cumple | `.claude/launch.json` | |
| 2 | `pytest` | Cumple | `116 passed in 1.74s` | 0 fallos. |
| 3 | lint y build | Cumple | `oxlint`: sin avisos. `vite build`: 1884 módulos, JS de 241,97 kB (gzip 76,30 kB) | |
| 4 | Ollama + prueba en navegador | Sin verificar | `curl 127.0.0.1:11434/api/tags` no respondió; log `ollama_unavailable_at_startup` | Ollama está instalado, pero no corriendo. La app se probó igual con el proveedor en la nube. |

**Para exponer**

1. **Qué hace.** Dos servidores: Uvicorn en `127.0.0.1:8000` y Vite en `:5173`, con proxy al backend. Los tests corren sin red ni Ollama gracias a los *fakes*.
2. **Dónde está.** `.claude/launch.json`, `backend/pytest.ini`, `backend/tests/conftest.py`.
3. **Fragmento clave** (`.claude/launch.json`):

```json
    {
      "name": "backend",
      "runtimeExecutable": ".venv/Scripts/python.exe",
      "runtimeArgs": ["backend/main.py"],
      "port": 8000
    },
```

4. **Por qué así.** Vite tiene `strictPort: true`. Si saltara a 5174, ese origen no estaría en `CORS_ORIGINS` y el WebSocket cerraría con 1008.
5. **Conexión con la teoría.** Sección "Puesta en marcha" del plan.
6. **Preguntas probables.**
   - *¿Cómo testean sin Ollama?* Con `FakeLLM`, que implementa el mismo contrato. Eso es DIP en acción.
   - *¿Los tests detectan alucinaciones?* No. Para eso está `evals/eval_agent.py`, que corre contra Ollama real.

### A6. Entregables del estudiante

| # | Requisito | Estado | Evidencia | Nota |
|---|---|---|---|---|
| 1 | Confirmación de conexión en consola | Equivalente | log `mcp_connected` con `tools` + `Application startup complete` | Ver A3.4g. |
| 2 | Navegación fluida | Cumple | navegador: clic en "Teoría de Fundación 1904", el artículo quedó a 32 px y con foco | Captura tomada durante la auditoría. |
| 3a | "¿Quién es Lorenzo Dabbene?" con llamada autónoma a la tool | Parcial (mitigado, sin reverificar) | Nube, intento 1: "Lo siento, solo puedo ayudar con preguntas sobre la historia de Las Varillas.", con log `agent_answer iteration: 1` **sin** `tool_call`. Intento 2: "No hay registros de «Lorenzo Dabbene» en los documentos. La teoría… 1903 es defendida por… Valter Dabbene…" (correcto) | No determinista: 1 de 2 sin tool. Prompt reescrito (corrección 2), **sin reprobar en vivo**. Local: sin verificar. |
| 3b | "¿Cuándo llegó el tren?" | Cumple (nube) | log `tool_call {"tema": "Llegada del Ferrocarril 24 de diciembre de 1900"}` y después `tool_search hits: ["debates_origen_01"]`. La respuesta cita el 24/12/1900 y el botón de fuente | |
| 3c | Repregunta con contexto | Parcial (corregido, ver nota) | "¿Y quién defiende esa fecha?": resolvió 1900 y Centro de Estudios Parada KM 81 (contexto OK), pero empezó con "No hay registros de «fecha» en los documentos." Log: `missing: ["fecha"]` | AVISO falso: "fecha" no estaba en `_GENERIC_TERMS`. **Corregido** (corrección 1, con test); no se repitió la prueba en el navegador. |
| 3d | Lo mismo con `llama3.2` local | Sin verificar | Ollama apagado | Para verificar: `ollama serve`, `ollama pull llama3.2`, reiniciar el backend y repetir. También `python -m evals.eval_agent --reps 2`. |

**Para exponer**

1. **Qué hace.** Es la prueba de punta a punta: el modelo decide solo cuándo buscar, y las citas que ve el usuario salen del texto que devolvió la tool, no de lo que dice el modelo.
2. **Dónde está.** `api/ws.py:126-134` (fuentes), `store/history.py:229-231` (`rendered_ids`).
3. **Fragmento clave** (logs reales de la demo):

```
{"msg": "tool_call", "iteration": 1, "tool": "consultar_fundacion_las_varillas", "arguments": {"tema": "Llegada del Ferrocarril 24 de diciembre de 1900"}}
{"logger": "mcp_server", "msg": "tool_search", "tema": "Llegada del Ferrocarril 24 de diciembre de 1900", "hits": ["debates_origen_01"], "missing": []}
```

   - La primera línea la escribe el agente: el modelo pidió la tool en la vuelta 1.
   - La segunda la escribe el subproceso MCP por stderr: qué buscó y qué encontró.
   - Las dos comparten `conn_id` (contextvar), así que se puede seguir una conversación entera.
4. **Por qué así.** Las citas no dependen de que el modelo escriba bien un ID. `rendered_ids` las extrae del formato `[id] titulo` que arma `render_documents`.
5. **Conexión con la teoría.** Entregables 1 a 3 del plan.
6. **Preguntas probables.**
   - *¿Cómo sé que no inventó?* Mirá el log `tool_search` y el botón de fuente. Abre el documento exacto.
   - *¿Por qué a veces dice "no hay registros de X"?* Es el AVISO del servidor MCP. Sirve para nombres inexistentes, pero hoy también salta con "fecha" (bug).

---

## 4. Parte B: SOLID y clases abstractas

### B1. SRP (responsabilidad única)

| # | Requisito | Estado | Evidencia | Gravedad / Nota |
|---|---|---|---|---|
| 1 | Una razón de cambio por módulo | Cumple | docstrings: `store/history.py:1`, `llm/ollama.py:1`, `tools/registry.py:1`, `historian.py:1`, `ws.py:1`, `main.py:1` | |
| 2 | Agente sin WebSocket; API sin lógica de agente | Cumple | `historian.py` no importa nada de `api/` ni de `fastapi` (grafo de imports). `ws.py:133` solo llama `agent.run` | |
| 3 | Funciones largas o complejas | Parcial | `ws.chat_socket` (`ws.py:166-217`, 52 líneas: Origin, límites, bucle y limpieza); `ws._run_turn` (9 ramas `except`, `:132-161`); `McpToolRegistry` (concurrencia, `registry.py:52-187`); `main.lifespan` (80 líneas, solo composición) | Baja. `_run_turn` es una tabla de traducción excepción a evento, cohesiva. `chat_socket` podría extraer `_admit(websocket)`. |

**Para exponer**

1. **Qué hace.** Cada carpeta tiene un único motivo para cambiar: datos, proveedores, herramientas, razonamiento, transporte, composición.
2. **Dónde está.** Docstring de cada módulo. Ejemplo: `api/rest.py`.
3. **Fragmento clave** (`backend/api/rest.py:19-25`):

```python
def get_store(request: Request) -> HistoryStore:
    return request.app.state.store


@router.get("/fundacion", response_model=FundacionResponse, summary="Corpus histórico completo")
def get_fundacion(store: Annotated[HistoryStore, Depends(get_store)]) -> FundacionResponse:
    return FundacionResponse(raw=list(store.documents), full_text=store.full_text)
```

   - `Depends(get_store)` es la inyección de dependencias de FastAPI: el endpoint recibe el store y no lo crea.
   - El endpoint solo transporta. Buscar y validar es trabajo de `HistoryStore`.
4. **Por qué así.** Si cambia el formato de Groq, se toca `openai_compat.py` y nada más. Si cambia el protocolo del WebSocket, se toca `ws.py`.
5. **Conexión con la teoría.** SRP: "una clase, una razón para cambiar".
6. **Preguntas probables.**
   - *¿`ws.py` no hace demasiado?* Hace transporte con seguridad (Origin, límites de mensajes y conexiones). Es la función más larga y la candidata a dividir.

### B2. OCP (abierto/cerrado)

| # | Requisito | Estado | Evidencia | Gravedad / Nota |
|---|---|---|---|---|
| 1 | Proveedor nuevo sin tocar `HistorianAgent` | Cumple | `historian.py:71,99-100`: elige por clave de un dict, sin `if` sobre tipos. Alta en `main.py:102-104` | |
| 2 | Sin `if`/`elif` sobre proveedor fuera de la composición | Parcial | Auditoría: `ws.py` tenía `if provider == "local"`. **Corregido:** ahora usa `LLMUnavailable.public`. Siguen `Provider = Literal["local", "cloud"]` (`ws.py`, `rest.py`) y `ChatDrawer.jsx` | Media. Un tercer proveedor obliga todavía a tocar `ws.py`, `rest.py` y el frontend. |
| 3 | Tool nueva solo en `mcp_server.py` | Cumple | `registry.py:23-31` (descubre por `tools/list`), `historian.py:102`; `CLAUDE.md` | |

**Para exponer**

1. **Qué hace.** El agente recibe un diccionario `{nombre: proveedor}`. Para sumar un modelo, se registra en `main.py` y el agente no cambia.
2. **Dónde está.** `main.py:102-104`, `historian.py:71,99-100`.
3. **Fragmento clave** (`backend/main.py:101-105`):

```python
        # Sin key el proveedor "cloud" no se registra: el agente responde provider_unavailable.
        llms: dict[str, LLMProvider] = {"local": llm}
        if settings.groq_api_key:
            llms["cloud"] = cloud
            logger.info("cloud_llm_configured", extra={"model": settings.groq_model})
```

   - El `if` está en la composición, que es donde corresponde.
   - El agente nunca pregunta "¿sos Ollama?": solo llama `chat`.
4. **Por qué así.** El modelo en la nube se sumó después sin tocar el bucle del agente. Quedó una fuga: la lista de nombres válidos está repetida en la API y en el frontend.
5. **Conexión con la teoría.** OCP: abierto a extensión (nuevo `LLMProvider`), cerrado a modificación (el agente).
6. **Preguntas probables.**
   - *¿Qué hay que tocar para sumar un proveedor?* Una clase nueva, `main.py` y, hoy, `ws.py`, `rest.py` y el frontend. Lo ideal sería solo los dos primeros.

### B3. LSP (sustitución de Liskov)

| # | Requisito | Estado | Evidencia | Gravedad / Nota |
|---|---|---|---|---|
| 1 | `OllamaClient`, `OpenAICompatClient` y `FakeLLM` intercambiables | Cumple | el agente los usa sin distinguir (`historian.py:108`); `test_provider_cloud_*` comparte historial | |
| 2 | Firmas iguales a la base | Cumple | comparación con `inspect.signature`: OK en `chat`, `chat_stream`, `health`, `warm_up` y `aclose` | |
| 3 | Excepciones dentro del contrato | Cumple | todas las de los proveedores heredan de `LLMError` (`provider.py:50-63`) | `OpenAICompatClient.chat` lanza `LLMUnavailable` sin key (`openai_compat.py:93-95`): está dentro de la jerarquía. |
| 4 | Sin `NotImplementedError` ni vacíos que rompan | Cumple | no hay `NotImplementedError` en `backend/`. `warm_up` y `aclose` de la base son *hooks* opcionales | |
| 5 | `ToolRegistry`, `McpToolRegistry`, `FakeTools` | Cumple | firmas OK. `FakeTools.call` lanzaba `KeyError`; **corregido**, ahora lanza `ToolError` como pide el contrato | `McpToolRegistry` ya lanzaba `ToolError`. |

**Para exponer**

1. **Qué hace.** Cualquier proveedor puede reemplazar a otro sin que el agente lo note: mismos métodos, mismos tipos y las mismas familias de errores.
2. **Dónde está.** `llm/provider.py:66-89`, `tests/conftest.py:19-43`.
3. **Fragmento clave** (`backend/llm/provider.py:70-79`):

```python
    async def chat_stream(self, messages: Sequence[Message], tools: Sequence[ToolSpec], on_delta: DeltaCallback) -> LLMResponse:
        """Igual que chat, pero emite el texto por on_delta mientras se genera. Devuelve la respuesta completa.

        Por defecto no hay stream real: emite el texto entero al final. Solo se emite texto de respuestas
        sin tool calls, salvo que el proveedor ya lo haya mandado antes de saber que venía una tool call.
        """
        response = await self.chat(messages, tools)
        if response.content and not response.tool_calls:
            await on_delta(response.content)
        return response
```

   - Es un método concreto en la clase abstracta: una implementación por defecto.
   - `FakeLLM` no implementa streaming y aun así cumple el contrato. Por eso los tests del WS funcionan sin cambios.
4. **Por qué así.** El streaming se agregó sin romper ningún proveedor ni ningún fake: LSP mantenido por diseño.
5. **Conexión con la teoría.** LSP: "un subtipo no debe sorprender a quien usa el tipo base".
6. **Preguntas probables.**
   - *¿Ollama no "sorprende" al retener texto que empieza con `{`?* No: el contrato es "emitir el texto de la respuesta". Un JSON que en realidad es una tool call no es respuesta.

### B4. ISP (segregación de interfaces)

| # | Requisito | Estado | Evidencia | Gravedad / Nota |
|---|---|---|---|---|
| 1 | Contratos chicos | Cumple | `LLMProvider`: 2 abstractos (`chat`, `health`). `ToolRegistry`: 2 (`specs`, `call`). Verificado con `__abstractmethods__` | |
| 2 | Métodos implementados "de relleno" | Cumple | `FakeLLM.health` devuelve `None` (`conftest.py:42-43`). `OpenAICompatClient.health` no hace request (`openai_compat.py:86-88`, justificado: "el free tier cuenta cada llamada") | Aceptables: el contrato es "lanzá si no podés atender". |
| 3 | Métodos de ciclo de vida fuera del contrato | Cumple | `McpToolRegistry.connect`/`aclose` no están en `ToolRegistry`. Solo los usa `main.py` | Buen ISP: el agente no ve `connect`. |

**Para exponer**

1. **Qué hace.** Los contratos piden lo mínimo. Lo opcional (precargar el modelo, cerrar conexiones) tiene implementación vacía por defecto.
2. **Dónde está.** `llm/provider.py:81-89`.
3. **Fragmento clave** (`backend/llm/provider.py:81-89`):

```python
    @abstractmethod
    async def health(self) -> None:
        """Lanza LLMUnavailable si el proveedor no puede atender pedidos."""

    async def warm_up(self) -> None:
        """Opcional: precarga el modelo."""

    async def aclose(self) -> None:
        """Opcional: libera conexiones."""
```

   - Solo `health` es obligatorio.
   - `warm_up` tiene sentido en Ollama (carga el modelo en RAM) y no en Groq: Groq no lo implementa y no pasa nada.
4. **Por qué así.** Si `warm_up` fuera abstracto, cada fake y cada proveedor en la nube tendría un método vacío solo para cumplir.
5. **Conexión con la teoría.** ISP: "ningún cliente debe depender de métodos que no usa".
6. **Preguntas probables.**
   - *¿Un método vacío no viola ISP?* Viola ISP cuando es obligatorio y no tiene sentido. Acá es un *hook* opcional con default.

### B5. DIP (inversión de dependencias)

| # | Requisito | Estado | Evidencia | Gravedad / Nota |
|---|---|---|---|---|
| 1 | `HistorianAgent` recibe abstracciones por constructor | Cumple | `historian.py:62-75` | |
| 2 | `main.py` única raíz de composición | Cumple | `query_graph` sobre aristas `IMPORTS`: solo `main.py` importa `llm.ollama`, `llm.openai_compat` y `McpToolRegistry` | |
| 3 | `api/` sin implementaciones concretas | Cumple | `ws.py:168` y `rest.py:19-20,34-35` usan `app.state` / `Depends`. `ws.py` importa `HistorianAgent` (clase concreta única, sin contrato) | Baja: aceptable, ver B7. |
| 4 | Sin imports de módulos concretos desde alto nivel | Cumple | Auditoría: `historian.py` importaba `tools.registry`, que arrastraba el SDK `mcp`. **Corregido:** `ToolRegistry`, `ToolError` y `ToolsUnavailable` viven en `tools/base.py`; el agente y la API importan de ahí | Solo `main.py` y las evals importan `tools.registry`. |
| 5 | Tests con fakes | Cumple | `tests/conftest.py:19-61`; 116 tests sin red | |

**Para exponer**

1. **Qué hace.** El agente no crea sus dependencias: se las pasan ya construidas. A eso se le llama **inyección de dependencias**. El agente depende de contratos y `main.py` decide qué implementación usar.
2. **Dónde está.** `historian.py:62-75`, `main.py:106-112`, `tests/conftest.py`.
3. **Fragmento clave** (`backend/agents/historian.py:62-75`):

```python
    def __init__(
        self,
        llm: LLMProvider | Mapping[str, LLMProvider],
        tools: ToolRegistry,
        system_prompt: str,
        *,
        max_iterations: int = 5,
        max_turns: int = 6,
    ) -> None:
        self._llms = dict(llm) if isinstance(llm, Mapping) else {DEFAULT_PROVIDER: llm}
        self._tools = tools
        self._system_prompt = system_prompt
        self._max_iterations = max_iterations
        self._max_turns = max_turns
```

   - Los tipos son abstracciones: `LLMProvider` y `ToolRegistry`, nunca `OllamaClient`.
   - El `*` obliga a pasar los parámetros opcionales por nombre.
   - Línea 10: acepta un proveedor suelto (lo usan tests y evals) o un dict (lo usa la app).
4. **Por qué así.** Gracias a esto los tests reemplazan Ollama y MCP por fakes en memoria, y la suite corre en menos de 2 segundos.
5. **Conexión con la teoría.** DIP: "los módulos de alto nivel no dependen de los de bajo nivel; ambos dependen de abstracciones".
6. **Preguntas probables.**
   - *¿Dónde se elige Ollama?* Solo en `main.py:52-60`.
   - *¿El agente importa algo concreto?* No usa nada concreto, pero el módulo de contratos de tools comparte archivo con la implementación MCP. Es la única fuga.

### B6. Clases abstractas y tipado

| # | Requisito | Estado | Evidencia | Gravedad / Nota |
|---|---|---|---|---|
| 1 | `abc.ABC` + `@abstractmethod`; instanciar la base lanza `TypeError` | Cumple | `provider.py:66-83`, `registry.py:42-49`. Ejecutado: "Can't instantiate abstract class LLMProvider without an implementation for abstract methods 'chat', 'health'", y lo mismo para `ToolRegistry` (`call`, `specs`) | |
| 2 | Propiedades abstractas con `@property` sobre `@abstractmethod` | Cumple (no aplica) | no hay propiedades abstractas | |
| 3 | ¿`typing.Protocol`? | Cumple | ver nota | `LLMProvider` debe seguir como ABC porque comparte código (`chat_stream` por defecto, hooks). `ToolRegistry` podría ser un `Protocol`: no comparte código. Pero el ABC da el `TypeError` temprano y los fakes heredan a propósito. |
| 4 | Type hints en firmas públicas | Cumple | todas las firmas públicas tipadas | Los dos tipos laxos de la auditoría se corrigieron: `StatusCallback` es un `Protocol` con firma exacta y `_detail` tiene `dict[str, Any]`. |
| 5 | `mypy` | Cumple | `mypy 2.3.1`, instalado con permiso: 58 errores iniciales (54 falsos positivos de `Settings()`, 4 reales), ahora 0 en 30 archivos | Config en `backend/mypy.ini` (plugin de pydantic, `check_untyped_defs`). |
| 6 | `pylint` / `flake8` / `ruff` | Cumple | `ruff 0.16.9`: 18 avisos iniciales, ahora 0 (11 con `--fix`, el resto a mano o con `# noqa` justificado). Ningún aviso de diseño | No se probó `pylint` ni `flake8`. |

**Para exponer**

1. **Qué hace.** Una clase abstracta es un molde: declara métodos obligatorios con `@abstractmethod`, y Python no deja crear objetos de una clase a la que le falta alguno.
2. **Dónde está.** `tools/registry.py:42-49`.
3. **Fragmento clave** (`backend/tools/registry.py:42-49`):

```python
class ToolRegistry(ABC):
    @abstractmethod
    async def specs(self) -> list[ToolSpec]:
        """Tools disponibles. Lanza ToolsUnavailable."""

    @abstractmethod
    async def call(self, name: str, arguments: dict[str, Any], *, user_question: str | None = None) -> str:
        """Ejecuta una tool. Lanza ToolError o ToolsUnavailable."""
```

   - El docstring documenta qué excepciones forman parte del contrato. Para LSP importa tanto como la firma.
   - `ToolRegistry()` lanza `TypeError` (verificado).
4. **Por qué así.** ABC frente a Protocol: `Protocol` es tipado estructural (*duck typing* chequeado por mypy, sin herencia). ABC exige herencia y falla al instanciar. Acá se eligió ABC porque `LLMProvider` comparte implementación.
5. **Conexión con la teoría.** Guía "clases y métodos abstractos".
6. **Preguntas probables.**
   - *¿Qué pasa si me olvido de implementar `health`?* `TypeError` al crear el objeto, no al llamarlo.
   - *¿Por qué no `Protocol`?* Porque `LLMProvider` trae código por defecto (`chat_stream`), y eso un `Protocol` no lo hereda.

### B7. Pragmatismo

| # | Requisito | Estado | Evidencia | Gravedad / Nota |
|---|---|---|---|---|
| 1 | Abstracciones sin aporte | Cumple | `LLMProvider`: 2 implementaciones + fake. `ToolRegistry`: 1 + fake usado en 116 tests. `HistorianAgent` sin contrato (bien: una sola implementación) | |
| 2 | Sobreingeniería | Parcial | `HistorianAgent.__init__` acepta `LLMProvider \| Mapping` (`historian.py:64,71`): dos formas de construirlo. Límites por IP y token bucket (`api/ratelimit.py`) para una app de aula | Baja. Los límites protegen la cuota de Groq; la tolerancia a typos y la detección de nombres están justificadas en docstrings. |
| 3 | Decisiones documentadas | Cumple | `CLAUDE.md` (sección "Decisiones que no son obvias"), docstrings en cada módulo, `.env.example` comentado | Los desvíos de frontend y de arranque se documentaron en `CLAUDE.md` (corrección 5). |

**Para exponer**

1. **Qué hace.** Las abstracciones existen donde hay más de una implementación o donde los tests las necesitan. Lo que tiene una sola forma (el agente, el store) es una clase concreta.
2. **Dónde está.** `CLAUDE.md`, `agents/historian.py:37-56`.
3. **Fragmento clave** (`backend/agents/historian.py:45-53`):

```python
    def __init__(self, system_prompt: str, max_turns: int) -> None:
        self._system = Message(role="system", content=system_prompt)
        self._turns: deque[tuple[Message, Message]] = deque(maxlen=max_turns)

    def with_pending(self, pending: list[Message]) -> list[Message]:
        return [self._system, *chain.from_iterable(self._turns), *pending]

    def commit(self, question: Message, answer: Message) -> None:
        self._turns.append((question, answer))
```

   - `deque(maxlen=…)` descarta solo los turnos viejos: es una ventana deslizante sin código extra.
   - El system prompt va siempre primero y nunca se recorta.
4. **Por qué así.** Es la solución más simple que garantiza que el prompt entre en el contexto de un 3B.
5. **Conexión con la teoría.** Contrapeso de SOLID: no abstraer "por si acaso" (YAGNI).
6. **Preguntas probables.**
   - *¿Por qué no hay interfaz para el agente?* Hay una sola implementación y los tests usan la real con fakes debajo.

---

## 5. Faltantes: estado final

Los 12 faltantes de la auditoría inicial se atendieron según la tabla "Correcciones aplicadas". Quedan abiertos:

1. **Verificar la nube con "¿Quién es Lorenzo Dabbene?" varias veces.** El prompt se reescribió, pero no se volvió a probar en vivo. Si sigue fallando, la alternativa es `tool_choice="required"` en la primera vuelta, lo que cambia el contrato de `LLMProvider` (`llm/provider.py`, `llm/openai_compat.py`, `agents/historian.py`) y obliga a actualizar los fakes.
2. **Probar con `llama3.2` local.** Falta `ollama serve` y `ollama pull llama3.2`; después reiniciar el backend y repetir las preguntas de A6, o correr `python -m evals.eval_agent --reps 2`. Las evals hoy solo cubren Ollama.
3. **OCP: lista de proveedores repetida.** `Provider = Literal["local", "cloud"]` en `api/ws.py` y `api/rest.py`, y el mapa `PROVIDER` de `frontend/src/components/ChatDrawer.jsx`. Arreglo: derivar los nombres de `agent.providers`. Impacto bajo mientras haya dos proveedores.
4. **Hueco antes del pie.** El último artículo conserva `last:min-h-[calc(100dvh-7rem)]`, así que queda espacio vacío antes del `<footer>`. Es cosmético; no se vio en el navegador.
5. **Sin pruebas en el navegador tras las correcciones.** Los cambios de frontend se validaron solo con lint y build, y el fix del aviso por «fecha» solo con tests.

## 6. Comandos ejecutados

| Comando | Resultado |
|---|---|
| `pytest -q` (desde `backend/`) | auditoría inicial: 116 passed en 1,74 s. Tras las correcciones: 118 passed en 1,59 s |
| `npm --prefix frontend run lint` | oxlint sin avisos |
| `npm --prefix frontend run build` | OK: 1884 módulos, JS 241,97 kB / CSS 28,13 kB |
| `curl 127.0.0.1:11434/api/tags` | sin respuesta: Ollama apagado (instalado en `AppData\Local\Programs\Ollama`) |
| `python -m mypy / ruff / pylint / flake8` | auditoría inicial: ninguno instalado |
| `pip install mypy==2.3.1 ruff==0.16.9` (con permiso) | instalados en `.venv` |
| `mypy .` (desde `backend/`) | 58 errores iniciales; tras las correcciones: "Success: no issues found in 30 source files" |
| `ruff check .` | 18 avisos iniciales; tras las correcciones: 0 |
| `npm run lint` y `npm run build` tras el pie y el fondo | sin errores |
| Script de chequeo ABC + `inspect.signature` | `TypeError` en ambas bases; firmas de las 5 subclases OK |
| `query_graph` (aristas `IMPORTS`) | solo `main.py` importa clases concretas |
| `check_index_coverage` scope `backend` | sin huecos en el código (solo `__pycache__` y una línea de `pytest.ini`) |
| `preview_start backend` / `frontend` | arrancaron. Logs: `store_loaded`, `ollama_unavailable_at_startup`, `mcp_connected`, `cloud_llm_configured` |
| Navegador: `/api/fundacion`, `/api/modelos` | 200; 3 docs; local `llama3.2:3b`, nube `openai/gpt-oss-120b` disponibles |
| Navegador: clic en el índice, ítem 3 | `debates_origen_03` a 32 px, con foco |
| Navegador: chat local | error `llm_unavailable`, mensaje claro |
| Navegador: chat nube (Dabbene ×2, tren, repregunta) | ver A6: 1 respuesta sin tool y 1 AVISO falso |

## 7. Guion de exposición (unos 15 minutos)

| Min | Tema | En pantalla | Idea principal |
|---|---|---|---|
| 0:00-1:30 | Problema | App abierta: lector + índice | Un chat que responde solo con documentos, en un debate abierto (1900/1903/1904). |
| 1:30-3:00 | Arquitectura | Diagrama de la sección 2 | Cinco piezas, y un mensaje que las recorre. |
| 3:00-4:30 | Datos + MCP | `mcp_server.py:60-93`, `store/history.py:156-179` | La herramienta es un proceso aparte que habla por stdio. |
| 4:30-6:30 | Contratos (SOLID) | `llm/provider.py:66-89`, `tools/registry.py:42-49` | ABC: el agente conoce contratos, no proveedores. DIP + LSP + ISP. |
| 6:30-8:30 | Agente | `historian.py:99-131` | Bucle de razonamiento con tope de 5 vueltas. El historial guarda solo (pregunta, respuesta). |
| 8:30-9:30 | Composición | `main.py:43-122` | Único lugar con clases concretas; `lifespan` abre y cierra todo. |
| 9:30-12:30 | **Demo en vivo** | Navegador + terminal del backend | Preguntar "¿Cuándo llegó el tren?". Mostrar el spinner "Consultando base histórica… «tema»", el log `tool_call` y el `tool_search` con `hits`, y el botón de fuente que salta al documento. Después, "¿Quién es Lorenzo Dabbene?" con el AVISO. |
| 12:30-13:30 | Seguridad y robustez | `ws.py:173-183`, `useWebSocket.js:36-47` | Validación de Origin (CSWSH), límites, reconexión con backoff. |
| 13:30-14:30 | Tests | `pytest` en vivo (2 s) + `conftest.py` | Los fakes prueban que las dependencias están invertidas. |
| 14:30-15:00 | Cierre | Sección 5 del informe | Lo que sigue: verificar con el modelo local y la nube. |

Antes de la demo: repetir varias veces "¿Quién es Lorenzo Dabbene?" con la nube (el prompt cambió y no se reprobó en vivo) y la repregunta "¿Y quién defiende esa fecha?". Levantar `ollama serve` si se va a mostrar el modelo local. Tener el modelo en la nube como respaldo.

## 8. Glosario

- **MCP (Model Context Protocol)**: protocolo estándar para que un programa ofrezca herramientas y datos a un LLM.
- **stdio**: entrada y salida estándar de un proceso; acá es el canal del protocolo MCP.
- **JSON-RPC**: formato de mensajes pedido/respuesta en JSON que usa MCP.
- **Tool / tool call**: función que el modelo puede pedir; el pedido estructurado es la *tool call*.
- **inputSchema**: JSON Schema de los argumentos de una tool.
- **LLM**: modelo de lenguaje grande (llama3.2, gpt-oss).
- **Ollama**: servidor local que corre modelos en la propia máquina.
- **Groq**: servicio en la nube con API compatible con OpenAI.
- **System prompt**: instrucciones fijas que el modelo lee antes de la conversación.
- **num_ctx**: tamaño de la ventana de contexto, en tokens, que el modelo puede leer.
- **Token**: pedazo de texto (aprox. una sílaba o palabra) con que el modelo mide su entrada.
- **Temperature**: cuánto azar usa el modelo; baja significa respuestas más fieles a los datos.
- **ReAct / bucle de razonamiento**: ciclo de pensar, pedir una herramienta, observar y responder.
- **Alucinación**: dato inventado por el modelo.
- **FastAPI**: framework web async de Python.
- **Uvicorn**: servidor ASGI que ejecuta la app FastAPI.
- **ASGI**: interfaz estándar de servidores web async en Python.
- **Event loop**: bucle de asyncio que atiende muchas tareas en un hilo; no se debe bloquear.
- **async/await**: sintaxis para código que espera sin bloquear.
- **httpx**: cliente HTTP de Python con soporte async.
- **Lifespan**: función de FastAPI que corre al arrancar y al apagar.
- **app.state**: lugar donde FastAPI guarda objetos compartidos de la app.
- **Depends**: mecanismo de FastAPI para inyectar dependencias en endpoints.
- **Pydantic**: validación de datos con type hints.
- **pydantic-settings**: carga y valida la configuración desde `.env`.
- **WebSocket**: conexión persistente y bidireccional entre navegador y servidor.
- **Streaming / delta**: envío de la respuesta en pedazos mientras se genera.
- **SSE / NDJSON**: formatos de stream de Groq (eventos `data:`) y de Ollama (un JSON por línea).
- **CORS**: reglas del navegador sobre qué orígenes pueden llamar a una API.
- **Origin**: header con el sitio que abrió la conexión.
- **CSWSH**: secuestro de WebSocket desde otro sitio; se evita validando el Origin.
- **Código 1008**: cierre de WebSocket por violación de política.
- **Rate limit / token bucket**: límite de mensajes por tiempo con un "balde" que se rellena.
- **Backoff exponencial con jitter**: reintentos con esperas crecientes y algo de azar.
- **Contextvar**: variable por tarea async; lleva el `conn_id` a los logs.
- **SOLID**: cinco principios de diseño orientado a objetos.
- **SRP**: una clase, una razón para cambiar.
- **OCP**: abierto a extensión, cerrado a modificación.
- **LSP**: un subtipo debe poder reemplazar a su base sin sorpresas.
- **ISP**: interfaces chicas; nadie implementa lo que no usa.
- **DIP**: depender de abstracciones, no de implementaciones.
- **ABC**: clase base abstracta de Python (`abc.ABC`).
- **@abstractmethod**: marca un método obligatorio; sin él la subclase no se puede instanciar.
- **typing.Protocol**: interfaz por estructura (duck typing chequeado), sin herencia.
- **Inyección de dependencias**: pasar las dependencias ya construidas en lugar de crearlas adentro.
- **Raíz de composición**: único lugar que crea y conecta los objetos concretos (`main.py`).
- **Fake / doble de test**: implementación falsa de un contrato para testear sin servicios reales.
- **pytest / asyncio_mode=auto**: framework de tests; corre tests async sin marcas.
- **Eval**: prueba de calidad contra el modelo real, con patrones requeridos y prohibidos.
- **React / reducer**: librería de UI; el reducer es una función pura que calcula el estado nuevo.
- **Hook (React)**: función `use…` que encapsula estado o efectos (`useWebSocket`).
- **StrictMode**: modo de desarrollo de React que monta dos veces para detectar errores.
- **Vite / proxy**: servidor de desarrollo; reenvía `/api` y `/ws` al backend.
- **Tailwind CSS**: CSS por clases utilitarias; la v4 se configura en el CSS.
- **scrollIntoView / scroll-mt**: desplazar hasta un elemento / margen superior al hacerlo.
- **XSS**: inyección de código en la página; se evita no insertando HTML del LLM.
- **_meta**: campo de MCP para contexto fuera de los argumentos de la tool.
