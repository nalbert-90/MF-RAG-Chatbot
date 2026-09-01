"""Hybrid intent classifier: PII and keyword rules first, Groq JSON fallback."""

from __future__ import annotations

import json
import re
from typing import Any

from src.guardrails.models import ClassificationResult, Intent
from src.guardrails.pii import contains_pii
from src.guardrails.scheme_resolver import resolve_scheme_id

CLASSIFY_SYSTEM_PROMPT = """Return ONLY JSON: {"intent":"<one of: factual|advisory|performance|pii_risk|out_of_scope>"}
You classify mutual-fund user questions for a facts-only assistant.
Advisory = asks what to buy/sell, suitability, allocation, or which fund is better.
Performance = asks to compute, predict, or compare returns, CAGR, NAV history, or rankings.
pii_risk = message shares PAN, Aadhaar, OTP, email, phone, or account numbers.
out_of_scope = unrelated to HDFC mutual fund facts, gibberish, or other AMCs.
factual = asks for a specific scheme fact (expense ratio, exit load, SIP minimum, lock-in, benchmark, stamp duty).
Do not explain. JSON only."""

_ADVISORY_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bshould\s+i\b",
        r"\bwhich\s+(?:fund|one)\s+is\s+better\b",
        r"\bwhich\s+is\s+better\b",
        r"\brecommend\b",
        r"\brecommendation\b",
        r"\bgood\s+for\s+me\b",
        r"\bsuitable\s+for\s+me\b",
        r"\bhow\s+much\s+(?:should\s+i\s+)?(?:invest|sip)\b",
        r"\bhow\s+much\s+sip\s+should\b",
        r"\bbuy\s+or\s+sell\b",
        r"\bwhat\s+should\s+i\s+(?:buy|invest|do)\b",
        r"\bignore\s+(?:all\s+)?(?:previous|prior)\s+instructions\b",
        r"\b(?:recommend|suggest)\s+(?:a\s+)?fund\b",
        r"\bsafe\s+fund\b",
        r"\bcompare\s+(?:exit\s+load|ter|expense|sip|lock[- ]?in)\b",
    )
)

_PERFORMANCE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\b(?:5|3|1|10)[\s-]?year\s+return\b",
        r"\b\d+\s*y(?:ear)?\s+return\b",
        r"\b(?:past|historic|historical)\s+(?:return|performance)\b",
        r"\b(?:cagr|xirr)\b",
        r"\b(?:higher|better|more)\s+returns?\b",
        r"\breturn\s+calculator\b",
        r"\bcompare\s+returns?\b",
        r"\bwhich\s+(?:fund\s+)?gave\s+(?:higher|better|more)\s+returns?\b",
        r"\b(?:current|live|today'?s?)\s+nav\b",
        r"\bnav\s+history\b",
        r"\bperformance\s+(?:of|for)\b",
        r"\bwhat\s+(?:is|was)\s+the\s+\d",
    )
)

_FACTUAL_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bexpense ratio\b",
        r"\bexit load\b",
        r"\bminimum sip\b",
        r"\bmin\.?\s*for sip\b",
        r"\bsip minimum\b",
        r"\block[- ]?in\b",
        r"\bbenchmark\b",
        r"\bstamp duty\b",
        r"\btax implication\b",
        r"\bfund size\b",
        r"\baum\b",
        r"\bnav\b",
        r"\bter\b",
    )
)

_OUT_OF_SCOPE_PATTERNS: tuple[re.Pattern[str], ...] = tuple(
    re.compile(pattern, re.IGNORECASE)
    for pattern in (
        r"\bsbi\s+(?:mutual\s+)?fund\b",
        r"\bicici\s+(?:mutual\s+)?fund\b",
        r"\baxis\s+(?:mutual\s+)?fund\b",
        r"\bnippon\s+(?:mutual\s+)?fund\b",
        r"\buti\s+(?:mutual\s+)?fund\b",
    )
)

_GIBBERISH_RE = re.compile(r"^[\W_\d\s]{1,12}$|^[\u2600-\u27BF\s]+$")


def _matches_any(text: str, patterns: tuple[re.Pattern[str], ...]) -> bool:
    return any(pattern.search(text) for pattern in patterns)


def classify_by_rules(question: str) -> Intent | None:
    text = (question or "").strip()
    if not text:
        return Intent.OUT_OF_SCOPE

    if _GIBBERISH_RE.match(text):
        return Intent.OUT_OF_SCOPE

    if _matches_any(text, _ADVISORY_PATTERNS):
        return Intent.ADVISORY

    if _matches_any(text, _PERFORMANCE_PATTERNS):
        return Intent.PERFORMANCE

    if _matches_any(text, _OUT_OF_SCOPE_PATTERNS):
        return Intent.OUT_OF_SCOPE

    if _matches_any(text, _FACTUAL_PATTERNS):
        return Intent.FACTUAL

    return None


def _parse_groq_intent(raw: str) -> Intent | None:
    text = (raw or "").strip()
    if not text:
        return None

    payload: dict[str, Any] | None = None
    try:
        payload = json.loads(text)
    except json.JSONDecodeError:
        match = re.search(r"\{.*\}", text, flags=re.DOTALL)
        if match:
            try:
                payload = json.loads(match.group(0))
            except json.JSONDecodeError:
                return None

    if not payload:
        return None

    label = str(payload.get("intent", "")).strip().lower()
    try:
        return Intent(label)
    except ValueError:
        return None


def classify_with_groq(question: str, groq_client: Any) -> Intent | None:
    messages = [
        {"role": "system", "content": CLASSIFY_SYSTEM_PROMPT},
        {"role": "user", "content": question.strip()},
    ]
    raw = groq_client.classify(messages)
    return _parse_groq_intent(raw)


def classify_intent(
    question: str,
    *,
    groq_client: Any | None = None,
    use_groq: bool = True,
) -> ClassificationResult:
    """Classify user intent. Rules override Groq for advisory, performance, and PII."""
    text = (question or "").strip()

    if contains_pii(text):
        return ClassificationResult(intent=Intent.PII_RISK, source="pii")

    rule_intent = classify_by_rules(text)
    if rule_intent is not None:
        scheme_id = (
            resolve_scheme_id(text)
            if rule_intent == Intent.PERFORMANCE
            else None
        )
        return ClassificationResult(
            intent=rule_intent,
            source="rules",
            scheme_id=scheme_id,
        )

    groq_intent: Intent | None = None
    if use_groq and groq_client is not None:
        try:
            groq_intent = classify_with_groq(text, groq_client)
        except Exception:
            groq_intent = None

    if groq_intent is not None and groq_intent != Intent.PII_RISK:
        scheme_id = (
            resolve_scheme_id(text) if groq_intent == Intent.PERFORMANCE else None
        )
        return ClassificationResult(
            intent=groq_intent,
            source="groq",
            scheme_id=scheme_id,
        )

    if not text:
        return ClassificationResult(intent=Intent.OUT_OF_SCOPE, source="fallback")

    # Ambiguous but on-topic — allow factual path (retrieval may still refuse).
    return ClassificationResult(
        intent=Intent.FACTUAL,
        source="fallback",
        scheme_id=resolve_scheme_id(text),
    )
