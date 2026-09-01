"""Phase 1 retrieval tests (L1): index contract + filtered hit@1. No Groq."""

from __future__ import annotations

from pathlib import Path

import pytest

from src.ingest.chunk import CHUNKS_PATH
from src.ingest.embed_index import (
    COLLECTION_NAME,
    EXPECTED_CHUNK_COUNT,
    IndexNotReadyError,
    IndexValidationError,
    chroma_metadata,
    embed_index,
    load_index_rows,
    open_index,
    upsert_chunks,
    validate_rows,
)
from src.ingest.inspect import format_vector
from src.ingest.retrieve_check import (
    ELSS_ID,
    FILTERED_PROBES,
    LARGE_ID,
    MIDCAP_ID,
    SENSEX_ID,
    SILVER_ID,
    UNFILTERED_DIAGNOSTICS,
    Probe,
    assert_index_inventory,
    evaluate_probe,
    run_probes,
)
from src.rag.retriever import RetrievalHit, build_where, retrieve
from src.registry import load_schemes

LARGE_URL = "https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth"
SENSEX_URL = "https://groww.in/mutual-funds/hdfc-bse-sensex-index-fund-direct-growth"


def _row(**overrides: object) -> dict:
    base: dict = {
        "chunk_id": f"{LARGE_ID}::expense_ratio",
        "scheme_id": LARGE_ID,
        "scheme_name": "HDFC Large Cap Fund - Direct Growth",
        "source_org": "groww",
        "doc_type": "scheme_page",
        "title": "Expense ratio",
        "citation_url": LARGE_URL,
        "published_or_as_of": "2026-08-28",
        "ingested_at": "2026-08-31T17:04:50+00:00",
        "section": "expense_ratio",
        "text": "HDFC Large Cap Fund - Direct Growth. Expense ratio 1.02%.",
    }
    base.update(overrides)
    return base


def _hit(**overrides: object) -> RetrievalHit:
    values = dict(
        chunk_id=f"{LARGE_ID}::expense_ratio",
        scheme_id=LARGE_ID,
        section="expense_ratio",
        text="HDFC Large Cap Fund - Direct Growth. Expense ratio 1.02%.",
        citation_url=LARGE_URL,
        published_or_as_of="2026-08-28",
        title="Expense ratio",
        distance=0.1,
        rank=1,
    )
    values.update(overrides)
    return RetrievalHit(**values)  # type: ignore[arg-type]


class _FakeEmbeddingFunction:
    """Deterministic 8-d vectors so Chroma tests do not download MiniLM."""

    @staticmethod
    def name() -> str:
        return "fake_hash_8d"

    @staticmethod
    def build_from_config(config: dict) -> "_FakeEmbeddingFunction":
        return _FakeEmbeddingFunction()

    def is_legacy(self) -> bool:
        return False

    def get_config(self) -> dict:
        return {"type": "fake_hash_8d"}

    def default_space(self) -> str:
        return "cosine"

    def supported_spaces(self) -> list[str]:
        return ["cosine", "l2", "ip"]

    def embed_query(self, input):  # noqa: A002
        return self(input)

    def __call__(self, input):  # noqa: A002 — chromadb callback name
        vectors = []
        for text in input:
            vec = [0.0] * 8
            for i, byte in enumerate(text.encode("utf-8")[:64]):
                vec[i % 8] += (byte % 17) / 17.0
            if not any(vec):
                vec[0] = 1.0
            vectors.append(vec)
        return vectors


def test_format_vector_truncates_and_full() -> None:
    vec = [0.1, -0.2, 0.3, 0.4]
    truncated = format_vector(vec, dims=2, full=False)
    assert "0.1000" in truncated
    assert "..." in truncated
    assert "dim=4" in truncated
    full = format_vector(vec, dims=2, full=True)
    assert "0.4000" in full
    assert "..." not in full


def test_build_where_always_includes_groww_scheme_page() -> None:
    unfiltered = build_where()
    assert unfiltered == {
        "$and": [
            {"source_org": "groww"},
            {"doc_type": "scheme_page"},
        ]
    }
    filtered = build_where(scheme_id=SENSEX_ID)
    assert {"scheme_id": SENSEX_ID} in filtered["$and"]
    assert {"source_org": "groww"} in filtered["$and"]
    assert {"doc_type": "scheme_page"} in filtered["$and"]


def test_chroma_metadata_is_flat_strings() -> None:
    meta = chroma_metadata(_row())
    assert meta["scheme_id"] == LARGE_ID
    assert meta["source_org"] == "groww"
    assert all(isinstance(value, str) for value in meta.values())


