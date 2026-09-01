"""Deterministic validators for answer bodies and formatted responses."""

from __future__ import annotations

import re
from datetime import date

from src.guardrails.models import DISCLAIMER, FOOTER_PREFIX, ValidationResult

ADVISORY_PHRASES: tuple[str, ...] = (
    "you should",
    "i recommend",
    "i suggest",
    "better than",
    "you must invest",
    "consider buying",
    "consider selling",
    "good investment",
    "will outperform",
)

_URL_RE = re.compile(r"https?://[^\s)>]+", re.IGNORECASE)
_SENTENCE_SPLIT_RE = re.compile(r"(?<=[.!?])\s+")
_FOOTER_DATE_RE = re.compile(
    rf"{re.escape(FOOTER_PREFIX)}\s*(\d{{4}}-\d{{2}}-\d{{2}})",
    re.IGNORECASE,
)


def count_sentences(text: str) -> int:
    cleaned = (text or "").strip()
    if not cleaned:
        return 0
    parts = [part.strip() for part in _SENTENCE_SPLIT_RE.split(cleaned) if part.strip()]
    return len(parts) if parts else 1


def contains_advisory_phrase(text: str) -> bool:
    lowered = (text or "").lower()
    return any(phrase in lowered for phrase in ADVISORY_PHRASES)


def extract_urls(text: str) -> list[str]:
    return _URL_RE.findall(text or "")


def validate_answer_body(body: str, *, max_sentences: int = 3) -> ValidationResult:
    errors: list[str] = []
    sentence_count = count_sentences(body)
    if sentence_count > max_sentences:
        errors.append(f"answer has {sentence_count} sentences; max is {max_sentences}")
    if contains_advisory_phrase(body):
        errors.append("answer contains advisory phrasing")
    return ValidationResult(ok=not errors, errors=tuple(errors))


def validate_formatted_response(
    text: str,
    *,
    expected_citation: str | None = None,
    require_footer: bool = True,
    max_sentences_in_body: int = 3,
) -> ValidationResult:
    errors: list[str] = []
    full = (text or "").strip()
    if not full:
        return ValidationResult(ok=False, errors=("empty response",))

    urls = extract_urls(full)
    if len(urls) != 1:
        errors.append(f"expected exactly one citation URL, found {len(urls)}")
    elif expected_citation and urls[0].rstrip(".,)") != expected_citation.rstrip(".,)"):
        errors.append("citation URL does not match expected Groww metadata URL")

    if require_footer and not _FOOTER_DATE_RE.search(full):
        errors.append("missing last-updated footer")

    if DISCLAIMER.lower() not in full.lower():
        errors.append("missing disclaimer")

    # Validate only the prose before Source:/footer markers when present.
    body = full.split("\nSource:", 1)[0].strip()
    body = body.split(f"\n{FOOTER_PREFIX}", 1)[0].strip()
    body_errors = validate_answer_body(body, max_sentences=max_sentences_in_body)
    errors.extend(body_errors.errors)

    return ValidationResult(ok=not errors, errors=tuple(errors))


def format_answered_response(
    body: str,
    *,
    citation_url: str,
    last_updated: str | date,
) -> str:
    """Canonical formatter for successful factual answers."""
    if isinstance(last_updated, date):
        updated = last_updated.isoformat()
    else:
        updated = str(last_updated)

    cleaned_body = body.strip()
    return (
        f"{cleaned_body}\n\n"
        f"Source: {citation_url}\n"
        f"{FOOTER_PREFIX} {updated}\n\n"
        f"{DISCLAIMER}"
    )
