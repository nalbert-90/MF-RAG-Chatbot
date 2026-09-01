"""Pydantic request/response models for the FastAPI layer."""

from __future__ import annotations

from typing import Literal

from pydantic import BaseModel, Field, field_validator

from src.guardrails.models import DISCLAIMER

AskStatus = Literal["answered", "refused", "redirected"]


class AskRequest(BaseModel):
    question: str = Field(..., min_length=1)

    @field_validator("question")
    @classmethod
    def question_must_not_be_blank(cls, value: str) -> str:
        stripped = value.strip()
        if not stripped:
            raise ValueError("question must not be blank")
        return stripped


class AskResponseBody(BaseModel):
    status: AskStatus
    answer: str
    citation_url: str | None
    last_updated: str | None
    disclaimer: str = DISCLAIMER


class HealthResponse(BaseModel):
    status: Literal["ok"]


class SchemeItem(BaseModel):
    scheme_id: str
    name: str
    category: str
    groww_url: str


class SchemesResponse(BaseModel):
    schemes: list[SchemeItem]


class ExamplesResponse(BaseModel):
    questions: list[str]
