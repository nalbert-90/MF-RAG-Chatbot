"""Phase 4 API smoke E2E: factual answer + advisory refusal.

Exercises the same paths the React UI uses via ``POST /api/v1/ask``.

Usage:
    python -m src.api.smoke_e2e
    python -m src.api.smoke_e2e --base-url http://127.0.0.1:8000
"""

from __future__ import annotations

import argparse
import sys
from collections.abc import Callable
from dataclasses import dataclass
from typing import Any

import httpx

from src.api.main import EXAMPLE_QUESTIONS, app, get_optional_groq_client
from src.guardrails.models import DISCLAIMER

LARGE_CAP_GROWW_URL = (
    "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
)
ADVISORY_QUESTION = "Should I invest in HDFC Mid Cap Fund Direct Growth?"
FACTUAL_QUESTION = EXAMPLE_QUESTIONS[0]


@dataclass(frozen=True)
class SmokeResult:
    name: str
    ok: bool
    detail: str


def _check_health(get_json: Callable[[str], dict[str, Any]]) -> SmokeResult:
    payload = get_json("/api/v1/health")
    ok = payload.get("status") == "ok"
    return SmokeResult("health", ok, str(payload))


def _check_advisory_refusal(post_json: Callable[[str, dict], dict[str, Any]]) -> SmokeResult:
    body = post_json("/api/v1/ask", {"question": ADVISORY_QUESTION})
    ok = (
        body.get("status") == "refused"
        and body.get("disclaimer") == DISCLAIMER
        and "advice" in str(body.get("answer", "")).lower()
        and bool(body.get("citation_url"))
    )
    detail = f"status={body.get('status')!r} citation={body.get('citation_url')!r}"
    return SmokeResult("advisory_refusal", ok, detail)


def _check_factual_answer(post_json: Callable[[str, dict], dict[str, Any]]) -> SmokeResult:
    body = post_json("/api/v1/ask", {"question": FACTUAL_QUESTION})
    answer = str(body.get("answer", ""))
    ok = (
        body.get("status") == "answered"
        and body.get("citation_url") == LARGE_CAP_GROWW_URL
        and body.get("last_updated")
        and body.get("disclaimer") == DISCLAIMER
        and "1.02" in answer
    )
    detail = (
        f"status={body.get('status')!r} citation={body.get('citation_url')!r} "
        f"last_updated={body.get('last_updated')!r}"
    )
    return SmokeResult("factual_answer", ok, detail)


def run_smoke(*, base_url: str | None = None) -> list[SmokeResult]:
    """Run smoke checks in-process (TestClient) or against a live API."""
    if base_url:
        return _run_against_server(base_url.rstrip("/"))
    return _run_in_process()


def _run_in_process() -> list[SmokeResult]:
    from fastapi.testclient import TestClient

    app.dependency_overrides[get_optional_groq_client] = lambda: None
    try:
        with TestClient(app) as client:

            def get_json(path: str) -> dict[str, Any]:
                response = client.get(path)
                response.raise_for_status()
                return response.json()

            def post_json(path: str, payload: dict) -> dict[str, Any]:
                response = client.post(path, json=payload)
                response.raise_for_status()
                return response.json()

            return [
                _check_health(get_json),
                _check_advisory_refusal(post_json),
                _check_factual_answer(post_json),
            ]
    finally:
        app.dependency_overrides.clear()


def _run_against_server(base_url: str) -> list[SmokeResult]:
    with httpx.Client(base_url=base_url, timeout=60.0) as client:

        def get_json(path: str) -> dict[str, Any]:
            response = client.get(path)
            response.raise_for_status()
            return response.json()

        def post_json(path: str, payload: dict) -> dict[str, Any]:
            response = client.post(path, json=payload)
            response.raise_for_status()
            return response.json()

        return [
            _check_health(get_json),
            _check_advisory_refusal(post_json),
            _check_factual_answer(post_json),
        ]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Phase 4 API smoke E2E (factual answer + advisory refusal)."
    )
    parser.add_argument(
        "--base-url",
        default=None,
        help="Live API base URL (default: in-process TestClient).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    mode = args.base_url or "in-process TestClient"
    print(f"Smoke E2E ({mode})")
    print("-" * 40)

    try:
        results = run_smoke(base_url=args.base_url)
    except Exception as exc:
        print(f"FAIL  smoke run aborted: {exc}", file=sys.stderr)
        if "Index not ready" in str(exc) or "index not ready" in str(exc).lower():
            print(
                "Hint: run `python -m src.ingest.run --rebuild` then retry.",
                file=sys.stderr,
            )
        return 1

    failed = 0
    for result in results:
        label = "PASS" if result.ok else "FAIL"
        print(f"{label}  {result.name}: {result.detail}")
        if not result.ok:
            failed += 1

    if failed:
        print("-" * 40)
        print(f"{failed} check(s) failed.", file=sys.stderr)
        return 1

    print("-" * 40)
    print("All API smoke checks passed.")
    if args.base_url:
        print("Manual UI check: open http://localhost:5173 and try an example question.")
    else:
        print(
            "Next: start the stack with .\\scripts\\run_api.ps1 and .\\scripts\\run_ui.ps1, "
            "then run `python -m src.api.smoke_e2e --base-url http://127.0.0.1:8000`."
        )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
