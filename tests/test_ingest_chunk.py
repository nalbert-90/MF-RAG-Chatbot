import json
from pathlib import Path

import pytest

from src.ingest.allowlist import validate_allowlist
from src.ingest.chunk import (
    CHUNKS_FILENAME,
    chunk_all,
    chunk_scheme,
    chunk_scheme_text,
    persist_results,
    write_chunks_jsonl,
)
from src.ingest.parse import PARSE_MANIFEST_FILENAME, TEXT_FILENAME
from src.registry import load_schemes

SENSEX_ID = "hdfc_bse_sensex_index_direct_growth"
SENSEX_NAME = "HDFC BSE Sensex Index Fund - Direct Growth"
SENSEX_URL = "https://groww.in/mutual-funds/hdfc-bse-sensex-index-fund-direct-growth"
MIDCAP_ID = "hdfc_mid_cap_direct_growth"
ELSS_ID = "hdfc_elss_tax_saver_direct_growth"
ELSS_NAME = "HDFC ELSS Tax Saver Fund - Direct Plan Growth"
ELSS_URL = "https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth"

SAMPLE_SENSEX = """\
NAV: 28 Aug '26 ₹739.71 Min. for SIP ₹100 Fund size (AUM) ₹8,657.46 Cr Expense ratio 0.22% Rating 1
Exit load, stamp duty and tax Exit load Exit load of 0.25% if redeemed within 3 days Stamp duty on investment: 0.005% (from July 1st, 2020) from July 1st 2020 Tax implication If you redeem within one year, returns are taxed at 20%. If you redeem after one year, returns exceeding Rs 1.25 lakh in a financial year are taxed at 12.5%. Check past data
Fund benchmark BSE Sensex Total Return Index Scheme Information Document(SID)
### Return calculator
Over the past
Total investment
Would've become
Historic returns
1 year
₹60,000
+ 15.14 %
### Returns and rankings
Fund returns
+6.9%
Category average ( Equity Large Cap )
### Exit load, stamp duty and tax
#### Exit load
#### Stamp duty on investment: 0.005% (from July 1st, 2020)
#### Tax implication
### Fund management
### AA Arun Agarwal Aug 2020 - Present View details
### NM Nandita Menezes Mar 2025 - Present View details
### About HDFC BSE Sensex Index Fund Direct Growth
#### Investment Objective
### Fund house
Fund benchmark: BSE Sensex Total Return Index
"""

SAMPLE_ELSS = """\
Lock-in period: 3Y
NAV: 28 Aug '26 ₹1,512.86 Min. for SIP ₹500 Fund size (AUM) ₹16,095.45 Cr Expense ratio 1.19% Rating 5
Exit load, stamp duty and tax Exit load Nil Stamp duty on investment: 0.005% (from July 1st, 2020) from July 1st 2020 Tax implication If you redeem within one year, returns are taxed at 20%. Check past data
Fund benchmark NIFTY 500 Total Return Index Scheme Information Document(SID)
### Return calculator
Historic returns
### Fund management
### AK Amar Kalkundrikar Dec 2025 - Present View details
### DM Dhruv Muchhal Jun 2023 - Present View details
"""

SAMPLE_MIDCAP_WITH_LEAK = """\
NAV: 28 Aug '26 ₹237.07 Min. for SIP ₹100 Fund size (AUM) ₹1,05,142.69 Cr Expense ratio 0.74% Rating 5
Exit load, stamp duty and tax Exit load Exit load of 1% if redeemed within 1 year. Stamp duty on investment: 0.005% (from July 1st, 2020) from July 1st 2020 Tax implication If you redeem within one year, returns are taxed at 20%. Check past data
Fund benchmark NIFTY Midcap 150 Total Return Index Scheme Information Document(SID)
HDFC ELSS Tax Saver Fund Direct Plan Growth
### Return calculator
Would've become
### Fund management
### CS Chirag Setalvad Jan 2013 - Present View details
"""

INGESTED_AT = "2026-08-31T16:00:00+00:00"
PERFORMANCE_NOISE = (
    "Would've become",
    "Historic returns",
    "Return calculator",
    "Category average",
    "Over the past",
    "Total investment",
)


