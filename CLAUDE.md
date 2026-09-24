# CLAUDE.md

This file provides guidance to Claude Code (claude.ai/code) when working with code in this repository.

## Idioma

El código, los docstrings, los comentarios y los mensajes de commit están en español. Mantené ese idioma al escribir código nuevo.

## Comandos

Todo se ejecuta con el venv de la raíz (`.venv/`).

```bash
# Backend (desde backend/, con .venv activo)
python main.py                      # uvicorn en 127.0.0.1:8000
python -m mcp_server                # servidor MCP solo, por stdio (normalmente lo lanza main.py)

# Tests (desde backend/ — pytest.ini vive ahí y fija pythonpath=.)
pytest
pytest tests/test_ws.py                                  # un archivo
pytest tests/test_ws.py::test_criterio_5_segundo_mensaje_en_curso_recibe_busy   # un test
pytest -k ollama                                          # por patrón

# Evals: NO corren en pytest. Necesitan Ollama real y el modelo instalado; tardan minutos.
python -m evals.eval_agent --reps 2 [--temperature 0.1] [--only valter,tren]

# Frontend (desde la raíz)
npm --prefix frontend install
npm --prefix frontend run dev       # vite en 5173, strictPort
npm --prefix frontend run lint      # oxlint
npm --prefix frontend run build
```

`.claude/launch.json` ya define los dos servidores (`backend`, `frontend`) para `preview_start`; usalo en vez de levantarlos por Bash.

Dependencias: `backend/requirements-dev.txt` incluye a `requirements.txt`.

## Arquitectura

Un chat sobre la historia de Las Varillas. Un LLM responde preguntas usando *solamente* documentos servidos por un servidor MCP. El usuario elige el modelo por mensaje: local de 3B (Ollama) o en la nube (Groq, API OpenAI-compatible).

### Cadena de un mensaje

```
navegador  --WS /ws/chat-->  api/ws.py  -->  HistorianAgent.run  -->  OllamaClient.chat        (provider="local")
                                                     |          \-->  OpenAICompatClient.chat  (provider="cloud")
                                                     |
                                                     +-->  McpToolRegistry.call  --stdio-->  mcp_server.py  -->  HistoryStore.search
```

`backend/main.py` es el único lugar donde se arma el grafo de objetos: en el `lifespan` construye `HistoryStore`, `OllamaClient`, `McpToolRegistry` y `HistorianAgent`, y los deja en `app.state`. No hay lógica de negocio ahí.

### Separación de capas (respetarla al agregar código)

- `store/history.py` — carga y valida `fundacion.json`, busca por tokens. No sabe de MCP, LLM ni HTTP.
- `llm/provider.py` — contrato abstracto (`LLMProvider`, `Message`, `ToolSpec`, `ToolCall`). El agente solo ve estos tipos.
- `llm/ollama.py`, `llm/openai_compat.py` — traducen ese contrato al formato de cable de Ollama y de `/chat/completions`.
- `tools/registry.py` — contrato `ToolRegistry` + implementación MCP.
- `agents/historian.py` — loop de razonamiento con tools. No sabe de WebSocket ni de proveedor concreto.
- `api/ws.py`, `api/rest.py` — transporte, validación y traducción de excepciones a eventos. Sin lógica de agente.

Para agregar una herramienta alcanza con declararla en `mcp_server.py`: `McpToolRegistry` las descubre por `tools/list` y `main.py` no se toca.

### Decisiones que no son obvias leyendo un solo archivo

