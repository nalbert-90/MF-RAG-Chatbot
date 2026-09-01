"""Phase 1 ingest CLI: chunk if needed, then embed + upsert Chroma.

Usage:
    python -m src.ingest.run
    python -m src.ingest.run --rebuild
    python -m src.ingest.run --chunk --rebuild
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from src.config import PROJECT_ROOT
from src.ingest.chunk import CHUNKS_PATH, chunk_all, persist_results
from src.ingest.embed_index import EXPECTED_CHUNK_COUNT, embed_index


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Chunk processed Groww pages if needed, then upsert Chroma."
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete collection groww_scheme_facts before upsert (drops stale ids).",
    )
    parser.add_argument(
        "--chunk",
        action="store_true",
        help="Re-run the fact-atom chunker before embedding.",
    )
    parser.add_argument(
        "--skip-chunk",
        action="store_true",
        help="Never run the chunker; fail if chunks.jsonl is missing.",
    )
    parser.add_argument(
        "--scheme",
        help="With --chunk, only re-chunk this scheme_id (merge into jsonl).",
    )
    parser.add_argument(
        "--chunks",
        type=Path,
        default=None,
        help="Path to chunks.jsonl (default: data/processed/chunks.jsonl).",
    )
    return parser.parse_args(argv)


def maybe_chunk(*, force: bool, skip: bool, scheme_id: str | None, chunks_path: Path) -> int:
    if skip:
        if not chunks_path.is_file():
            raise FileNotFoundError(
                f"No chunks at {chunks_path}. Run without --skip-chunk or "
                "`python -m src.ingest.chunk` first."
            )
        return 0
    if not force and chunks_path.is_file():
        return 0

    results = chunk_all(scheme_id=scheme_id)
    failed = sum(1 for result in results if result.status == "failed")
    for result in results:
        line = f"chunk {result.scheme_id}: {result.status}"
        if result.status == "ok":
            line += f" ({result.chunk_count} chunks)"
        if result.error:
            line += f" — {result.error}"
        print(line)
    written = 0
    if any(result.status == "ok" for result in results):
        persist_results(results, merge=bool(scheme_id))
        written = sum(result.chunk_count for result in results if result.status == "ok")
        try:
            rel = chunks_path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            rel = chunks_path
        print(f"Wrote {written} chunks -> {rel}")
    if failed:
        raise RuntimeError(f"Chunker failed for {failed} scheme(s).")
    return written


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    chunks_path = args.chunks or CHUNKS_PATH
    maybe_chunk(
        force=args.chunk,
        skip=args.skip_chunk,
        scheme_id=args.scheme,
        chunks_path=chunks_path,
    )
    stats = embed_index(
        chunks_path=chunks_path,
        rebuild=args.rebuild,
        expected_count=EXPECTED_CHUNK_COUNT if chunks_path == CHUNKS_PATH else None,
    )
    try:
        rel = stats.chroma_path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        rel = stats.chroma_path
    print(
        f"Indexed {stats.count} chunks into {stats.collection} at {rel}"
        f"{' (rebuilt)' if stats.rebuilt else ''}"
    )
    print(f"schemes: {', '.join(stats.scheme_ids)}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
