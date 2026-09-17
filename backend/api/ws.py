"""WebSocket /ws/chat: transporte, validación, límites y estados. La lógica de agente vive en HistorianAgent."""

import asyncio
import logging
import unicodedata
import uuid
from typing import Annotated, Literal

from fastapi import APIRouter, WebSocket, WebSocketDisconnect
from pydantic import AfterValidator, BaseModel, ConfigDict, ValidationError

from agents.historian import Conversation, HistorianAgent, MaxIterationsExceeded
from api.ratelimit import TokenBucket
from config import Settings
from llm.provider import LLMError, LLMTimeout, LLMUnavailable
from logging_config import conn_id_var
from tools.registry import ToolsUnavailable

logger = logging.getLogger(__name__)
router = APIRouter()

MAX_TEXT_CHARS = 1000
_MAX_FRAME_CHARS = 8 * MAX_TEXT_CHARS
_WS_POLICY_VIOLATION = 1008
_WS_TRY_AGAIN_LATER = 1013
_BIDI_CONTROLS = dict.fromkeys(map(ord, "‪‫‬‭‮⁦⁧⁨⁩"))

ErrorCode = Literal[
    "llm_unavailable", "llm_timeout", "tools_unavailable", "busy",
    "rate_limited", "invalid_input", "max_iterations", "internal",
]


def sanitize_text(value: str) -> str:
    """NFC, sin caracteres de control (salvo \\n y \\t) ni overrides bidi, con límites de largo."""
    value = unicodedata.normalize("NFC", value)
    value = "".join(char for char in value if char in "\n\t" or unicodedata.category(char) != "Cc")
    value = value.translate(_BIDI_CONTROLS).strip()
    if not value:
        raise ValueError("el texto está vacío")
    if len(value) > MAX_TEXT_CHARS:
        raise ValueError(f"el texto supera {MAX_TEXT_CHARS} caracteres")
    return value


class ChatIn(BaseModel):
    """Cliente → servidor."""

    model_config = ConfigDict(extra="forbid")
    text: Annotated[str, AfterValidator(sanitize_text)]


class StatusEvent(BaseModel):
    """Servidor → cliente: estado del agente."""

    type: Literal["status"] = "status"
    state: Literal["thinking", "tool_call", "idle"]
    tool: str | None = None


class ResponseEvent(BaseModel):
    """Servidor → cliente: respuesta final del turno."""

    type: Literal["response"] = "response"
    content: str


class ErrorEvent(BaseModel):
    """Servidor → cliente: error apto para mostrar. El detalle técnico queda en el log."""

    type: Literal["error"] = "error"
    code: ErrorCode
    message: str


WS_SCHEMAS = (ChatIn, StatusEvent, ResponseEvent, ErrorEvent)


class _Channel:
    """Serializa envíos: el loop de recepción y la tarea del turno escriben en el mismo socket."""

    def __init__(self, websocket: WebSocket) -> None:
        self._websocket = websocket
        self._lock = asyncio.Lock()

    async def send(self, event: BaseModel) -> None:
        async with self._lock:
            try:
                await self._websocket.send_text(event.model_dump_json(exclude_none=True))
            except (WebSocketDisconnect, RuntimeError, OSError):
                pass  # el cliente se fue; el loop de recepción cierra la conexión


def _parse(text: str | None) -> ChatIn:
    if text is None or len(text) > _MAX_FRAME_CHARS:
        raise ValueError("frame inválido")
    try:
        return ChatIn.model_validate_json(text)
    except ValidationError as exc:
        raise ValueError(str(exc)) from exc


