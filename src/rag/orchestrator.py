"""RAG orchestrator: classify → retrieve → generate → validate → format."""

from __future__ import annotations

import re
from typing import Any

from src.guardrails.classifier import classify_intent
from src.guardrails.models import Intent
from src.guardrails.refusals import (
    build_guardrail_response,
    build_groq_error_refusal,
    build_index_not_ready_refusal,
    build_insufficient_evidence_refusal,
    build_scheme_unresolved_refusal,
)
from src.guardrails.scheme_resolver import resolve_scheme_id
from src.guardrails.validators import validate_answer_body
from src.ingest.embed_index import IndexNotReadyError
from src.rag.generator import generate_answer
from src.rag.models import AskResponse, from_guardrail
from src.rag.output_sanitize import is_meta_placeholder_answer
from src.rag.retriever import (
    RetrievalHit,
    retrieve_for_question,
    select_hits_for_facts,
)


def ask(
    question: str,
    *,
    groq_client: Any | None = None,
    use_groq: bool = True,
    collection: Any | None = None,
) -> AskResponse:
    """End-to-end ask flow for factual and guarded non-factual queries."""
    text = (question or "").strip()
    if not text:
        return from_guardrail(build_scheme_unresolved_refusal())

    classification = classify_intent(
        text,
        groq_client=groq_client,
        use_groq=use_groq and groq_client is not None,
    )
    guardrail = build_guardrail_response(
        classification.intent,
        scheme_id=classification.scheme_id,
    )
    if guardrail is not None:
        return from_guardrail(guardrail)

    scheme_id = resolve_scheme_id(text)
    if not scheme_id:
        return from_guardrail(build_scheme_unresolved_refusal())

    try:
        retrieval = retrieve_for_question(
            text,
            scheme_id=scheme_id,
            collection=collection,
        )
    except IndexNotReadyError:
        return from_guardrail(build_index_not_ready_refusal())

    if not retrieval.sufficient or not retrieval.hits:
        return from_guardrail(build_insufficient_evidence_refusal())

    hits = list(retrieval.hits)
    target_facts = list(retrieval.target_facts)
    context_hits = _build_context_hits(hits, target_facts)
    primary = context_hits[0]
    citation_url = primary.citation_url
    last_updated = primary.published_or_as_of

    if use_groq and groq_client is None:
        return from_guardrail(build_groq_error_refusal())

    body = _generate_validated_body(
        text,
        context_hits,
        groq_client=groq_client,
        use_groq=use_groq,
    )
    if body is None:
        return from_guardrail(build_insufficient_evidence_refusal())

    if _is_missing_fact_response(body):
        return from_guardrail(build_insufficient_evidence_refusal())

    return AskResponse(
        status="answered",
        answer=body,
        citation_url=citation_url,
        last_updated=last_updated,
        intent=Intent.FACTUAL,
    )


def _build_context_hits(
    hits: list[RetrievalHit],
    target_facts: list[str],
) -> list[RetrievalHit]:
    """Prefer fact-matched chunks for Groq context when targets are known."""
    if not target_facts:
        return hits
    matched = select_hits_for_facts(hits, target_facts)
    if len(target_facts) > 1:
        return matched if len(matched) == len(target_facts) else hits
    return matched if matched else hits


def _generate_validated_body(
    question: str,
    hits: list[RetrievalHit],
    *,
    groq_client: Any | None,
    use_groq: bool,
) -> str | None:
    if not use_groq:
        return _fallback_body_from_hits(hits)

    assert groq_client is not None
    try:
        body = generate_answer(question, hits, groq_client, strict_retry=False)
    except Exception:
        body = ""

    if body and _is_usable_answer(body, hits):
        return body.strip()

    try:
        retry_body = generate_answer(
            question,
            hits,
            groq_client,
            strict_retry=True,
        )
    except Exception:
        retry_body = ""

    if retry_body and _is_usable_answer(retry_body, hits):
        return retry_body.strip()

    # Groq returned unusable reasoning-only output — fall back to retrieved facts.
    return _fallback_body_from_hits(hits)


_DIGIT_RE = re.compile(r"\d")


def _answer_lacks_retrieved_facts(body: str, hits: list[RetrievalHit]) -> bool:
    """Reject answers with no numbers when retrieved chunks contain numeric facts."""
    if _DIGIT_RE.search(body):
        return False
    return any(_DIGIT_RE.search(hit.text) for hit in hits)


def _is_usable_answer(body: str, hits: list[RetrievalHit]) -> bool:
    if not body or not validate_answer_body(body).ok:
        return False
    if is_meta_placeholder_answer(body):
        return False
    if _answer_lacks_retrieved_facts(body, hits):
        return False
    return True


def _fallback_body_from_hits(hits: list[RetrievalHit]) -> str:
    """Deterministic answer from one or more retrieved fact atoms (max 3 sentences)."""
    sentences: list[str] = []
    for hit in hits[:3]:
        text = hit.text.strip()
        if ". " in text:
            _, fact = text.split(". ", 1)
            sentence = fact.strip().rstrip(".") + "."
        else:
            sentence = text.rstrip(".") + "."
        sentences.append(sentence)
    return " ".join(sentences)


def _is_missing_fact_response(body: str) -> bool:
    lowered = body.lower()
    return "do not have that fact" in lowered or "don't have that fact" in lowered
