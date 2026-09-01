"""Query classification, refusals, and validators (Phase 2)."""

from src.guardrails.classifier import (
    CLASSIFY_SYSTEM_PROMPT,
    classify_by_rules,
    classify_intent,
    classify_with_groq,
)
from src.guardrails.models import (
    DISCLAIMER,
    FOOTER_PREFIX,
    ClassificationResult,
    GuardrailResponse,
    Intent,
    ResponseStatus,
    ValidationResult,
)
from src.guardrails.pii import contains_pii
from src.guardrails.refusals import (
    build_advisory_refusal,
    build_guardrail_response,
    build_groq_error_refusal,
    build_index_not_ready_refusal,
    build_insufficient_evidence_refusal,
    build_out_of_scope_refusal,
    build_performance_redirect,
    build_pii_refusal,
    build_scheme_unresolved_refusal,
)
from src.guardrails.scheme_resolver import groww_url_for_scheme, resolve_scheme_id
from src.guardrails.validators import (
    ADVISORY_PHRASES,
    count_sentences,
    format_answered_response,
    validate_answer_body,
    validate_formatted_response,
)


def evaluate_guardrails(
    question: str,
    *,
    groq_client=None,
    use_groq: bool = True,
) -> GuardrailResponse | None:
    """Return a short-circuit response when the query must not reach RAG generation."""
    result = classify_intent(question, groq_client=groq_client, use_groq=use_groq)
    return build_guardrail_response(result.intent, scheme_id=result.scheme_id)


__all__ = [
    "ADVISORY_PHRASES",
    "CLASSIFY_SYSTEM_PROMPT",
    "DISCLAIMER",
    "FOOTER_PREFIX",
    "ClassificationResult",
    "GuardrailResponse",
    "Intent",
    "ResponseStatus",
    "ValidationResult",
    "build_advisory_refusal",
    "build_guardrail_response",
    "build_groq_error_refusal",
    "build_index_not_ready_refusal",
    "build_insufficient_evidence_refusal",
    "build_out_of_scope_refusal",
    "build_performance_redirect",
    "build_pii_refusal",
    "build_scheme_unresolved_refusal",
    "classify_by_rules",
    "classify_intent",
    "classify_with_groq",
    "contains_pii",
    "count_sentences",
    "evaluate_guardrails",
    "format_answered_response",
    "groww_url_for_scheme",
    "resolve_scheme_id",
    "validate_answer_body",
    "validate_formatted_response",
]
