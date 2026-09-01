"""Daily ingest pipeline: fetch → parse → chunk → embed → validate.

Chains the Phase 1 ingest steps used by the GitHub Actions scheduler (Phase 6)
and the manual re-ingest playbook (Phase 5).

Usage:
    python -m src.ingest.pipeline
    python -m src.ingest.pipeline --strict-fetch
    python -m src.ingest.pipeline --offline          # local recovery only
"""

from __future__ import annotations

import argparse
import os
import subprocess
import sys
from datetime import datetime, timezone
from pathlib import Path

from src.ingest.allowlist import is_allowlisted_citation_url
from src.ingest.chunk import CHUNKS_PATH, load_chunks_jsonl
from src.ingest.embed_index import EXPECTED_CHUNK_COUNT, open_index
from src.ingest.fetch import fetch_all
from src.ingest.retrieve_check import assert_index_inventory

PIPELINE_STEPS: tuple[str, ...] = (
    "fetch",
    "parse",
    "chunk",
    "embed",
    "retrieve_check",
    "pytest",
)


def _log(step: str, message: str) -> None:
    print(f"[pipeline:{step}] {message}", flush=True)


def _run_module(step: str, module: str, *args: str) -> int:
    cmd = [sys.executable, "-m", module, *args]
    _log(step, " ".join(cmd))
    completed = subprocess.run(cmd, check=False)
    if completed.returncode != 0:
        _log(step, f"failed with exit code {completed.returncode}")
    return completed.returncode


def run_fetch(*, offline: bool, strict: bool) -> int:
    results = fetch_all(offline=offline)
    failed = 0
    non_ok = 0
    for result in results:
        line = f"{result.scheme_id}: {result.status}"
        if result.sha256:
            line += f" sha256={result.sha256[:12]}... ({result.bytes} bytes)"
        if result.error:
            line += f" — {result.error}"
        _log("fetch", line)
        if result.status == "failed":
            failed += 1
        if result.status != "ok":
            non_ok += 1

    if failed:
        _log("fetch", f"{failed} scheme(s) failed — aborting pipeline")
        return 1
    if strict and non_ok:
        _log(
            "fetch",
            "strict-fetch: refusing manual_fallback / non-live HTML "
            "(scheduled jobs must fetch fresh Groww pages)",
        )
        return 1
    return 0


def print_ingest_summary() -> dict[str, str | int]:
    rows = load_chunks_jsonl(CHUNKS_PATH)
    dates = sorted(
        {str(row.get("published_or_as_of") or "") for row in rows if row.get("published_or_as_of")}
    )
    ingested = sorted(
        {str(row.get("ingested_at") or "") for row in rows if row.get("ingested_at")}
    )
    opened = open_index(create=False)
    count = opened.collection.count()
    inventory = assert_index_inventory(opened.collection)

    bad_citations = [
        row["chunk_id"]
        for row in rows
        if not is_allowlisted_citation_url(str(row.get("citation_url") or ""))
    ]

    summary = {
        "chunk_count": len(rows),
        "expected_chunk_count": EXPECTED_CHUNK_COUNT,
        "chroma_count": count,
        "published_or_as_of_min": dates[0] if dates else "",
        "published_or_as_of_max": dates[-1] if dates else "",
        "ingested_at_min": ingested[0] if ingested else "",
        "ingested_at_max": ingested[-1] if ingested else "",
        "inventory_ok": not inventory,
        "bad_citation_count": len(bad_citations),
    }

    _log("summary", f"chunks={len(rows)} chroma_vectors={count}")
    if dates:
        _log("summary", f"published_or_as_of range: {dates[0]} .. {dates[-1]}")
    if ingested:
        _log("summary", f"ingested_at range: {ingested[0]} .. {ingested[-1]}")
    if inventory:
        for problem in inventory:
            _log("summary", f"inventory problem: {problem}")
    if bad_citations:
        _log("summary", f"non-allowlisted citations: {bad_citations[:5]}")

    return summary


def write_github_step_summary(summary: dict[str, str | int]) -> None:
    path = os.environ.get("GITHUB_STEP_SUMMARY")
    if not path:
        return

    completed_at = datetime.now(timezone.utc).strftime("%Y-%m-%d %H:%M:%S UTC")
    body = f"""## Daily ingest summary

| Field | Value |
|-------|-------|
| Completed | {completed_at} |
| Chunks | {summary.get("chunk_count")} |
| Chroma vectors | {summary.get("chroma_count")} |
| `published_or_as_of` (min) | {summary.get("published_or_as_of_min")} |
| `published_or_as_of` (max) | {summary.get("published_or_as_of_max")} |
| `ingested_at` (max) | {summary.get("ingested_at_max")} |
| Inventory OK | {summary.get("inventory_ok")} |
"""
    Path(path).write_text(body, encoding="utf-8")


def run_pipeline(
    *,
    offline: bool = False,
    strict_fetch: bool = False,
    skip_pytest: bool = False,
) -> int:
    started = datetime.now(timezone.utc)
    _log("start", f"daily ingest at {started.isoformat()}")

    steps: list[tuple[str, int]] = []

    if run_fetch(offline=offline, strict=strict_fetch) != 0:
        return 1
    steps.append(("fetch", 0))

    for step, module, args in (
        ("parse", "src.ingest.parse", ()),
        ("chunk", "src.ingest.run", ("--chunk",)),
        ("embed", "src.ingest.run", ("--rebuild",)),
        ("retrieve_check", "src.ingest.retrieve_check", ()),
    ):
        code = _run_module(step, module, *args)
        steps.append((step, code))
        if code != 0:
            return code

    if not skip_pytest:
        code = _run_module(
            "pytest",
            "pytest",
            "tests/test_retrieval_facts.py",
            "-m",
            "not integration",
            "--tb=short",
            "-q",
        )
        steps.append(("pytest", code))
        if code != 0:
            return code

    try:
        summary = print_ingest_summary()
    except Exception as exc:
        _log("summary", f"failed: {exc}")
        return 1

    if summary.get("bad_citation_count"):
        _log("summary", "citation allowlist check failed")
        return 1
    if not summary.get("inventory_ok"):
        _log("summary", "index inventory check failed")
        return 1

    write_github_step_summary(summary)
    elapsed = (datetime.now(timezone.utc) - started).total_seconds()
    _log("done", f"pipeline completed in {elapsed:.0f}s")
    return 0


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Run the full Groww ingest pipeline (Phase 6 daily ingest)."
    )
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Fetch step uses local HTML only (manual recovery; not for scheduled runs).",
    )
    parser.add_argument(
        "--strict-fetch",
        action="store_true",
        help="Fail if any scheme fetch is not status=ok (no manual_fallback).",
    )
    parser.add_argument(
        "--skip-pytest",
        action="store_true",
        help="Skip retrieval pytest gate (retrieve_check still runs).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    if args.offline and args.strict_fetch:
        print("Cannot combine --offline with --strict-fetch.", file=sys.stderr)
        return 1
    return run_pipeline(
        offline=args.offline,
        strict_fetch=args.strict_fetch,
        skip_pytest=args.skip_pytest,
    )


if __name__ == "__main__":
    raise SystemExit(main())
