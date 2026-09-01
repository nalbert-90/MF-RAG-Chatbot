"""Query-time retriever for groww_scheme_facts.

Embeds the question with the same MiniLM used at ingest. When scheme_id is
known, always filter {scheme_id, source_org=groww, doc_type=scheme_page}.
Does not filter on section — MiniLM ranks TER vs SIP inside the scheme set.
"""

from __future__ import annotations

import re
from dataclasses import dataclass
from typing import Any

from src.config import get_settings
from src.ingest.allowlist import ALLOWED_DOC_TYPE, ALLOWED_SOURCE_ORG
from src.ingest.embed_index import (
    IndexNotReadyError,
    get_embedding_function,
    open_index,
)

DEFAULT_TOP_K = 3
MAX_TOP_K = 5

_cached_collection: Any | None = None

# Cosine distance ceiling calibrated above P1 filtered-probe rank-1 distances.
DEFAULT_MAX_DISTANCE = 1.15

_SECTION_KEYWORDS: tuple[tuple[str, ...], str] = (
    (("riskometer", "risk level", "risk rating"), "riskometer"),
    (
        ("expense ratio", "expnse ratio", " expnse ", " ter ", "total expense"),
        "expense_ratio",
    ),
    (("exit load", "redemption charge"), "exit_load"),
    (("minimum sip", "min sip", "min. for sip", "sip minimum"), "sip"),
    (("lock-in", "lock in", "lockin"), "lock_in"),
    (("benchmark",), "benchmark"),
    (("stamp duty", "tax implication"), "process"),
    (("nav", "net asset value"), "other::nav"),
    (("rating",), "other::rating"),
    (("aum", "fund size"), "other::aum"),
    (("fund manager", "fund management"), "other::managers"),
)


@dataclass(frozen=True)
class RetrievalHit:
    chunk_id: str
    scheme_id: str
    section: str
    text: str
    citation_url: str
    published_or_as_of: str
    title: str
    distance: float
    rank: int


@dataclass(frozen=True)
class RetrievalResult:
    hits: tuple[RetrievalHit, ...]
    scheme_id: str
    target_section: str | None
    target_facts: tuple[str, ...]
    sufficient: bool
    reason: str | None = None


def clamp_top_k(top_k: int) -> int:
    return max(1, min(int(top_k), MAX_TOP_K))


def get_shared_collection() -> Any:
    """Process-local Chroma collection (avoids reopening the index per request)."""
    global _cached_collection
    if _cached_collection is None:
        _cached_collection = open_index(create=False).collection
    return _cached_collection


def warmup_retriever() -> None:
    """Preload MiniLM embeddings and open the vector index at API startup."""
    get_embedding_function()
    get_shared_collection()


def build_where(*, scheme_id: str | None = None) -> dict[str, Any]:
    """Always constrain to the Groww scheme-page corpus; scheme_id when known."""
    clauses: list[dict[str, str]] = [
        {"source_org": ALLOWED_SOURCE_ORG},
        {"doc_type": ALLOWED_DOC_TYPE},
    ]
    if scheme_id:
        clauses.append({"scheme_id": scheme_id})
    if len(clauses) == 1:
        return clauses[0]
    return {"$and": clauses}


def infer_target_facts(question: str) -> list[str]:
    """Map fact keywords to chunk keys; returns all matches for multi-fact queries."""
    normalized = re.sub(r"\s+", " ", (question or "").lower())
    if not normalized:
        return []
    padded = f" {normalized} "
    matches: list[tuple[int, str]] = []
    for keywords, fact_key in _SECTION_KEYWORDS:
        positions = [
            padded.find(keyword)
            for keyword in keywords
            if keyword in padded
        ]
        if not positions:
            continue
        matches.append((min(positions), fact_key))
    matches.sort(key=lambda item: item[0])
    facts: list[str] = []
    for _, fact_key in matches:
        if fact_key not in facts:
            facts.append(fact_key)
    return facts


def infer_target_section(question: str) -> str | None:
    """Single primary section for backward-compatible probes (first matched fact)."""
    facts = infer_target_facts(question)
    if not facts:
        return None
    if len(facts) > 1:
        return None
    fact_key = facts[0]
    if fact_key == "riskometer":
        return "riskometer"
    if "::" in fact_key:
        return fact_key.split("::", 1)[0]
    return fact_key


def hit_matches_fact(hit: RetrievalHit, fact_key: str) -> bool:
    if "::" in fact_key:
        section, atom = fact_key.split("::", 1)
        return hit.section == section and hit.chunk_id.endswith(f"::{atom}")
    return hit.section == fact_key


def select_hits_for_facts(
    hits: list[RetrievalHit],
    fact_keys: list[str],
) -> list[RetrievalHit]:
    """Pick the best hit per requested fact key, preserving query order."""
    selected: list[RetrievalHit] = []
    for fact_key in fact_keys:
        match = next((hit for hit in hits if hit_matches_fact(hit, fact_key)), None)
        if match is not None and match not in selected:
            selected.append(match)
    return selected


