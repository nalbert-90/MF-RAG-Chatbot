"""Phase 4 FastAPI app tests (no live Groq required)."""

from __future__ import annotations

from collections.abc import Iterator
from unittest.mock import MagicMock

import pytest
from fastapi.testclient import TestClient

from src.api.main import EXAMPLE_QUESTIONS, app, get_optional_groq_client
from src.guardrails.models import DISCLAIMER
from src.rag.models import AskResponse
from src.registry import load_schemes

LARGE_URL = "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"


@pytest.fixture
def client() -> Iterator[TestClient]:
    app.dependency_overrides[get_optional_groq_client] = lambda: None
    with TestClient(app) as test_client:
        yield test_client
    app.dependency_overrides.clear()


def test_health(client: TestClient) -> None:
    response = client.get("/api/v1/health")
    assert response.status_code == 200
    assert response.json() == {"status": "ok"}


def test_schemes_from_registry(client: TestClient) -> None:
    response = client.get("/api/v1/schemes")
    assert response.status_code == 200
    payload = response.json()
    schemes = payload["schemes"]
    registry = load_schemes()
    assert len(schemes) == 5
    assert {item["scheme_id"] for item in schemes} == {
        entry["scheme_id"] for entry in registry
    }
    for item in schemes:
        assert item["name"]
        assert item["category"]
        assert item["groww_url"].startswith("https://groww.in/mutual-funds/")


def test_examples_are_the_three_fixed_questions(client: TestClient) -> None:
    response = client.get("/api/v1/examples")
    assert response.status_code == 200
    questions = response.json()["questions"]
    assert questions == list(EXAMPLE_QUESTIONS)
    assert len(questions) == 3
    assert "expense ratio" in questions[0].lower()
    assert "exit load" in questions[1].lower()
    assert "lock-in" in questions[2].lower()


def test_ask_answered_contract(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = AskResponse(
        status="answered",
        answer="The expense ratio is 1.02%.",
        citation_url=LARGE_URL,
        last_updated="2026-08-28",
    )
    monkeypatch.setattr("src.api.main.run_ask", lambda *args, **kwargs: fake)

    response = client.post(
        "/api/v1/ask",
        json={"question": EXAMPLE_QUESTIONS[0]},
    )
    assert response.status_code == 200
    body = response.json()
    assert body == {
        "status": "answered",
        "answer": "The expense ratio is 1.02%.",
        "citation_url": LARGE_URL,
        "last_updated": "2026-08-28",
        "disclaimer": DISCLAIMER,
    }
    assert set(response.cookies) == set()


def test_ask_refused_contract(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    fake = AskResponse(
        status="refused",
        answer="I provide facts-only answers and cannot offer investment advice.",
        citation_url="https://www.amfiindia.com/investor-corner",
        last_updated=None,
    )
    monkeypatch.setattr("src.api.main.run_ask", lambda *args, **kwargs: fake)

    response = client.post(
        "/api/v1/ask",
        json={"question": "Should I invest in HDFC Mid Cap Fund Direct Growth?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "refused"
    assert body["disclaimer"] == DISCLAIMER
    assert body["last_updated"] is None


def test_ask_advisory_uses_orchestrator(client: TestClient) -> None:
    response = client.post(
        "/api/v1/ask",
        json={"question": "Should I invest in HDFC Mid Cap Fund Direct Growth?"},
    )
    assert response.status_code == 200
    body = response.json()
    assert body["status"] == "refused"
    assert body["disclaimer"] == DISCLAIMER
    assert "advice" in body["answer"].lower()


def test_ask_rejects_blank_question(client: TestClient) -> None:
    response = client.post("/api/v1/ask", json={"question": "   "})
    assert response.status_code == 422


def test_ask_rejects_missing_question(client: TestClient) -> None:
    response = client.post("/api/v1/ask", json={})
    assert response.status_code == 422


def test_ask_internal_error_is_safe(client: TestClient, monkeypatch: pytest.MonkeyPatch) -> None:
    monkeypatch.setattr(
        "src.api.main.run_ask",
        MagicMock(side_effect=RuntimeError("boom")),
    )
    response = client.post(
        "/api/v1/ask",
        json={"question": EXAMPLE_QUESTIONS[0]},
    )
    assert response.status_code == 500
    assert response.json()["detail"] == "Unable to process this question right now."
