"""REST: /api/fundacion y /api/modelos. Lee HistoryStore directo, sin MCP: funciona aunque MCP esté caído."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
from llm.catalog import ProviderId
from pydantic import BaseModel, Field
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
    id: ProviderId
    nombre: str
    disponible: bool = Field(description="false: falta configuración (ej: GROQ_API_KEY)")


@router.get("/modelos", response_model=list[Modelo], summary="Modelos que ofrece el selector del chat")
def get_modelos(request: Request) -> list[Modelo]:
    # El catálogo lo arma main.py en el lifespan: qué proveedores existen y cuáles tienen cliente registrado.
    return [Modelo(id=info.id, nombre=info.nombre, disponible=info.disponible) for info in request.app.state.proveedores]
