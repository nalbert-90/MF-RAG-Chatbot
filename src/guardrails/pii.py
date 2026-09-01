"""Rules-first PII detection for user messages."""

from __future__ import annotations

import re

# Indian PAN: 5 letters + 4 digits + 1 letter (e.g. ABCDE1234F)
_PAN_RE = re.compile(r"\b[A-Z]{5}\d{4}[A-Z]\b", re.IGNORECASE)

# Aadhaar: 12 digits, optionally grouped (XXXX XXXX XXXX)
_AADHAAR_RE = re.compile(r"\b\d{4}[\s-]?\d{4}[\s-]?\d{4}\b")

_EMAIL_RE = re.compile(
    r"\b[A-Za-z0-9._%+-]+@[A-Za-z0-9.-]+\.[A-Za-z]{2,}\b",
)

# Indian mobile: +91XXXXXXXXXX or labeled 10-digit starting 6–9
_PHONE_RE = re.compile(
    r"(?:\+91[\s-]?[6-9]\d{9}\b)|(?:\b[6-9]\d{9}\b)",
)

_OTP_CONTEXT_RE = re.compile(
    r"\b(?:otp|one[\s-]?time\s+password)\s*(?:is|:)?\s*\d{4,8}\b",
    re.IGNORECASE,
)

_ACCOUNT_CONTEXT_RE = re.compile(
    r"\b(?:account|acc(?:ount)?\.?\s*(?:no|number)|bank\s+a/c)\s*(?:is|:)?\s*\d{6,18}\b",
    re.IGNORECASE,
)

# Explicit PAN label with value
_PAN_LABELED_RE = re.compile(
    r"\bpan\s*(?:no|number|card)?\s*(?:is|:)?\s*[A-Z0-9]{10}\b",
    re.IGNORECASE,
)


def _is_likely_aadhaar(match: re.Match[str], text: str) -> bool:
    """Avoid treating SIP amounts or short numeric facts as Aadhaar."""
    digits = re.sub(r"\D", "", match.group(0))
    if len(digits) != 12:
        return False
    # Require grouping or an aadhaar label nearby
    if re.search(r"\baadhaar\b", text, re.IGNORECASE):
        return True
    return bool(re.search(r"\d{4}[\s-]\d{4}[\s-]\d{4}", match.group(0)))


def _is_likely_phone(match: re.Match[str], text: str) -> bool:
    """Reduce false positives on bare digit sequences in fund facts."""
    value = match.group(0)
    if value.startswith("+91"):
        return True
    if re.search(
        r"\b(?:phone|mobile|contact|call me at)\b", text, re.IGNORECASE
    ):
        return True
    # Bare 10-digit numbers are too noisy for fund Q&A — require +91 or label
    return False


def contains_pii(text: str) -> bool:
    """Return True when the message likely contains sensitive personal data."""
    if not text or not text.strip():
        return False

    normalized = text.strip()

    if _PAN_RE.search(normalized) or _PAN_LABELED_RE.search(normalized):
        return True

    for match in _AADHAAR_RE.finditer(normalized):
        if _is_likely_aadhaar(match, normalized):
            return True

    if _EMAIL_RE.search(normalized):
        return True

    for match in _PHONE_RE.finditer(normalized):
        if _is_likely_phone(match, normalized):
            return True

    if _OTP_CONTEXT_RE.search(normalized):
        return True

    if _ACCOUNT_CONTEXT_RE.search(normalized):
        return True

    return False
