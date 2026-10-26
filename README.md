# Historia de Las Varillas

Chat sobre la historia de Las Varillas. El modelo responde solo con documentos que sirve un servidor MCP. Los libros viven en MongoDB.

## Requisitos

- Python 3.12 con venv en la raíz (`.venv/`).
- MongoDB 7.0 (Community local, o Atlas).
- Node.js para el frontend.
- Opcional: Ollama con un modelo local, o una key de Groq en `.env` para el modelo en la nube. Sin modelo, el chat responde `llm_unavailable`.

## Arranque

1. Instalá las dependencias del backend desde la raíz:

   ```bash
   python -m venv .venv
   .venv\Scripts\activate
   pip install -r backend/requirements-dev.txt
   ```

2. Copiá `.env.example` a `.env` y completá `MONGODB_URL`. Con Mongo local:

   ```bash
   copy .env.example .env
   ```

   ```
   MONGODB_URL=mongodb://127.0.0.1:27017/
   ```

3. Sembrá la base una vez, desde `backend/`:

   ```bash
   python -m scripts.seed_from_json --autor "<autor>" --anio <año>
   ```

   Crea el libro `debates-origen` publicado con los tres documentos de `fundacion.json`. Reejecutarla no duplica datos. Opciones: `--slug`, `--titulo`, `--fuente-tipo` y `--datos`.

4. Arrancá el backend, desde `backend/`:

   ```bash
   python main.py
   ```

   Escucha en `127.0.0.1:8000`. Sin libros publicados arranca igual y deja un warning `sin_libros_publicados` en el log.

5. Arrancá el frontend, desde la raíz:

   ```bash
   npm --prefix frontend install
   npm --prefix frontend run dev
   ```

   Vite sirve en `http://localhost:5173`.

## Pruebas

Desde `backend/`:

```bash
pytest
```

Sin `MONGODB_URL_TEST` se saltan las pruebas que necesitan Mongo real.

Contra Mongo real. Usa la base `historia_test` y la borra antes y después:

```bash
MONGODB_URL_TEST=mongodb://127.0.0.1:27017/ pytest
```

Frontend, desde la raíz:

```bash
npm --prefix frontend test
npm --prefix frontend run lint
```

## Estructura

- `backend/`: API FastAPI, servidor MCP (`mcp_server.py`), agente, repositorio de Mongo (`store/`) y siembra (`scripts/`).
- `frontend/`: lector y chat (React + Vite).
- `specs/`: especificaciones por parte del taller (spec, plan, tareas y verificación).
- `server.py`, `client.py`, `web.py`, `index.html`: versión anterior, independiente. No se tocan.

## Notas

- `.env` no va al repositorio. Ya está en `.gitignore`.
- La base de libros es la fuente de verdad. `fundacion.json` solo se usa para sembrar.
- El backend lee los libros al arrancar. Después de publicar un libro nuevo, reiniciá el backend para verlo en el prompt y en `/api/fundacion`. El MCP lo ve sin reiniciar.
