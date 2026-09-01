"""Template refusals and performance redirects."""

from __future__ import annotations

from src.guardrails.models import DISCLAIMER, GuardrailResponse, Intent
from src.guardrails.scheme_resolver import groww_url_for_scheme
from src.registry import load_educational_links


def _default_education_url() -> str:
    data = load_educational_links()
    return str(data.get("default_refusal_link") or "")


def _education_links_text() -> str:
    data = load_educational_links()
    links = data.get("educational_links") or []
    if not links:
        return _default_education_url()
    primary = links[0]
    return str(primary.get("url") or _default_education_url())


def build_pii_refusal() -> GuardrailResponse:
    return GuardrailResponse(
        status="refused",
        intent=Intent.PII_RISK,
        answer=(
            "Please do not share sensitive personal information such as PAN, "
            "Aadhaar, bank account numbers, OTPs, email addresses, or phone numbers. "
            "I can only answer factual questions about HDFC mutual fund schemes from curated sources."
        ),
        citation_url=_default_education_url(),
        last_updated=None,
        disclaimer=DISCLAIMER,
    )


def build_advisory_refusal() -> GuardrailResponse:
    education_url = _education_links_text()
    return GuardrailResponse(
        status="refused",
        intent=Intent.ADVISORY,
        answer=(
            "I provide facts-only answers from curated scheme sources and cannot offer "
            "investment advice, recommendations, or fund comparisons. "
            f"For general investor education, see {education_url}."
        ),
        citation_url=education_url,
        last_updated=None,
        disclaimer=DISCLAIMER,
    )


def build_out_of_scope_refusal() -> GuardrailResponse:
    education_url = _education_links_text()
    return GuardrailResponse(
        status="refused",
        intent=Intent.OUT_OF_SCOPE,
        answer=(
            "I can only answer factual questions about the five curated HDFC schemes on Groww "
            "(expense ratio, exit load, SIP minimum, lock-in, benchmark, and related facts). "
            f"For broader investor education, see {education_url}."
        ),
        citation_url=education_url,
        last_updated=None,
        disclaimer=DISCLAIMER,
    )


def build_scheme_unresolved_refusal() -> GuardrailResponse:
    education_url = _education_links_text()
    return GuardrailResponse(
        status="refused",
        intent=Intent.OUT_OF_SCOPE,
        answer=(
            "Please name one of the five curated HDFC schemes "
            "(Mid Cap, Large Cap, BSE Sensex Index, Silver ETF FoF, or ELSS Tax Saver) "
            "so I can look up the fact. "
            f"For investor education, see {education_url}."
        ),
        citation_url=education_url,
        last_updated=None,
        disclaimer=DISCLAIMER,
    )


def build_insufficient_evidence_refusal() -> GuardrailResponse:
    education_url = _education_links_text()
    return GuardrailResponse(
        status="refused",
        intent=Intent.FACTUAL,
        answer=(
            "I could not find enough matching information in the curated Groww scheme sources "
            "to answer that question safely. "
            f"For investor education, see {education_url}."
        ),
        citation_url=education_url,
        last_updated=None,
        disclaimer=DISCLAIMER,
    )


def build_index_not_ready_refusal() -> GuardrailResponse:
    education_url = _education_links_text()
    return GuardrailResponse(
        status="refused",
        intent=Intent.OUT_OF_SCOPE,
        answer=(
            "The facts index is not ready yet. "
            "Please try again after running ingestion. "
            f"For investor education, see {education_url}."
        ),
        citation_url=education_url,
        last_updated=None,
        disclaimer=DISCLAIMER,
    )


def build_groq_error_refusal() -> GuardrailResponse:
    education_url = _education_links_text()
    return GuardrailResponse(
        status="refused",
        intent=Intent.OUT_OF_SCOPE,
        answer=(
            "The assistant is temporarily unavailable. "
            "Please try again in a moment. "
            f"For investor education, see {education_url}."
        ),
        citation_url=education_url,
        last_updated=None,
        disclaimer=DISCLAIMER,
    )


def build_performance_redirect(scheme_id: str | None) -> GuardrailResponse:
    groww_url = groww_url_for_scheme(scheme_id) if scheme_id else None
    if groww_url:
        return GuardrailResponse(
            status="redirected",
            intent=Intent.PERFORMANCE,
            answer=(
                "I cannot calculate, predict, or compare investment returns. "
                "For historic performance and return details, please refer to the "
                "official Groww scheme page."
            ),
            citation_url=groww_url,
            last_updated=None,
            disclaimer=DISCLAIMER,
        )

    education_url = _education_links_text()
    return GuardrailResponse(
        status="refused",
        intent=Intent.PERFORMANCE,
        answer=(
            "I cannot calculate or compare returns between funds. "
            "Please ask about a specific HDFC scheme fact, or review performance "
            f"on the official Groww scheme page. For investor education, see {education_url}."
        ),
        citation_url=education_url,
        last_updated=None,
        disclaimer=DISCLAIMER,
    )


def build_guardrail_response(
    intent: Intent,
    *,
    scheme_id: str | None = None,
) -> GuardrailResponse | None:
    """Build a short-circuit response for non-factual intents; None for factual."""
    if intent == Intent.FACTUAL:
        return None
    if intent == Intent.PII_RISK:
        return build_pii_refusal()
    if intent == Intent.ADVISORY:
        return build_advisory_refusal()
    if intent == Intent.PERFORMANCE:
        return build_performance_redirect(scheme_id)
    if intent == Intent.OUT_OF_SCOPE:
        return build_out_of_scope_refusal()
    return build_out_of_scope_refusal()
