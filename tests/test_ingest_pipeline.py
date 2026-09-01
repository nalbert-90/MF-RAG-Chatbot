"""Tests for the Phase 6 daily ingest pipeline wrapper."""

from __future__ import annotations

from unittest.mock import MagicMock, patch

from src.ingest.fetch import FetchResult
from src.ingest.pipeline import run_fetch


def _result(scheme_id: str, status: str) -> FetchResult:
    return FetchResult(
        scheme_id=scheme_id,
        citation_url=f"https://groww.in/mutual-funds/{scheme_id}",
        source_org="groww",
        doc_type="scheme_page",
        fetched_at="2026-09-01T00:00:00+00:00",
        sha256="abc",
        bytes=100,
        path=f"{scheme_id}/scheme_page.html",
        http_status=200,
        status=status,
        error=None,
    )


@patch("src.ingest.pipeline.fetch_all")
def test_run_fetch_strict_rejects_manual_fallback(mock_fetch_all: MagicMock) -> None:
    mock_fetch_all.return_value = [
        _result("hdfc_large_cap_direct_growth", "ok"),
        _result("hdfc_mid_cap_direct_growth", "manual_fallback"),
    ]
    assert run_fetch(offline=False, strict=True) == 1


@patch("src.ingest.pipeline.fetch_all")
def test_run_fetch_strict_accepts_all_ok(mock_fetch_all: MagicMock) -> None:
    mock_fetch_all.return_value = [
        _result("hdfc_large_cap_direct_growth", "ok"),
        _result("hdfc_mid_cap_direct_growth", "ok"),
    ]
    assert run_fetch(offline=False, strict=True) == 0


@patch("src.ingest.pipeline.fetch_all")
def test_run_fetch_non_strict_allows_manual_fallback(mock_fetch_all: MagicMock) -> None:
    mock_fetch_all.return_value = [
        _result("hdfc_large_cap_direct_growth", "manual_fallback"),
    ]
    assert run_fetch(offline=False, strict=False) == 0