def test_chroma_metadata_rejects_none() -> None:
    row = _row()
    row["published_or_as_of"] = None
    with pytest.raises(IndexValidationError, match="must not be empty"):
        chroma_metadata(row)


def test_validate_rows_rejects_riskometer_and_foreign_url() -> None:
    with pytest.raises(IndexValidationError, match="riskometer"):
        validate_rows(
            [_row(section="riskometer", chunk_id=f"{LARGE_ID}::riskometer")],
            require_all_schemes=False,
        )
    with pytest.raises(IndexValidationError, match="not allowlisted"):
        validate_rows(
            [_row(citation_url="https://www.hdfcfund.com/factsheet")],
            require_all_schemes=False,
        )


def test_evaluate_probe_rank1_and_miss() -> None:
    hit = evaluate_probe(
        Probe(
            id="t",
            question="expense ratio?",
            scheme_id=LARGE_ID,
            expected_section="expense_ratio",
            expected_chunk_id=f"{LARGE_ID}::expense_ratio",
        ),
        [_hit()],
    )
    assert hit.passed

    miss = evaluate_probe(
        Probe(
            id="m",
            question="lock-in?",
            scheme_id=SILVER_ID,
            expect_miss_section="lock_in",
        ),
        [_hit(scheme_id=SILVER_ID, section="expense_ratio", chunk_id=f"{SILVER_ID}::expense_ratio")],
    )
    assert miss.passed

    leaked = evaluate_probe(
        Probe(
            id="m2",
            question="lock-in?",
            scheme_id=SILVER_ID,
            expect_miss_section="lock_in",
        ),
        [_hit(scheme_id=SILVER_ID, section="lock_in", chunk_id=f"{SILVER_ID}::lock_in")],
    )
    assert not leaked.passed

    collision = evaluate_probe(
        Probe(
            id="c",
            question="ter?",
            scheme_id=SENSEX_ID,
            expected_section="expense_ratio",
            expected_chunk_id=f"{SENSEX_ID}::expense_ratio",
            forbidden_scheme_id=SILVER_ID,
        ),
        [
            _hit(
                scheme_id=SENSEX_ID,
                chunk_id=f"{SENSEX_ID}::expense_ratio",
                citation_url=SENSEX_URL,
            ),
            _hit(
                rank=2,
                scheme_id=SILVER_ID,
                chunk_id=f"{SILVER_ID}::expense_ratio",
            ),
        ],
    )
    assert not collision.passed


def test_filtered_probe_table_covers_fact_types() -> None:
    sections = {probe.expected_section for probe in FILTERED_PROBES if probe.expected_section}
    assert {
        "expense_ratio",
        "exit_load",
        "sip",
        "lock_in",
        "benchmark",
        "process",
    } <= sections
    miss_sections = {
        probe.expect_miss_section for probe in FILTERED_PROBES if probe.expect_miss_section
    }
    assert miss_sections == {"lock_in", "riskometer"}
    assert all(probe.scheme_id is None for probe in UNFILTERED_DIAGNOSTICS)
    assert all(probe.diagnostic for probe in UNFILTERED_DIAGNOSTICS)


def test_retrieve_index_not_ready(tmp_path: Path) -> None:
    with pytest.raises(IndexNotReadyError, match="Index not ready"):
        retrieve("What is the expense ratio?", scheme_id=LARGE_ID, chroma_path=tmp_path)


def test_upsert_rebuild_drops_stale_ids(tmp_path: Path) -> None:
    fake = _FakeEmbeddingFunction()
    first = [
        _row(),
        _row(
            chunk_id=f"{SENSEX_ID}::expense_ratio",
            scheme_id=SENSEX_ID,
            scheme_name="HDFC BSE Sensex Index Fund - Direct Growth",
            citation_url=SENSEX_URL,
            text="HDFC BSE Sensex Index Fund - Direct Growth. Expense ratio 0.22%.",
        ),
    ]
    stats = upsert_chunks(
        first,
        chroma_path=tmp_path,
        rebuild=True,
        embedding_function=fake,
        require_all_schemes=False,
    )
    assert stats.count == 2
    assert stats.collection == COLLECTION_NAME

    stats = upsert_chunks(
        [first[0]],
        chroma_path=tmp_path,
        rebuild=True,
        embedding_function=fake,
        require_all_schemes=False,
    )
    assert stats.count == 1
    opened = open_index(chroma_path=tmp_path, create=False, embedding_function=fake)
    snapshot = opened.collection.get()
    assert snapshot["ids"] == [f"{LARGE_ID}::expense_ratio"]


