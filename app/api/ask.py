from __future__ import annotations

from functools import lru_cache
from typing import Any, Literal

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field

from app.index_guard import ensure_index_ready
from core.answer import MAX_EVIDENCE, GroundedAnswerService

router = APIRouter(tags=["ask"])


class AskRequest(BaseModel):
    query: str = Field(min_length=1, max_length=500)
    top_k: int = Field(default=MAX_EVIDENCE, ge=1, le=MAX_EVIDENCE)


class AskResponse(BaseModel):
    query: str
    status: Literal["answered", "partial", "refused", "error"]
    answer: str
    citations: list[str]
    missing_parts: list[str]
    notes: list[str]
    refusal_reason: str | None
    generation_mode: str
    analysis: dict[str, Any]
    citation_validation: dict[str, Any]
    grounding_validation: dict[str, Any]
    evidence: list[dict[str, Any]]


@lru_cache(maxsize=1)
def get_answer_service() -> GroundedAnswerService:
    ensure_index_ready()
    return GroundedAnswerService()


@router.post("/ask", response_model=AskResponse)
def ask(
    request: AskRequest,
    service: GroundedAnswerService = Depends(get_answer_service),  # noqa: B008
) -> dict[str, Any]:
    return service.ask(request.query, top_k=request.top_k)
