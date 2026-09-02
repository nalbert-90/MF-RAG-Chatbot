from src.rag.output_sanitize import is_meta_placeholder_answer, sanitize_model_output


def test_sanitize_strips_closed_thinking_block() -> None:
    raw = (
        "<think>internal reasoning</think>"
        "The expense ratio is 1.02%."
    )
    assert sanitize_model_output(raw) == "The expense ratio is 1.02%."


def test_sanitize_extracts_draft_from_unclosed_thinking() -> None:
    raw = """<think>
Thinking Process:
5.  **Draft Response:** The lock-in period for the HDFC ELSS Tax Saver Fund is 3 years.
6.  **Check Constraints:** 1 sentence.
"""
    assert (
        sanitize_model_output(raw)
        == "The lock-in period for the HDFC ELSS Tax Saver Fund is 3 years."
    )


def test_sanitize_strips_meta_parenthetical() -> None:
    raw = '"The expense ratio is 1.02%." (Matches constraints perfectly)'
    assert sanitize_model_output(raw) == "The expense ratio is 1.02%."


def test_sanitize_extracts_final_output_generation() -> None:
    raw = """<think>
6.  **Final Output Generation:** The lock-in period for the HDFC ELSS Tax Saver Fund is 3 years.✅
"""
    assert (
        sanitize_model_output(raw)
        == "The lock-in period for the HDFC ELSS Tax Saver Fund is 3 years."
    )


def test_is_meta_placeholder_answer_detects_prompt_echo() -> None:
    assert is_meta_placeholder_answer("(Just the answer text)")
    assert is_meta_placeholder_answer("Just the answer text")
    assert not is_meta_placeholder_answer("The expense ratio is 1.02%.")
