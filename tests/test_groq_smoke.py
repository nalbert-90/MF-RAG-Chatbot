import pytest

from src.rag.groq_client import GroqClient
from tests.conftest import groq_api_key_configured


@pytest.mark.integration
def test_groq_smoke_returns_non_empty_response() -> None:
    if not groq_api_key_configured():
        pytest.skip("GROQ_API_KEY not set — copy .env.example to .env")

    client = GroqClient()
    reply = client.chat(
        [
            {
                "role": "system",
                "content": "Reply with exactly one word: pong",
            },
            {"role": "user", "content": "ping"},
        ],
        max_tokens=16,
        temperature=0.0,
    )

    assert reply
    assert len(reply.strip()) > 0


def test_groq_client_requires_api_key() -> None:
    with pytest.raises(ValueError, match="GROQ_API_KEY"):
        GroqClient(api_key="")
