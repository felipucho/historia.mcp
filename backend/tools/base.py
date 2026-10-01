"""Contrato de herramientas. Sin dependencias del SDK MCP: el agente y la API importan solo esto."""

from abc import ABC, abstractmethod
from typing import Any

from llm.provider import ToolSpec


class ToolError(Exception):
    """La herramienta falló. El mensaje vuelve al modelo como resultado de la tool."""


class ToolsUnavailable(Exception):
    """El backend de herramientas no está disponible."""


class ToolRegistry(ABC):
    @abstractmethod
    async def specs(self) -> list[ToolSpec]:
        """Tools disponibles. Lanza ToolsUnavailable."""

    @abstractmethod
    async def call(self, name: str, arguments: dict[str, Any], *, user_question: str | None = None) -> str:
        """Ejecuta una tool. Lanza ToolError o ToolsUnavailable."""
