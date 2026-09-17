"""Logging JSON centralizado. El conn_id viaja por contextvar: el agente loguea con contexto sin conocer el transporte."""

import json
import logging
import sys
from contextvars import ContextVar
from datetime import datetime, timezone
from typing import TextIO

conn_id_var: ContextVar[str | None] = ContextVar("conn_id", default=None)

_RESERVED = set(vars(logging.makeLogRecord({}))) | {"message", "asctime", "taskName", "color_message"}


class JsonFormatter(logging.Formatter):
    def format(self, record: logging.LogRecord) -> str:
        payload: dict[str, object] = {
            "ts": datetime.fromtimestamp(record.created, timezone.utc).isoformat(timespec="milliseconds"),
            "level": record.levelname,
            "logger": record.name,
            "msg": record.getMessage(),
        }
        if (conn_id := conn_id_var.get()) is not None:
            payload["conn_id"] = conn_id
        payload.update({key: value for key, value in vars(record).items() if key not in _RESERVED})
        if record.exc_info:
            payload["exc"] = self.formatException(record.exc_info)
        return json.dumps(payload, ensure_ascii=False, default=str)


def setup_logging(level: str, stream: TextIO = sys.stdout) -> None:
    """stream=sys.stderr en el servidor MCP: su stdout es el canal del protocolo."""
    try:
        stream.reconfigure(encoding="utf-8")  # consola Windows en cp1252
    except (AttributeError, ValueError):
        pass
    handler = logging.StreamHandler(stream)
    handler.setFormatter(JsonFormatter())
    root = logging.getLogger()
    root.handlers[:] = [handler]
    root.setLevel(level)
    for name in ("uvicorn", "uvicorn.error", "uvicorn.access"):
        uvicorn_logger = logging.getLogger(name)
        uvicorn_logger.handlers.clear()
        uvicorn_logger.propagate = True
    for noisy in ("httpx", "httpcore", "mcp"):
        logging.getLogger(noisy).setLevel(max(logging.WARNING, logging.getLevelName(level)))
