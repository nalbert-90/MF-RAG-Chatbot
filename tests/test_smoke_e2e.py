"""Phase 4 smoke E2E tests (API factual + advisory paths)."""

from __future__ import annotations

import pytest

from src.api.smoke_e2e import run_smoke
from src.config import get_settings
from src.ingest.chunk import CHUNKS_PATH
from src.ingest.embed_index import IndexNotReadyError, open_index


@pytest.fixture(scope="module")
def ensure_index() -> None:
    """Require a populated Chroma index (same gate as manual smoke)."""
    try:
        open_index(chroma_path=get_settings().chroma_path_resolved, create=False)
    except IndexNotReadyError:
        if not CHUNKS_PATH.is_file():
            pytest.skip("vector index and chunks.jsonl missing — run ingest first")
        pytest.skip("vector index not ready — run `python -m src.ingest.run --rebuild`")


def test_smoke_e2e_in_process(ensure_index: None) -> None:
    results = run_smoke()
    assert results, "expected smoke checks to run"
    failed = [result for result in results if not result.ok]
    assert not failed, failed