def test_scheme_filter_excludes_other_fund(tmp_path: Path) -> None:
    fake = _FakeEmbeddingFunction()
    rows = [
        _row(),
        _row(
            chunk_id=f"{SENSEX_ID}::expense_ratio",
            scheme_id=SENSEX_ID,
            scheme_name="HDFC BSE Sensex Index Fund - Direct Growth",
            citation_url=SENSEX_URL,
            text="HDFC BSE Sensex Index Fund - Direct Growth. Expense ratio 0.22%.",
        ),
    ]
    upsert_chunks(
        rows,
        chroma_path=tmp_path,
        rebuild=True,
        embedding_function=fake,
        require_all_schemes=False,
    )
    opened = open_index(chroma_path=tmp_path, create=False, embedding_function=fake)
    hits = retrieve(
        "expense ratio",
        scheme_id=LARGE_ID,
        collection=opened.collection,
        embedding_function=fake,
    )
    assert hits
    assert all(hit.scheme_id == LARGE_ID for hit in hits)
    assert all(hit.chunk_id.startswith(LARGE_ID) for hit in hits)


def _live_chunks_path() -> Path:
    if not CHUNKS_PATH.is_file():
        pytest.skip("data/processed/chunks.jsonl not present")
    return CHUNKS_PATH


def test_live_chunks_jsonl_matches_index_contract() -> None:
    rows = load_index_rows(_live_chunks_path())
    validate_rows(rows, expected_count=EXPECTED_CHUNK_COUNT)
    assert len({row["scheme_id"] for row in rows}) == 5
    assert all(row["section"] != "riskometer" for row in rows)
    assert any(row["scheme_id"] == ELSS_ID and row["section"] == "lock_in" for row in rows)
    assert not any(
        row["scheme_id"] == SILVER_ID and row["section"] == "lock_in" for row in rows
    )


@pytest.fixture(scope="module")
def live_collection(tmp_path_factory: pytest.TempPathFactory):
    path = _live_chunks_path()
    chroma_dir = tmp_path_factory.mktemp("chroma_live")
    embed_index(
        chunks_path=path,
        chroma_path=chroma_dir,
        rebuild=True,
        expected_count=EXPECTED_CHUNK_COUNT,
    )
    return open_index(chroma_path=chroma_dir, create=False)


def test_live_index_inventory(live_collection) -> None:
    problems = assert_index_inventory(live_collection.collection)
    assert problems == []
    assert live_collection.collection.count() == EXPECTED_CHUNK_COUNT
    scheme_ids = {scheme["scheme_id"] for scheme in load_schemes()}
    snapshot = live_collection.collection.get(include=["metadatas"])
    indexed = {(meta or {}).get("scheme_id") for meta in snapshot["metadatas"]}
    assert indexed == scheme_ids


def test_live_filtered_probes_hit_at_1(live_collection) -> None:
    results = run_probes(FILTERED_PROBES, collection=live_collection.collection)
    failed = [f"{r.probe.id}: {r.reasons}" for r in results if not r.passed]
    assert failed == []


def test_live_collision_probes_stay_on_named_scheme(live_collection) -> None:
    sensex = retrieve(
        "What is the expense ratio of HDFC BSE Sensex Index Fund Direct Growth?",
        scheme_id=SENSEX_ID,
        collection=live_collection.collection,
    )
    silver = retrieve(
        "What is the expense ratio of HDFC Silver ETF FoF Direct Growth?",
        scheme_id=SILVER_ID,
        collection=live_collection.collection,
    )
    assert sensex[0].chunk_id == f"{SENSEX_ID}::expense_ratio"
    assert silver[0].chunk_id == f"{SILVER_ID}::expense_ratio"
    assert all(hit.scheme_id != SILVER_ID for hit in sensex)
    assert all(hit.scheme_id != SENSEX_ID for hit in silver)

    mid = retrieve(
        "What is the exit load for HDFC Mid Cap Fund Direct Growth?",
        scheme_id=MIDCAP_ID,
        collection=live_collection.collection,
    )
    large = retrieve(
        "What is the exit load for HDFC Large Cap Fund Direct Growth?",
        scheme_id=LARGE_ID,
        collection=live_collection.collection,
    )
    assert mid[0].chunk_id == f"{MIDCAP_ID}::exit_load"
    assert large[0].chunk_id == f"{LARGE_ID}::exit_load"
    assert all(hit.scheme_id != LARGE_ID for hit in mid)
    assert all(hit.scheme_id != MIDCAP_ID for hit in large)
