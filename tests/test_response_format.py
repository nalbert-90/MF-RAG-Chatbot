import pytest

from src.guardrails import (
    DISCLAIMER,
    count_sentences,
    format_answered_response,
    validate_answer_body,
    validate_formatted_response,
)


def test_count_sentences() -> None:
    assert count_sentences("One sentence.") == 1
    assert count_sentences("First. Second. Third.") == 3
    assert count_sentences("First! Second? Third.") == 3


def test_validate_answer_body_accepts_three_sentences() -> None:
    body = "Sentence one. Sentence two. Sentence three."
    result = validate_answer_body(body)
    assert result.ok


def test_validate_answer_body_rejects_four_sentences() -> None:
    body = "One. Two. Three. Four."
    result = validate_answer_body(body)
    assert not result.ok
    assert any("4 sentences" in error for error in result.errors)


def test_validate_answer_body_rejects_advisory_phrasing() -> None:
    body = "You should consider this fund for long-term goals."
    result = validate_answer_body(body)
    assert not result.ok
    assert any("advisory" in error for error in result.errors)


def test_format_and_validate_answered_response() -> None:
    citation = "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
    formatted = format_answered_response(
        "The expense ratio is 1.02%.",
        citation_url=citation,
        last_updated="2026-08-28",
    )
    result = validate_formatted_response(formatted, expected_citation=citation)
    assert result.ok
    assert "Source:" in formatted
    assert "Last updated from sources: 2026-08-28" in formatted
    assert DISCLAIMER in formatted


def test_validate_formatted_response_requires_single_url() -> None:
    text = (
        "Fact one.\n\n"
        "Source: https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth\n"
        "Source: https://investor.sebi.gov.in/\n"
        "Last updated from sources: 2026-08-28\n\n"
        f"{DISCLAIMER}"
    )
    result = validate_formatted_response(text)
    assert not result.ok
    assert any("exactly one citation URL" in error for error in result.errors)


def test_validate_formatted_response_requires_footer() -> None:
    text = (
        "Fact one.\n\n"
        "Source: https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth\n\n"
        f"{DISCLAIMER}"
    )
    result = validate_formatted_response(text)
    assert not result.ok
    assert any("footer" in error for error in result.errors)


@pytest.mark.parametrize(
    "phrase",
    [
        "I recommend this fund.",
        "Fund A is better than Fund B.",
        "You should invest more.",
    ],
)
def test_advisory_blocklist(phrase: str) -> None:
    result = validate_answer_body(phrase)
    assert not result.ok