def _by_id(chunks) -> dict[str, object]:
    return {chunk.chunk_id: chunk for chunk in chunks}


def _source(scheme_id: str) -> dict:
    return next(s for s in validate_allowlist() if s["scheme_id"] == scheme_id)


def test_hero_line_splits_into_fact_atoms() -> None:
    chunks = chunk_scheme_text(
        SAMPLE_SENSEX,
        scheme_id=SENSEX_ID,
        scheme_name=SENSEX_NAME,
        citation_url=SENSEX_URL,
        ingested_at=INGESTED_AT,
        foreign_names=[ELSS_NAME],
    )
    by_id = _by_id(chunks)

    assert by_id[f"{SENSEX_ID}::expense_ratio"].text == (
        f"{SENSEX_NAME}. Expense ratio 0.22%."
    )
    assert "Min. for SIP" not in by_id[f"{SENSEX_ID}::expense_ratio"].text
    assert "Fund size" not in by_id[f"{SENSEX_ID}::expense_ratio"].text

    assert by_id[f"{SENSEX_ID}::sip"].text == f"{SENSEX_NAME}. Min. for SIP ₹100."
    assert by_id[f"{SENSEX_ID}::other::nav"].text == (
        f"{SENSEX_NAME}. NAV: 28 Aug '26 ₹739.71."
    )
    assert by_id[f"{SENSEX_ID}::other::aum"].text == (
        f"{SENSEX_NAME}. Fund size (AUM) ₹8,657.46 Cr."
    )
    assert by_id[f"{SENSEX_ID}::other::rating"].text == f"{SENSEX_NAME}. Rating 1."
    assert by_id[f"{SENSEX_ID}::exit_load"].text == (
        f"{SENSEX_NAME}. Exit load of 0.25% if redeemed within 3 days."
    )
    assert "Stamp duty" not in by_id[f"{SENSEX_ID}::exit_load"].text
    assert "0.22%" not in by_id[f"{SENSEX_ID}::exit_load"].text
    assert "BSE Sensex Total Return Index" in by_id[f"{SENSEX_ID}::benchmark"].text
    assert "Scheme Information Document" not in by_id[f"{SENSEX_ID}::benchmark"].text
    assert "Stamp duty on investment: 0.005%" in by_id[f"{SENSEX_ID}::process"].text
    assert "Tax implication" in by_id[f"{SENSEX_ID}::process"].text
    assert "Check past data" not in by_id[f"{SENSEX_ID}::process"].text
    assert "Arun Agarwal Aug 2020 - Present" in by_id[f"{SENSEX_ID}::other::managers"].text
    assert "Nandita Menezes Mar 2025 - Present" in by_id[f"{SENSEX_ID}::other::managers"].text
    assert f"{SENSEX_ID}::lock_in" not in by_id
    assert all(chunk.section != "riskometer" for chunk in chunks)


def test_elss_lock_in_and_nil_exit_load() -> None:
    chunks = chunk_scheme_text(
        SAMPLE_ELSS,
        scheme_id=ELSS_ID,
        scheme_name=ELSS_NAME,
        citation_url=ELSS_URL,
        ingested_at=INGESTED_AT,
        foreign_names=[SENSEX_NAME],
    )
    by_id = _by_id(chunks)
    assert by_id[f"{ELSS_ID}::lock_in"].text == f"{ELSS_NAME}. Lock-in period: 3Y."
    assert by_id[f"{ELSS_ID}::sip"].text.endswith("Min. for SIP ₹500.")
    assert by_id[f"{ELSS_ID}::exit_load"].text.endswith("Exit load Nil.")
    assert by_id[f"{ELSS_ID}::lock_in"].section == "lock_in"


