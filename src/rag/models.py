"""RAG response types."""

from __future__ import annotations

from dataclasses import dataclass

from src.guardrails.models import DISCLAIMER, GuardrailResponse, Intent, ResponseStatus


@dataclass(frozen=True)
class AskResponse:
    status: ResponseStatus
    answer: str
    citation_url: str | None
    last_updated: str | None
    disclaimer: str = DISCLAIMER
    intent: Intent | None = None

    def to_dict(self) -> dict[str, str | None]:
        return {
            "status": self.status,
            "answer": self.answer,
            "citation_url": self.citation_url,
            "last_updated": self.last_updated,
            "disclaimer": self.disclaimer,
        }


def from_guardrail(response: GuardrailResponse) -> AskResponse:
    return AskResponse(
        status=response.status,
        answer=response.answer,
        citation_url=response.citation_url,
        last_updated=response.last_updated,
        disclaimer=response.disclaimer,
        intent=response.intent,
    )
