"""Strip reasoning/thinking blocks from Groq model output (e.g. Qwen 3.6)."""

from __future__ import annotations

import re

_THINKING_BLOCK_RE = re.compile(
    r"<(?:redacted_)?think(?:ing)?>.*?(?:</(?:redacted_)?think(?:ing)?>|$)",
    re.DOTALL | re.IGNORECASE,
)
_EXTRACT_PATTERNS: tuple[re.Pattern[str], ...] = (
    re.compile(
        r"Draft Response:\**\s*(.+?)(?:\n\s*\d+\.\s|\n\s*Check Constraints|\Z)",
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(
        r"Final Output Generation:\**\s*(.+?)(?:\s*✅|\n|\Z)",
        re.DOTALL | re.IGNORECASE,
    ),
    re.compile(
        r"Formulate Answer:\**\s*(.+?)(?:\n\s*\d+\.\s|\Z)",
        re.DOTALL | re.IGNORECASE,
    ),
)
_MARKDOWN_BOLD_RE = re.compile(r"\*\*(.+?)\*\*")
_TRAILING_CHECKMARK_RE = re.compile(r"\s*✅\s*$")
_META_PAREN_RE = re.compile(
    r'\s*\([^)]*(?:matches|constraints|check|valid|perfectly)[^)]*\)\s*$',
    re.IGNORECASE,
)
_QUOTED_ANSWER_RE = re.compile(r'^["\'](.+)["\'](?:\s*\([^)]*\))?\s*$', re.DOTALL)
_META_PLACEHOLDER_RE = re.compile(
    r"(?:^\(?\s*)?just the answer(?:\s+text)?\s*\)?$|"
    r"final answer text|"
    r"^output only\b",
    re.IGNORECASE,
)


def _strip_markdown(text: str) -> str:
    cleaned = _MARKDOWN_BOLD_RE.sub(r"\1", text)
    cleaned = _TRAILING_CHECKMARK_RE.sub("", cleaned)
    return cleaned.strip()


def _clean_surface_text(text: str) -> str:
    cleaned = text.strip()
    quoted = _QUOTED_ANSWER_RE.match(cleaned)
    if quoted:
        cleaned = quoted.group(1).strip()
    cleaned = _META_PAREN_RE.sub("", cleaned).strip()
    return cleaned


def _extract_from_reasoning(raw: str) -> str:
    for pattern in _EXTRACT_PATTERNS:
        match = pattern.search(raw)
        if match:
            candidate = _strip_markdown(match.group(1).strip())
            if candidate:
                return candidate
    return ""


def sanitize_model_output(text: str) -> str:
    """Return user-facing model text without chain-of-thought wrappers."""
    raw = (text or "").strip()
    if not raw:
        return ""

    cleaned = _strip_markdown(_THINKING_BLOCK_RE.sub("", raw).strip())
    if cleaned:
        return _clean_surface_text(cleaned)

    extracted = _extract_from_reasoning(raw)
    if extracted:
        return _clean_surface_text(extracted)

    return ""


def is_meta_placeholder_answer(text: str) -> bool:
    """True when the model echoed prompt scaffolding instead of a factual answer."""
    cleaned = (text or "").strip()
    if not cleaned:
        return True
    return bool(_META_PLACEHOLDER_RE.search(cleaned))
