"""REST: /api/fundacion. Lee HistoryStore directo, sin MCP: funciona aunque MCP esté caído."""

from typing import Annotated

from fastapi import APIRouter, Depends, Request
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
