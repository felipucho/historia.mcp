"""FastAPI app: arma dependencias en el lifespan y monta routers. Sin lógica de negocio.

Arranque (desde backend/, con .venv activo): python main.py
"""

import asyncio
import logging
import sys
from collections.abc import AsyncIterator
from contextlib import asynccontextmanager
from typing import Any

import uvicorn
from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware
from fastapi.openapi.utils import get_openapi
from mcp import StdioServerParameters

from agents.historian import HistorianAgent
from agents.prompt import build_system_prompt
from api import rest, ws
from api.ratelimit import ConnectionLimiter
from config import BACKEND_DIR, Settings
from llm.ollama import OllamaClient
from llm.openai_compat import OpenAICompatClient
from llm.provider import LLMError, LLMProvider
from logging_config import setup_logging
from store.history import HistoryStore, HistoryStoreError, render_index
from tools.registry import McpToolRegistry, ToolsUnavailable

settings = Settings()
setup_logging(settings.log_level)
logger = logging.getLogger("backend")


async def _warm_up(llm: LLMProvider) -> None:
    try:
        await llm.warm_up()
    except LLMError as exc:
        logger.warning("ollama_warm_up_failed", extra={"error": str(exc)})


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    try:
        store = HistoryStore.from_file(settings.data_file)
    except HistoryStoreError as exc:
        logger.critical("data_invalid", extra={"error": str(exc)})
        raise
    logger.info("store_loaded", extra={"documents": len(store.documents), "file": str(settings.data_file)})

    llm = OllamaClient(
        settings.ollama_base_url,
        settings.ollama_model,
        num_ctx=settings.ollama_num_ctx,
        keep_alive=settings.ollama_keep_alive,
        connect_timeout=settings.ollama_connect_timeout,
        read_timeout=settings.ollama_read_timeout,
        temperature=settings.ollama_temperature,
    )
    cloud = OpenAICompatClient(
        settings.groq_base_url,
        settings.groq_model,
        settings.groq_api_key,
        temperature=settings.cloud_temperature,
        connect_timeout=settings.ollama_connect_timeout,
        read_timeout=settings.cloud_read_timeout,
    )
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
    warm_up: asyncio.Task[None] | None = None
    try:
        try:
            await llm.health()
            logger.info("ollama_ready", extra={"model": settings.ollama_model, "url": settings.ollama_base_url})
            warm_up = asyncio.create_task(_warm_up(llm))
        except LLMError as exc:
            if settings.ollama_required:
                logger.critical("ollama_required_unavailable", extra={"error": str(exc)})
                raise
            logger.error("ollama_unavailable_at_startup", extra={"error": str(exc), "effect": "chat responde llm_unavailable"})
        try:
            await tools.connect()
        except ToolsUnavailable:
            logger.error("mcp_unavailable_at_startup", extra={"effect": "chat responde tools_unavailable; reintento por mensaje"})

        system_prompt = build_system_prompt(settings.ia_config_dir, render_index(store.documents))
        app.state.settings = settings
        app.state.store = store
        # Sin key el proveedor "cloud" no se registra: el agente responde provider_unavailable.
        llms: dict[str, LLMProvider] = {"local": llm}
        if settings.groq_api_key:
            llms["cloud"] = cloud
            logger.info("cloud_llm_configured", extra={"model": settings.groq_model})
        app.state.agent = HistorianAgent(
            llms,
            tools,
            system_prompt,
            max_iterations=settings.agent_max_iterations,
            max_turns=settings.history_max_turns,
        )
        app.state.connections = ConnectionLimiter(settings.ws_max_connections_per_ip)
        yield
    finally:
        if warm_up is not None:
            warm_up.cancel()
            await asyncio.gather(warm_up, return_exceptions=True)
        await tools.aclose()
        await llm.aclose()
        await cloud.aclose()
        logger.info("shutdown_complete")


WS_DESCRIPTION = """
### WebSocket `/ws/chat`
OpenAPI no describe WebSockets: el contrato está en los schemas `ChatIn`, `StatusEvent`, `DeltaEvent`, `ResponseEvent` y `ErrorEvent`.

- Entrada: `ChatIn` → `{"text": "...", "provider": "local" | "cloud"}` (1 a 1000 caracteres; provider opcional, default `local`).
- Salida: `StatusEvent` | `DeltaEvent` | `ResponseEvent` | `ErrorEvent`. Los `delta` llegan mientras el modelo escribe; el `response` final trae el texto completo.
- Origin fuera de `CORS_ORIGINS` → cierre `1008`.
"""

app = FastAPI(title="Historia de Las Varillas", version="1.0.0", description=WS_DESCRIPTION, lifespan=lifespan)
app.add_middleware(CORSMiddleware, allow_origins=settings.cors_origins, allow_methods=["GET"], allow_headers=[])
app.include_router(rest.router)
app.include_router(ws.router)


def _openapi() -> dict[str, Any]:
    if app.openapi_schema is None:
        schema = get_openapi(title=app.title, version=app.version, description=app.description, routes=app.routes)
        components = schema.setdefault("components", {}).setdefault("schemas", {})
        for model in ws.WS_SCHEMAS:
            components[model.__name__] = model.model_json_schema(ref_template="#/components/schemas/{model}")
        app.openapi_schema = schema
    return app.openapi_schema


app.openapi = _openapi  # type: ignore[method-assign]


if __name__ == "__main__":
    uvicorn.run(
        app,
        host=settings.backend_host,
        port=settings.backend_port,
        log_config=None,
        ws_max_size=16 * 1024,  # default 16 MB: un frame gigante se parsearía entero
    )