def test_drops_cross_scheme_leak_and_performance_tables() -> None:
    chunks = chunk_scheme_text(
        SAMPLE_MIDCAP_WITH_LEAK,
        scheme_id=MIDCAP_ID,
        scheme_name="HDFC Mid Cap Fund - Direct Growth",
        citation_url="https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth",
        ingested_at=INGESTED_AT,
        foreign_names=[ELSS_NAME],
    )
    blob = "\n".join(chunk.text for chunk in chunks)
    assert "ELSS Tax Saver" not in blob
    for token in PERFORMANCE_NOISE:
        assert token.lower() not in blob.lower()
    assert "+6.9%" not in blob
    assert "Would've become" not in blob


def test_published_or_as_of_from_nav_date() -> None:
    chunks = chunk_scheme_text(
        SAMPLE_SENSEX,
        scheme_id=SENSEX_ID,
        scheme_name=SENSEX_NAME,
        citation_url=SENSEX_URL,
        ingested_at=INGESTED_AT,
        foreign_names=[],
    )
    assert all(chunk.published_or_as_of == "2026-08-28" for chunk in chunks)
    assert all(chunk.ingested_at == INGESTED_AT for chunk in chunks)
    assert all(chunk.source_org == "groww" for chunk in chunks)
    assert all(chunk.doc_type == "scheme_page" for chunk in chunks)
    assert all(chunk.citation_url == SENSEX_URL for chunk in chunks)


def test_published_or_as_of_falls_back_to_manifest() -> None:
    chunks = chunk_scheme_text(
        "Fund benchmark NIFTY 100 Total Return Index\n",
        scheme_id="hdfc_large_cap_direct_growth",
        scheme_name="HDFC Large Cap Fund - Direct Growth",
        citation_url="https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth",
        parse_manifest={"parsed_at": "2026-08-30T12:59:37+00:00"},
        ingested_at=INGESTED_AT,
        foreign_names=[],
    )
    assert chunks
    assert all(chunk.published_or_as_of == "2026-08-30" for chunk in chunks)


def test_rejects_non_allowlisted_citation_url() -> None:
    with pytest.raises(ValueError, match="allowlisted"):
        chunk_scheme_text(
            SAMPLE_SENSEX,
            scheme_id=SENSEX_ID,
            scheme_name=SENSEX_NAME,
            citation_url="https://www.hdfcfund.com/not-allowed",
            ingested_at=INGESTED_AT,
            foreign_names=[],
        )


def test_chunk_scheme_reads_processed_text(tmp_path: Path) -> None:
    scheme_dir = tmp_path / SENSEX_ID
    scheme_dir.mkdir(parents=True)
    (scheme_dir / TEXT_FILENAME).write_text(SAMPLE_SENSEX, encoding="utf-8")
    (scheme_dir / PARSE_MANIFEST_FILENAME).write_text(
        json.dumps(
            {
                "scheme_id": SENSEX_ID,
                "citation_url": SENSEX_URL,
                "parsed_at": "2026-08-30T12:59:37+00:00",
            }
        ),
        encoding="utf-8",
    )

    result = chunk_scheme(_source(SENSEX_ID), processed_root=tmp_path, ingested_at=INGESTED_AT)
    assert result.status == "ok"
    assert result.chunk_count >= 8
    path = persist_results([result], processed_root=tmp_path)
    assert path == tmp_path / CHUNKS_FILENAME
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    assert len(rows) == result.chunk_count
    assert rows[0]["chunk_id"].startswith(f"{SENSEX_ID}::")
    assert "section" in rows[0]
    assert "text" in rows[0]


def test_chunk_scheme_missing_text(tmp_path: Path) -> None:
    result = chunk_scheme(_source(SENSEX_ID), processed_root=tmp_path)
    assert result.status == "failed"
    assert "Missing processed text" in (result.error or "")


