"""Phase 3 RAG orchestrator tests (L3 unit; live Groq optional)."""

from __future__ import annotations

import json
from pathlib import Path
from unittest.mock import MagicMock

import pytest

from src.guardrails import DISCLAIMER, Intent, count_sentences
from src.ingest.chunk import CHUNKS_PATH
from src.ingest.embed_index import embed_index, open_index
from src.rag.orchestrator import ask
from src.rag.retriever import (
    infer_target_facts,
    infer_target_section,
    is_retrieval_sufficient,
)

FIXTURES = Path(__file__).resolve().parent / "fixtures" / "golden_qa.json"
LARGE_ID = "hdfc_large_cap_direct_growth"
MIDCAP_ID = "hdfc_mid_cap_direct_growth"
ELSS_ID = "hdfc_elss_tax_saver_direct_growth"
SILVER_ID = "hdfc_silver_etf_fof_direct_growth"
LARGE_URL = "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"


def _load_golden_cases() -> list[dict]:
    return json.loads(FIXTURES.read_text(encoding="utf-8"))


@pytest.fixture(scope="module")
def live_collection(tmp_path_factory: pytest.TempPathFactory):
    if not CHUNKS_PATH.is_file():
        pytest.skip("data/processed/chunks.jsonl not present")
    chroma_dir = tmp_path_factory.mktemp("chroma_rag")
    embed_index(chunks_path=CHUNKS_PATH, chroma_path=chroma_dir, rebuild=True)
    return open_index(chroma_path=chroma_dir, create=False)


def test_infer_target_section_keywords() -> None:
    assert infer_target_section("What is the expense ratio?") == "expense_ratio"
    assert infer_target_section("What is the exit load?") == "exit_load"
    assert infer_target_section("What is the minimum SIP?") == "sip"
    assert infer_target_section("What is the lock-in period?") == "lock_in"
    assert infer_target_section("What is the riskometer?") == "riskometer"
    assert infer_target_section("What is the NAV?") == "other"


def test_infer_target_facts_multi_fact() -> None:
    facts = infer_target_facts("NAV and expnse ratio of HDFC mid cap fund")
    assert facts == ["other::nav", "expense_ratio"]


def test_advisory_never_reaches_generation(live_collection) -> None:
    groq = MagicMock()
    groq.chat.return_value = "You should buy this fund."
    groq.classify.return_value = '{"intent":"factual"}'

    response = ask(
        "Should I invest in HDFC Mid Cap Fund Direct Growth?",
        groq_client=groq,
        collection=live_collection.collection,
    )
    assert response.status == "refused"
    assert response.intent == Intent.ADVISORY
    groq.chat.assert_not_called()


def test_ambiguous_scheme_refused(live_collection) -> None:
    response = ask(
        "What is the expense ratio of HDFC fund?",
        groq_client=None,
        use_groq=False,
        collection=live_collection.collection,
    )
    assert response.status == "refused"


def test_riskometer_insufficient_evidence(live_collection) -> None:
    response = ask(
        "What is the risk level of HDFC Mid Cap Fund?",
        groq_client=None,
        use_groq=False,
        collection=live_collection.collection,
    )
    assert response.status == "refused"


def test_silver_lockin_refused(live_collection) -> None:
    response = ask(
        "What is the lock-in for HDFC Silver ETF FoF?",
        groq_client=None,
        use_groq=False,
        collection=live_collection.collection,
    )
    assert response.status == "refused"


def test_factual_no_groq_fallback(live_collection) -> None:
    response = ask(
        "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
        groq_client=None,
        use_groq=False,
        collection=live_collection.collection,
    )
    assert response.status == "answered"
    assert response.citation_url == LARGE_URL
    assert response.last_updated == "2026-08-28"
    assert "1.02" in response.answer
    assert count_sentences(response.answer) <= 3
    assert response.disclaimer == DISCLAIMER


def test_multi_fact_nav_and_expense_ratio(live_collection) -> None:
    response = ask(
        "NAV and expnse ratio of HDFC mid cap fund",
        groq_client=None,
        use_groq=False,
        collection=live_collection.collection,
    )
    assert response.status == "answered"
    assert "0.74" in response.answer
    assert "237.07" in response.answer
    assert "Rating" not in response.answer
    assert count_sentences(response.answer) <= 3


def test_factual_with_mock_groq(live_collection) -> None:
    groq = MagicMock()
    groq.classify.return_value = '{"intent":"factual"}'
    groq.chat.return_value = "The expense ratio is 1.02%."

    response = ask(
        "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
        groq_client=groq,
        collection=live_collection.collection,
    )
    assert response.status == "answered"
    assert response.citation_url == LARGE_URL
    assert "1.02" in response.answer
    groq.chat.assert_called()
    groq.classify.assert_not_called()


def test_performance_redirect(live_collection) -> None:
    response = ask(
        "What is the 5-year return of HDFC Large Cap Fund Direct Growth?",
        groq_client=None,
        use_groq=False,
        collection=live_collection.collection,
    )
    assert response.status == "redirected"
    assert response.citation_url == LARGE_URL
    assert "cannot calculate" in response.answer.lower()


def test_is_retrieval_sufficient_rejects_riskometer() -> None:
    from src.rag.retriever import RetrievalHit

    hits = [
        RetrievalHit(
            chunk_id=f"{MIDCAP_ID}::expense_ratio",
            scheme_id=MIDCAP_ID,
            section="expense_ratio",
            text="Expense ratio 0.74%.",
            citation_url="https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
            published_or_as_of="2026-08-28",
            title="Expense ratio",
            distance=0.2,
            rank=1,
        )
    ]
    ok, reason = is_retrieval_sufficient(
        hits,
        question="What is the riskometer of HDFC Mid Cap?",
    )
    assert not ok
    assert reason == "riskometer is not in the curated corpus"


@pytest.mark.parametrize("case", _load_golden_cases(), ids=lambda c: c["id"])
def test_golden_cases_no_groq(case: dict, live_collection) -> None:
    if case["expected_status"] == "redirected":
        pytest.skip("redirect cases covered in dedicated test")

    response = ask(
        case["question"],
        groq_client=None,
        use_groq=False,
        collection=live_collection.collection,
    )
    assert response.status == case["expected_status"]
    if case["expected_status"] == "answered":
        assert response.citation_url == case["citation_url"]
        assert response.last_updated
        assert any(token in response.answer for token in case["must_include_any"])
        assert count_sentences(response.answer) <= 3
        assert response.disclaimer == DISCLAIMER
    if "citation_url" in case and case["expected_status"] == "refused":
        pass  # education link optional on some refusals


@pytest.mark.integration
def test_live_groq_factual_answer(live_collection) -> None:
    from tests.conftest import groq_api_key_configured

    if not groq_api_key_configured():
        pytest.skip("GROQ_API_KEY not set")

    from src.rag.groq_client import GroqClient

    response = ask(
        "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
        groq_client=GroqClient(),
        collection=live_collection.collection,
    )
    assert response.status == "answered"
    assert response.citation_url == LARGE_URL
    assert count_sentences(response.answer) <= 3
    assert response.disclaimer == DISCLAIMER
