"""Offline retrieval check against groww_scheme_facts (Phase 1 task 6).

Usage:
    python -m src.ingest.retrieve_check
    python -m src.ingest.retrieve_check --diagnostics

No Groq. Pass = filtered probes hit expected section at rank 1; miss probes
return no atom of the absent section. Unfiltered searches are diagnostic only.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Sequence

from src.config import PROJECT_ROOT
from src.ingest.embed_index import (
    COLLECTION_NAME,
    EXPECTED_CHUNK_COUNT,
    EXPECTED_SCHEME_COUNT,
    IndexNotReadyError,
    open_index,
)
from src.rag.retriever import DEFAULT_TOP_K, RetrievalHit, retrieve

MIDCAP_ID = "hdfc_mid_cap_direct_growth"
SILVER_ID = "hdfc_silver_etf_fof_direct_growth"
SENSEX_ID = "hdfc_bse_sensex_index_direct_growth"
LARGE_ID = "hdfc_large_cap_direct_growth"
ELSS_ID = "hdfc_elss_tax_saver_direct_growth"

PERFORMANCE_NOISE = (
    "Would've become",
    "Historic returns",
    "Return calculator",
    "Category average",
    "Over the past",
    "Total investment",
)
ELSS_LEAK_NEEDLE = "ELSS Tax Saver"
LEAK_SCHEME_IDS = frozenset({MIDCAP_ID, LARGE_ID})


@dataclass(frozen=True)
class Probe:
    id: str
    question: str
    scheme_id: str | None
    expected_section: str | None = None
    expected_chunk_id: str | None = None
    forbidden_scheme_id: str | None = None
    expect_miss_section: str | None = None
    diagnostic: bool = False


@dataclass
class ProbeResult:
    probe: Probe
    hits: list[RetrievalHit]
    passed: bool
    reasons: list[str] = field(default_factory=list)


FILTERED_PROBES: tuple[Probe, ...] = (
    Probe(
        id="ret_expense_large_cap",
        question="What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
        scheme_id=LARGE_ID,
        expected_section="expense_ratio",
        expected_chunk_id=f"{LARGE_ID}::expense_ratio",
    ),
    Probe(
        id="ret_expense_sensex",
        question="What is the expense ratio of HDFC BSE Sensex Index Fund Direct Growth?",
        scheme_id=SENSEX_ID,
        expected_section="expense_ratio",
        expected_chunk_id=f"{SENSEX_ID}::expense_ratio",
        forbidden_scheme_id=SILVER_ID,
    ),
    Probe(
        id="ret_expense_silver",
        question="What is the expense ratio of HDFC Silver ETF FoF Direct Growth?",
        scheme_id=SILVER_ID,
        expected_section="expense_ratio",
        expected_chunk_id=f"{SILVER_ID}::expense_ratio",
        forbidden_scheme_id=SENSEX_ID,
    ),
    Probe(
        id="ret_exit_mid_cap",
        question="What is the exit load for HDFC Mid Cap Fund Direct Growth?",
        scheme_id=MIDCAP_ID,
        expected_section="exit_load",
        expected_chunk_id=f"{MIDCAP_ID}::exit_load",
        forbidden_scheme_id=LARGE_ID,
    ),
    Probe(
        id="ret_exit_large_cap",
        question="What is the exit load for HDFC Large Cap Fund Direct Growth?",
        scheme_id=LARGE_ID,
        expected_section="exit_load",
        expected_chunk_id=f"{LARGE_ID}::exit_load",
        forbidden_scheme_id=MIDCAP_ID,
    ),
    Probe(
        id="ret_exit_sensex",
        question="What is the exit load for HDFC BSE Sensex Index Fund Direct Growth?",
        scheme_id=SENSEX_ID,
        expected_section="exit_load",
        expected_chunk_id=f"{SENSEX_ID}::exit_load",
    ),
    Probe(
        id="ret_exit_elss",
        question="What is the exit load for HDFC ELSS Tax Saver Fund?",
        scheme_id=ELSS_ID,
        expected_section="exit_load",
        expected_chunk_id=f"{ELSS_ID}::exit_load",
    ),
    Probe(
        id="ret_sip_elss",
        question="What is the minimum SIP for HDFC ELSS Tax Saver Fund?",
        scheme_id=ELSS_ID,
        expected_section="sip",
        expected_chunk_id=f"{ELSS_ID}::sip",
    ),
    Probe(
        id="ret_sip_mid_cap",
        question="What is the minimum SIP for HDFC Mid Cap Fund Direct Growth?",
        scheme_id=MIDCAP_ID,
        expected_section="sip",
        expected_chunk_id=f"{MIDCAP_ID}::sip",
    ),
    Probe(
        id="ret_lockin_elss",
        question="What is the lock-in period for HDFC ELSS Tax Saver Fund?",
        scheme_id=ELSS_ID,
        expected_section="lock_in",
        expected_chunk_id=f"{ELSS_ID}::lock_in",
    ),
    Probe(
        id="ret_lockin_silver_miss",
        question="What is the lock-in for HDFC Silver ETF FoF?",
        scheme_id=SILVER_ID,
        expect_miss_section="lock_in",
    ),
    Probe(
        id="ret_benchmark_sensex",
        question="What is the benchmark of HDFC BSE Sensex Index Fund Direct Growth?",
        scheme_id=SENSEX_ID,
        expected_section="benchmark",
        expected_chunk_id=f"{SENSEX_ID}::benchmark",
    ),
    Probe(
        id="ret_process_silver",
        question="What is the stamp duty on HDFC Silver ETF FoF Direct Growth?",
        scheme_id=SILVER_ID,
        expected_section="process",
        expected_chunk_id=f"{SILVER_ID}::process",
    ),
    Probe(
        id="ret_riskometer_mid_miss",
        question="What is the risk level / riskometer of HDFC Mid Cap Fund?",
        scheme_id=MIDCAP_ID,
        expect_miss_section="riskometer",
    ),
)

UNFILTERED_DIAGNOSTICS: tuple[Probe, ...] = (
    Probe(
        id="diag_ter_022_unfiltered",
        question="What is the expense ratio of HDFC BSE Sensex Index Fund Direct Growth?",
        scheme_id=None,
        diagnostic=True,
    ),
    Probe(
        id="diag_sip_100_unfiltered",
        question="What is the minimum SIP for HDFC Mid Cap Fund Direct Growth?",
        scheme_id=None,
        diagnostic=True,
    ),
    Probe(
        id="diag_stamp_duty_unfiltered",
        question="What is the stamp duty on HDFC Silver ETF FoF Direct Growth?",
        scheme_id=None,
        diagnostic=True,
    ),
    Probe(
        id="diag_exit_1yr_unfiltered",
        question="What is the exit load for HDFC Mid Cap Fund Direct Growth?",
        scheme_id=None,
        diagnostic=True,
    ),
)


def _preview(text: str, width: int = 80) -> str:
    compact = " ".join((text or "").split()).replace("₹", "Rs")
    if len(compact) <= width:
        return compact
    return compact[: width - 1] + "..."


def _hit_noise(hit: RetrievalHit) -> list[str]:
    reasons: list[str] = []
    blob = hit.text
    for token in PERFORMANCE_NOISE:
        if token.lower() in blob.lower():
            reasons.append(f"performance noise {token!r} in {hit.chunk_id}")
    if hit.scheme_id in LEAK_SCHEME_IDS and ELSS_LEAK_NEEDLE in blob:
        reasons.append(f"ELSS display-name leak in {hit.chunk_id}")
    if hit.section == "riskometer":
        reasons.append(f"fabricated riskometer atom {hit.chunk_id}")
    return reasons


def evaluate_probe(probe: Probe, hits: Sequence[RetrievalHit]) -> ProbeResult:
    reasons: list[str] = []
    for hit in hits:
        reasons.extend(_hit_noise(hit))

    if probe.expect_miss_section:
        leaked = [hit for hit in hits if hit.section == probe.expect_miss_section]
        if leaked:
            reasons.append(
                f"expected miss of section={probe.expect_miss_section!r} "
                f"but found {[hit.chunk_id for hit in leaked]}"
            )
        passed = not reasons
        return ProbeResult(probe=probe, hits=list(hits), passed=passed, reasons=reasons)

    if not hits:
        reasons.append("no hits returned")
        return ProbeResult(probe=probe, hits=[], passed=False, reasons=reasons)

    top = hits[0]
    if probe.scheme_id and top.scheme_id != probe.scheme_id:
        reasons.append(
            f"rank-1 scheme_id={top.scheme_id!r} != {probe.scheme_id!r}"
        )
    if probe.forbidden_scheme_id and any(
        hit.scheme_id == probe.forbidden_scheme_id for hit in hits
    ):
        reasons.append(
            f"collision: found forbidden scheme_id={probe.forbidden_scheme_id!r}"
        )
    if probe.expected_section and top.section != probe.expected_section:
        reasons.append(
            f"rank-1 section={top.section!r} != {probe.expected_section!r}"
        )
    if probe.expected_chunk_id and top.chunk_id != probe.expected_chunk_id:
        reasons.append(
            f"rank-1 chunk_id={top.chunk_id!r} != {probe.expected_chunk_id!r}"
        )
    passed = not reasons
    return ProbeResult(probe=probe, hits=list(hits), passed=passed, reasons=reasons)


def format_hits(hits: Sequence[RetrievalHit], *, scheme_filter: str | None) -> list[str]:
    filter_label = scheme_filter or "(none)"
    lines: list[str] = []
    if not hits:
        lines.append(f"  filter={filter_label}  (no hits)")
        return lines
    for hit in hits:
        lines.append(
            f"  rank={hit.rank} dist={hit.distance:.4f} "
            f"chunk_id={hit.chunk_id} section={hit.section} "
            f"scheme_id={hit.scheme_id} filter={filter_label} "
            f"text={_preview(hit.text)!r}"
        )
    return lines


def run_probes(
    probes: Sequence[Probe],
    *,
    chroma_path: Path | str | None = None,
    collection: Any | None = None,
    top_k: int = DEFAULT_TOP_K,
) -> list[ProbeResult]:
    results: list[ProbeResult] = []
    for probe in probes:
        hits = retrieve(
            probe.question,
            scheme_id=probe.scheme_id,
            top_k=top_k,
            chroma_path=chroma_path,
            collection=collection,
        )
        results.append(evaluate_probe(probe, hits))
    return results


def assert_index_inventory(collection: Any) -> list[str]:
    problems: list[str] = []
    count = collection.count()
    if count != EXPECTED_CHUNK_COUNT:
        problems.append(
            f"collection count {count} != {EXPECTED_CHUNK_COUNT}"
        )
    snapshot = collection.get(include=["metadatas", "documents"])
    metas = snapshot.get("metadatas") or []
    docs = snapshot.get("documents") or []
    scheme_ids = {(meta or {}).get("scheme_id") for meta in metas}
    if len(scheme_ids) != EXPECTED_SCHEME_COUNT:
        problems.append(f"scheme count {len(scheme_ids)} != {EXPECTED_SCHEME_COUNT}")
    for meta, text in zip(metas, docs):
        meta = meta or {}
        if (meta.get("section") or "") == "riskometer":
            problems.append(f"riskometer section in index: {meta.get('chunk_id')}")
        if "riskometer" in (text or "").lower():
            problems.append(f"riskometer text in {(meta.get('scheme_id'))}")
        scheme_id = meta.get("scheme_id") or ""
        if scheme_id in LEAK_SCHEME_IDS and ELSS_LEAK_NEEDLE in (text or ""):
            problems.append(f"ELSS leak in {meta.get('scheme_id')}")
        for token in PERFORMANCE_NOISE:
            if token.lower() in (text or "").lower():
                problems.append(f"performance noise in {meta.get('scheme_id')}: {token}")
    return problems


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Offline retrieval probes against groww_scheme_facts (no Groq)."
    )
    parser.add_argument(
        "--diagnostics",
        action="store_true",
        help="Also print unfiltered searches (not a pass/fail gate).",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="Hits per probe (default 3, max 5).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        opened = open_index(create=False)
    except IndexNotReadyError as exc:
        print(exc)
        return 1

    inventory = assert_index_inventory(opened.collection)
    if inventory:
        print("Index inventory failed:")
        for problem in inventory:
            print(f"  - {problem}")
        return 1

    print(
        f"{COLLECTION_NAME}: {opened.collection.count()} vectors at "
        f"{_rel(opened.path)}"
    )

    gated = run_probes(
        FILTERED_PROBES,
        collection=opened.collection,
        top_k=args.top_k,
    )
    failed = 0
    for result in gated:
        status = "PASS" if result.passed else "FAIL"
        if not result.passed:
            failed += 1
        print(f"[{status}] {result.probe.id}: {result.probe.question}")
        for line in format_hits(result.hits, scheme_filter=result.probe.scheme_id):
            print(line)
        for reason in result.reasons:
            print(f"  reason: {reason}")

    if args.diagnostics:
        print("\nUnfiltered diagnostics (not gated):")
        diag = run_probes(
            UNFILTERED_DIAGNOSTICS,
            collection=opened.collection,
            top_k=args.top_k,
        )
        for result in diag:
            schemes = sorted({hit.scheme_id for hit in result.hits})
            mixed = len(schemes) > 1
            print(
                f"[DIAG] {result.probe.id}: mixed_schemes={mixed} "
                f"scheme_ids={schemes}"
            )
            for line in format_hits(result.hits, scheme_filter=None):
                print(line)

    if failed:
        print(f"\n{failed}/{len(gated)} gated probes failed.")
        return 1
    print(f"\n{len(gated)}/{len(gated)} gated probes passed.")
    return 0


def _rel(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


if __name__ == "__main__":
    sys.exit(main())
