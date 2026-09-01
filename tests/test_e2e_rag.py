"""L3 end-to-end RAG integration tests (live Groq + vector index)."""

from __future__ import annotations

import json
from pathlib import Path

import pytest

from src.guardrails import DISCLAIMER, count_sentences
from src.ingest.allowlist import is_allowlisted_citation_url
from src.ingest.chunk import CHUNKS_PATH
from src.ingest.embed_index import embed_index, open_index
from src.rag.groq_client import GroqClient
from src.rag.orchestrator import ask
from tests.conftest import groq_api_key_configured

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "golden_qa.json"
FIXTURE_CHUNKS = Path(__file__).resolve().parent / "fixtures" / "chunks.jsonl"


def _load_golden_cases() -> list[dict]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def live_collection(tmp_path_factory: pytest.TempPathFactory):
    chunks_path = CHUNKS_PATH if CHUNKS_PATH.is_file() else FIXTURE_CHUNKS
    if not chunks_path.is_file():
        pytest.skip("chunks.jsonl fixture missing")

    chroma_dir = tmp_path_factory.mktemp("chroma_e2e")
    embed_index(chunks_path=chunks_path, chroma_path=chroma_dir, rebuild=True)
    return open_index(chroma_path=chroma_dir, create=False).collection


@pytest.fixture(scope="module")
def groq_client() -> GroqClient:
    if not groq_api_key_configured():
        pytest.skip("GROQ_API_KEY not set")
    return GroqClient()


@pytest.mark.integration
@pytest.mark.parametrize("case", _load_golden_cases(), ids=lambda c: c["id"])
def test_golden_e2e_with_groq(
    case: dict,
    live_collection,
    groq_client: GroqClient,
) -> None:
    if case["expected_status"] == "redirected":
        pytest.skip("redirect cases covered in unit guardrail tests")

    response = ask(
        case["question"],
        groq_client=groq_client,
        collection=live_collection,
    )
    assert response.status == case["expected_status"]

    if case["expected_status"] == "answered":
        assert response.citation_url
        assert is_allowlisted_citation_url(response.citation_url)
        if "citation_url" in case:
            assert response.citation_url == case["citation_url"]
        assert response.last_updated
        assert response.disclaimer == DISCLAIMER
        assert count_sentences(response.answer) <= 3
        assert any(
            token.lower() in response.answer.lower()
            for token in case["must_include_any"]
        )
        lowered = response.answer.lower()
        assert "you should" not in lowered
        assert "i recommend" not in lowered

    if case["expected_status"] == "refused":
        assert response.disclaimer == DISCLAIMER
        assert "advice" in response.answer.lower() or "facts-only" in response.answer.lower()


@pytest.mark.integration
def test_advisory_never_answered_with_groq(live_collection, groq_client: GroqClient) -> None:
    response = ask(
        "Should I invest in HDFC Mid Cap Fund Direct Growth?",
        groq_client=groq_client,
        collection=live_collection,
    )
    assert response.status == "refused"
    assert "advice" in response.answer.lower()
