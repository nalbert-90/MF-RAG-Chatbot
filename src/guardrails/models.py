from __future__ import annotations

from dataclasses import dataclass
from enum import Enum
from typing import Literal

ResponseStatus = Literal["answered", "refused", "redirected"]

DISCLAIMER = "Facts-only. No investment advice."
FOOTER_PREFIX = "Last updated from sources:"


class Intent(str, Enum):
    FACTUAL = "factual"
    ADVISORY = "advisory"
    PERFORMANCE = "performance"
    PII_RISK = "pii_risk"
    OUT_OF_SCOPE = "out_of_scope"


@dataclass(frozen=True)
class ClassificationResult:
    intent: Intent
    source: str  # "pii" | "rules" | "groq" | "fallback"
    scheme_id: str | None = None


@dataclass(frozen=True)
class GuardrailResponse:
    status: ResponseStatus
    answer: str
    citation_url: str | None
    last_updated: str | None
    intent: Intent
    disclaimer: str = DISCLAIMER


@dataclass(frozen=True)
class ValidationResult:
    ok: bool
    errors: tuple[str, ...] = ()