def retrieve(
    query: str,
    *,
    scheme_id: str | None = None,
    top_k: int = DEFAULT_TOP_K,
    chroma_path: Any | None = None,
    collection: Any | None = None,
    embedding_function: Any | None = None,
) -> list[RetrievalHit]:
    """Return cosine-distance hits. Lower distance is better. No Groq."""
    question = (query or "").strip()
    if not question:
        raise ValueError("query must be non-empty.")

    n_results = clamp_top_k(top_k)
    if collection is None and chroma_path is None:
        collection = get_shared_collection()
    elif collection is None:
        opened = open_index(
            chroma_path=chroma_path,
            create=False,
            embedding_function=embedding_function or get_embedding_function(),
        )
        collection = opened.collection

    where = build_where(scheme_id=scheme_id)
    try:
        raw = collection.query(
            query_texts=[question],
            n_results=n_results,
            where=where,
            include=["documents", "metadatas", "distances"],
        )
    except IndexNotReadyError:
        raise
    except Exception as exc:
        message = str(exc).lower()
        if "not found" in message or "does not exist" in message:
            raise IndexNotReadyError(
                "Index not ready. Run `python -m src.ingest.run --rebuild`."
            ) from exc
        raise

    ids = (raw.get("ids") or [[]])[0]
    documents = (raw.get("documents") or [[]])[0]
    metadatas = (raw.get("metadatas") or [[]])[0]
    distances = (raw.get("distances") or [[]])[0]

    hits: list[RetrievalHit] = []
    for rank, chunk_id in enumerate(ids, start=1):
        meta = metadatas[rank - 1] if rank - 1 < len(metadatas) else None
        meta = meta or {}
        text = documents[rank - 1] if rank - 1 < len(documents) else ""
        distance = distances[rank - 1] if rank - 1 < len(distances) else 0.0
        hits.append(
            RetrievalHit(
                chunk_id=str(chunk_id),
                scheme_id=str(meta.get("scheme_id") or ""),
                section=str(meta.get("section") or ""),
                text=str(text or ""),
                citation_url=str(meta.get("citation_url") or ""),
                published_or_as_of=str(meta.get("published_or_as_of") or ""),
                title=str(meta.get("title") or ""),
                distance=float(distance),
                rank=rank,
            )
        )
    return hits


def is_retrieval_sufficient(
    hits: list[RetrievalHit],
    *,
    question: str,
    max_distance: float | None = None,
) -> tuple[bool, str | None]:
    """Decide whether retrieved context is strong enough to ground generation."""
    if not hits:
        return False, "no retrieval hits"

    settings = get_settings()
    ceiling = (
        settings.retrieval_max_distance
        if max_distance is None
        else max_distance
    )
    best = hits[0]
    if best.distance > ceiling:
        return False, f"best distance {best.distance:.4f} exceeds {ceiling:.4f}"

    target_facts = infer_target_facts(question)
    if not target_facts:
        return True, None

    if "riskometer" in target_facts:
        return False, "riskometer is not in the curated corpus"

    if len(target_facts) > 1:
        missing = [
            fact
            for fact in target_facts
            if not any(hit_matches_fact(hit, fact) for hit in hits)
        ]
        if missing:
            return False, f"no chunk for {missing[0]!r} in top-{len(hits)}"
        return True, None

    fact_key = target_facts[0]
    matching = [hit for hit in hits if hit_matches_fact(hit, fact_key)]
    if not matching:
        return False, f"no chunk for {fact_key!r} in top-{len(hits)}"

    return True, None


def retrieve_for_question(
    question: str,
    *,
    scheme_id: str,
    top_k: int | None = None,
    max_distance: float | None = None,
    chroma_path: Any | None = None,
    collection: Any | None = None,
    embedding_function: Any | None = None,
) -> RetrievalResult:
    """Retrieve with required scheme filter and sufficiency check."""
    settings = get_settings()
    target_facts = infer_target_facts(question)
    k = top_k if top_k is not None else settings.retrieval_top_k
    if len(target_facts) > 1:
        k = max(k, min(len(target_facts) + 1, MAX_TOP_K))
    hits = retrieve(
        question,
        scheme_id=scheme_id,
        top_k=k,
        chroma_path=chroma_path,
        collection=collection,
        embedding_function=embedding_function,
    )
    target = infer_target_section(question)
    sufficient, reason = is_retrieval_sufficient(
        hits,
        question=question,
        max_distance=max_distance,
    )
    return RetrievalResult(
        hits=tuple(hits),
        scheme_id=scheme_id,
        target_section=target,
        target_facts=tuple(target_facts),
        sufficient=sufficient,
        reason=reason,
    )