async def _run_turn(channel: _Channel, agent: HistorianAgent, conversation: Conversation, text: str) -> None:
    async def on_status(state: Literal["thinking", "tool_call"], tool: str | None) -> None:
        await channel.send(StatusEvent(state=state, tool=tool))

    event: BaseModel
    try:
        event = ResponseEvent(content=await agent.run(conversation, text, on_status))
    except ToolsUnavailable as exc:
        logger.error("turn_tools_unavailable", extra={"error": str(exc)})
        event = ErrorEvent(code="tools_unavailable", message="La base histórica no está disponible. Probá de nuevo en unos segundos.")
    except LLMTimeout as exc:
        logger.error("turn_llm_timeout", extra={"error": str(exc)})
        event = ErrorEvent(code="llm_timeout", message="El modelo tardó demasiado en responder. Probá de nuevo.")
    except LLMUnavailable as exc:
        logger.error("turn_llm_unavailable", extra={"error": str(exc)})
        event = ErrorEvent(code="llm_unavailable", message="El modelo de lenguaje no está disponible. Verificá que Ollama esté corriendo.")
    except MaxIterationsExceeded:
        event = ErrorEvent(code="max_iterations", message="No llegué a una respuesta final. Probá reformular la pregunta.")
    except LLMError as exc:
        logger.error("turn_llm_error", extra={"error": str(exc)})
        event = ErrorEvent(code="internal", message="El modelo devolvió una respuesta inválida. Probá reformular la pregunta.")
    except Exception:
        logger.exception("turn_failed")
        event = ErrorEvent(code="internal", message="Error interno al procesar la consulta.")
    await channel.send(event)
    await channel.send(StatusEvent(state="idle"))


@router.websocket("/ws/chat")
async def chat_socket(websocket: WebSocket) -> None:
    state = websocket.app.state
    settings: Settings = state.settings
    origin = websocket.headers.get("origin", "").rstrip("/")
    ip = websocket.client.host if websocket.client else "unknown"

    # Starlette no aplica CORS a WebSocket: sin este chequeo cualquier sitio abre el socket (CSWSH).
    # Se acepta antes de cerrar para que el cliente reciba 1008; sin accept vería 1006.
    await websocket.accept()
    if origin not in settings.cors_origins:
        logger.warning("ws_origin_rejected", extra={"origin": origin, "ip": ip})
        await websocket.close(code=_WS_POLICY_VIOLATION, reason="origin not allowed")
        return
    if not state.connections.acquire(ip):
        logger.warning("ws_connection_limit", extra={"ip": ip})
        await websocket.close(code=_WS_TRY_AGAIN_LATER, reason="too many connections")
        return

    token = conn_id_var.set(uuid.uuid4().hex[:8])
    channel = _Channel(websocket)
    conversation = state.agent.new_conversation()
    bucket = TokenBucket(settings.ws_rate_capacity, settings.ws_rate_refill_per_minute / 60)
    turn: asyncio.Task[None] | None = None
    logger.info("ws_connected", extra={"ip": ip, "origin": origin})
    try:
        while True:
            message = await websocket.receive()
            if message["type"] == "websocket.disconnect":
                break
            if not bucket.consume():
                await channel.send(ErrorEvent(code="rate_limited", message="Demasiados mensajes. Esperá unos segundos."))
                continue
            if turn is not None and not turn.done():
                await channel.send(ErrorEvent(code="busy", message="Todavía estoy respondiendo la consulta anterior."))
                continue
            try:
                incoming = _parse(message.get("text"))
            except ValueError as exc:
                logger.info("ws_invalid_input", extra={"error": str(exc)[:300]})
                await channel.send(ErrorEvent(code="invalid_input", message=f'Enviá {{"text": ...}} con 1 a {MAX_TEXT_CHARS} caracteres.'))
                continue
            turn = asyncio.create_task(_run_turn(channel, state.agent, conversation, incoming.text))
    except WebSocketDisconnect:
        pass
    finally:
        if turn is not None and not turn.done():
            turn.cancel()  # corta la request a Ollama de un cliente que ya no escucha
            await asyncio.gather(turn, return_exceptions=True)
        state.connections.release(ip)
        logger.info("ws_disconnected", extra={"ip": ip})
        conn_id_var.reset(token)
