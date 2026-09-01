"""Map natural-language queries to one of the five curated scheme_ids."""

from __future__ import annotations

import re
from functools import lru_cache

from src.registry import load_schemes


@lru_cache
def _scheme_lookup() -> list[tuple[str, str, tuple[str, ...]]]:
    """Return (scheme_id, normalized name, aliases) sorted longest match first."""
    rows: list[tuple[str, str, tuple[str, ...]]] = []
    for scheme in load_schemes():
        scheme_id = scheme["scheme_id"]
        name = scheme["name"]
        aliases = tuple(scheme.get("aliases") or [])
        rows.append((scheme_id, _normalize(name), tuple(_normalize(a) for a in aliases)))
    rows.sort(key=lambda row: max(len(row[1]), max((len(a) for a in row[2]), default=0)), reverse=True)
    return rows


def _normalize(text: str) -> str:
    lowered = text.lower().strip()
    lowered = re.sub(r"[^\w\s-]", " ", lowered)
    return re.sub(r"\s+", " ", lowered).strip()


def resolve_scheme_id(question: str) -> str | None:
    """Return scheme_id when exactly one scheme matches; None if ambiguous or unknown."""
    normalized = _normalize(question)
    if not normalized:
        return None

    matches: list[str] = []
    for scheme_id, name, aliases in _scheme_lookup():
        candidates = (name, *aliases)
        if any(token and token in normalized for token in candidates):
            matches.append(scheme_id)

    unique = list(dict.fromkeys(matches))
    if len(unique) == 1:
        return unique[0]
    return None


def groww_url_for_scheme(scheme_id: str) -> str | None:
    for scheme in load_schemes():
        if scheme["scheme_id"] == scheme_id:
            return scheme["groww_url"]
    return None