- **El índice de documentos va en el system prompt; el contenido solo por tool.** `build_system_prompt` inyecta `render_index(...)`. Por eso `consultar_fundacion_las_varillas` no tiene "modo índice": con `tema` vacío el modelo veía solo títulos y contestaba "no tengo información".
- **El agente nunca consulta al modelo sin tools.** `HistorianAgent.run` llama a `self._tools.specs()` antes del primer `chat`: un 3B sin datos inventa historia.
- **La pregunta original viaja por `_meta`, no por los argumentos.** Contrato en `mcp_meta.py` (`USER_QUESTION_META`). Permite que `_missing_terms` detecte nombres que el modelo recortó ("Alvarez" por "Juan Alvarez") y emita el AVISO que dispara la regla 5 del prompt. `mcp_meta.py` no importa nada: el subproceso MCP no debe depender del lado cliente.
- **`Conversation` guarda solo pares (pregunta, respuesta final).** Los resultados de tools se descartan: son la mayoría de los tokens y el modelo los vuelve a pedir. Así el system prompt nunca queda fuera de `num_ctx` ni quedan mensajes `role=tool` huérfanos.
- **El cliente MCP vive en una tarea supervisora propia** (`McpToolRegistry._supervise`). Los task groups de anyio exigen abrir y cerrar el contexto en la *misma* tarea, y quien dispara la reconexión es otro handler.
- **No existe `ping` en el protocolo MCP desde 2026-07-28.** El chequeo de vida es `tools/list` con `cache_mode="bypass"` y timeout de 3s; de paso refresca las tools.
- **`temperature` por defecto 0.1.** Con el 0.8 de Ollama el modelo 3B inventa datos.
- **Starlette no aplica CORS a WebSocket.** `chat_socket` valida el header `Origin` contra `CORS_ORIGINS` a mano y cierra con 1008 (CSWSH). Acepta antes de cerrar para que el cliente vea 1008 y no 1006.
- **Vite usa `strictPort: true` y proxy a `127.0.0.1:8000`.** Si Vite saltara a 5174 ese origen no está en `CORS_ORIGINS` y el WebSocket cerraría con 1008. No es "localhost" porque Node 17+ lo resuelve a `::1` y uvicorn escucha IPv4.
- **`/api/fundacion` lee `HistoryStore` directo, sin MCP**, para que el lector funcione aunque el servidor MCP esté caído.
- **Logs en JSON a stdout**, salvo en `mcp_server.py`: ahí stdout es el canal del protocolo, así que va a stderr. El `conn_id` viaja por contextvar.
- **Los límites (`TokenBucket`, `ConnectionLimiter`) son en memoria**: válidos con un solo worker. Con varios hace falta un store compartido.
- **El proveedor viaja en cada mensaje (`ChatIn.provider`), no en la conexión.** Cambiar de modelo no corta el WebSocket ni borra el historial: `Conversation` es por conexión y ambos modelos ven los mismos turnos. `HistorianAgent` recibe un dict `{nombre: LLMProvider}`; sin `GROQ_API_KEY` el `"cloud"` no se registra y el turno responde `provider_unavailable`. `GET /api/modelos` le dice al frontend cuál está disponible.
- **La key de Groq solo la ve el backend.** Vive en `.env`; el navegador habla con `/ws/chat` y nunca con Groq. `OpenAICompatClient.health()` no hace request: el free tier cuenta cada llamada.
- **Las citas salen del texto de la tool, no del modelo.** `rendered_ids` (en `store/history.py`, junto a `render_documents`, que define el formato `[id] titulo`) extrae los IDs de cada resultado; `api/ws.py` los manda en `ResponseEvent.sources`. El índice de "sin resultados" usa `- ID: x |` y a propósito no cuenta como cita.

- **Streaming: `chat_stream` convive con `chat`.** El agente usa `chat_stream` solo si le pasan `on_delta` (el WS siempre; evals y tests no). La implementación por defecto en `LLMProvider` llama a `chat` y emite todo junto, por eso `FakeLLM` no necesita cambios. El WS manda `DeltaEvent` por pedazo y el `ResponseEvent` final con el texto completo sigue siendo la fuente de verdad. Si el modelo escribe algo antes de pedir una tool, el frontend lo borra al recibir el estado `tool_call`.
- **Ollama retiene el texto que arranca con `{` o `` ` ``** hasta terminar: puede ser una tool call escrita como JSON (`_parse_text_tool_call`) y no debe aparecer en el chat.
- **El frontend renderiza markdown mínimo** (`AnswerText` en `ChatDrawer.jsx`: negrita, cursiva, títulos) armando nodos de React, nunca HTML. También borra las marcas `【id】` que mete gpt-oss: las citas ya son botones.

### Configuración

`backend/config.py` (`Settings`, pydantic-settings) lee el `.env` de la raíz y se valida al importar: config inválida = no arranca. `.env.example` documenta cada variable con su default. `CORS_ORIGINS` rechaza `*` explícitamente. Las rutas relativas (`DATA_FILE`, `IA_CONFIG_DIR`) se resuelven desde la raíz del proyecto, no desde `backend/`.

La persona del asistente sale de `ia_config/*.txt` (`nombre`, `personalidad`, `instrucciones`, `conocimiento`). Las `RULES` de `agents/prompt.py` van al final del prompt a propósito: un 3B sigue mejor lo último que lee, y no llevan ejemplos con nombres propios porque el modelo los copia literal.

### Tests

`backend/tests/` usa `FakeLLM` y `FakeTools` (ver `conftest.py`) — sin red, sin Ollama, sin subprocesos. `asyncio_mode = auto`, así que los tests async no necesitan marca. `pytest.ini` convierte `MCPDeprecationWarning` en error: si el SDK de MCP deprecia algo, los tests fallan.

Los tests con FakeLLM no ven regresiones de calidad (alucinaciones, avisos falsos). Para eso está `evals/eval_agent.py`, que corre contra Ollama real y el servidor MCP en memoria, con escenarios de regex requeridos/prohibidos.

### Código legacy en la raíz

`server.py`, `client.py`, `web.py` e `index.html` son la versión anterior (stdlib + `requests`, sin FastAPI ni React) y siguen funcionando de forma independiente. No comparten código con `backend/`; solo comparten los datos (`fundacion.json`) y la persona (`ia_config/`). No los toques al trabajar en `backend/` o `frontend/`.

### Datos

`fundacion.json` es una lista de documentos (`id`, `titulo`, `contenido`, `tags`, `metadata`). El `id` se usa como ancla DOM en el lector del frontend, por eso el schema lo restringe a `^[A-Za-z0-9][A-Za-z0-9_-]*$`. El corpus presenta un **debate historiográfico abierto** sobre el año de fundación (1900 / 1903 / 1904): la regla 4 del prompt obliga a presentar todas las teorías con su fuente, sin elegir una.
