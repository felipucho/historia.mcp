"""REST: /api/fundacion y /api/modelos. Lee HistoryStore directo, sin MCP: funciona aunque MCP esté caído."""

from typing import Annotated, Literal

from fastapi import APIRouter, Depends, Request
from pydantic import BaseModel, Field

from config import Settings
from store.history import Documento, HistoryStore

router = APIRouter(prefix="/api", tags=["fundacion"])


class FundacionResponse(BaseModel):
    raw: list[Documento] = Field(description="Documentos estructurados; el lector usa `id` como ancla")
    full_text: str = Field(description="Narrativa concatenada: `## titulo\\ncontenido` por documento")


def get_store(request: Request) -> HistoryStore:
    return request.app.state.store


@router.get("/fundacion", response_model=FundacionResponse, summary="Corpus histórico completo")
def get_fundacion(store: Annotated[HistoryStore, Depends(get_store)]) -> FundacionResponse:
    return FundacionResponse(raw=list(store.documents), full_text=store.full_text)


class Modelo(BaseModel):
    id: Literal["local", "cloud"]
    nombre: str
    disponible: bool = Field(description="false: falta configuración (ej: GROQ_API_KEY)")


def get_settings(request: Request) -> Settings:
    return request.app.state.settings


@router.get("/modelos", response_model=list[Modelo], summary="Modelos que ofrece el selector del chat")
def get_modelos(settings: Annotated[Settings, Depends(get_settings)]) -> list[Modelo]:
    return [
        Modelo(id="local", nombre=f"Local · {settings.ollama_model}", disponible=True),
        Modelo(id="cloud", nombre=f"Nube · {settings.groq_model}", disponible=bool(settings.groq_api_key)),
    ]