def test_write_chunks_jsonl_merges_by_scheme(tmp_path: Path) -> None:
    sensex = chunk_scheme_text(
        SAMPLE_SENSEX,
        scheme_id=SENSEX_ID,
        scheme_name=SENSEX_NAME,
        citation_url=SENSEX_URL,
        ingested_at=INGESTED_AT,
        foreign_names=[],
    )
    elss = chunk_scheme_text(
        SAMPLE_ELSS,
        scheme_id=ELSS_ID,
        scheme_name=ELSS_NAME,
        citation_url=ELSS_URL,
        ingested_at=INGESTED_AT,
        foreign_names=[],
    )
    path = tmp_path / CHUNKS_FILENAME
    write_chunks_jsonl(sensex + elss, path)
    replacement = chunk_scheme_text(
        SAMPLE_ELSS,
        scheme_id=ELSS_ID,
        scheme_name=ELSS_NAME,
        citation_url=ELSS_URL,
        ingested_at="2026-09-01T00:00:00+00:00",
        foreign_names=[],
    )
    write_chunks_jsonl(replacement, path, replace_scheme_ids={ELSS_ID})
    rows = [json.loads(line) for line in path.read_text(encoding="utf-8").splitlines() if line]
    elss_rows = [row for row in rows if row["scheme_id"] == ELSS_ID]
    sensex_rows = [row for row in rows if row["scheme_id"] == SENSEX_ID]
    assert sensex_rows
    assert elss_rows
    assert all(row["ingested_at"] == "2026-09-01T00:00:00+00:00" for row in elss_rows)


def test_live_processed_corpus_if_present() -> None:
    processed_root = Path("data/processed")
    sample = processed_root / SENSEX_ID / TEXT_FILENAME
    if not sample.is_file():
        pytest.skip("Processed scheme pages not present")

    results = chunk_all(processed_root=processed_root, ingested_at=INGESTED_AT)
    assert len(results) == 5
    assert all(result.status == "ok" for result in results)

    chunks = [chunk for result in results for chunk in result.chunks]
    scheme_ids = {chunk.scheme_id for chunk in chunks}
    assert scheme_ids == {scheme["scheme_id"] for scheme in load_schemes()}
    assert 45 <= len(chunks) <= 60

    by_scheme: dict[str, list] = {}
    for chunk in chunks:
        by_scheme.setdefault(chunk.scheme_id, []).append(chunk)
        assert chunk.source_org == "groww"
        assert chunk.doc_type == "scheme_page"
        assert chunk.citation_url.startswith("https://groww.in/mutual-funds/")
        assert chunk.published_or_as_of == "2026-08-28"
        assert chunk.section != "riskometer"
        assert chunk.scheme_name in chunk.text
        for token in PERFORMANCE_NOISE:
            assert token.lower() not in chunk.text.lower()

    required = {"sip", "expense_ratio", "exit_load", "benchmark", "process"}
    for scheme_id, scheme_chunks in by_scheme.items():
        sections = {chunk.section for chunk in scheme_chunks}
        assert required <= sections, scheme_id
        if scheme_id == ELSS_ID:
            assert "lock_in" in sections
            lock = next(c for c in scheme_chunks if c.section == "lock_in")
            assert "3Y" in lock.text
        else:
            assert "lock_in" not in sections

        if scheme_id in {MIDCAP_ID, "hdfc_large_cap_direct_growth"}:
            blob = "\n".join(c.text for c in scheme_chunks)
            assert "ELSS Tax Saver" not in blob

    ter = {
        chunk.scheme_id: chunk.text
        for chunk in chunks
        if chunk.section == "expense_ratio"
    }
    assert "0.22%" in ter[SENSEX_ID]
    assert "0.74%" in ter[MIDCAP_ID]
    assert "1.02%" in ter["hdfc_large_cap_direct_growth"]
    assert "1.19%" in ter[ELSS_ID]
    assert "0.22%" in ter["hdfc_silver_etf_fof_direct_growth"]

    sip = next(c for c in by_scheme[ELSS_ID] if c.section == "sip")
    assert "₹500" in sip.text
    silver_exit = next(
        c
        for c in by_scheme["hdfc_silver_etf_fof_direct_growth"]
        if c.section == "exit_load"
    )
    assert "15 days" in silver_exit.text
    silver_process = next(
        c
        for c in by_scheme["hdfc_silver_etf_fof_direct_growth"]
        if c.section == "process"
    )
    assert "two years" in silver_process.text.lower()
    silver_rating = next(
        c for c in by_scheme["hdfc_silver_etf_fof_direct_growth"] if c.chunk_id.endswith("::rating")
    )
    assert "Rating --" in silver_rating.text
