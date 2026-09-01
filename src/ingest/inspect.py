"""Inspect stored MiniLM vectors and run example retrieval (no Groq).

Usage:
    python -m src.ingest.inspect
    python -m src.ingest.inspect --scheme hdfc_elss_tax_saver_direct_growth
    python -m src.ingest.inspect --full
    python -m src.ingest.inspect --query "What is the lock-in period for HDFC ELSS Tax Saver Fund?" --scheme-id hdfc_elss_tax_saver_direct_growth
    python -m src.ingest.inspect --out data/processed/embeddings.tsv

Requires a built index: python -m src.ingest.run --rebuild
"""

from __future__ import annotations

import argparse
import csv
import sys
from pathlib import Path
from typing import Any, Sequence

from src.config import PROJECT_ROOT, get_settings
from src.ingest.embed_index import (
    COLLECTION_NAME,
    IndexNotReadyError,
    get_embedding_function,
    open_index,
)
from src.ingest.retrieve_check import (
    FILTERED_PROBES,
    UNFILTERED_DIAGNOSTICS,
    Probe,
    _preview,
)
from src.rag.retriever import DEFAULT_TOP_K, retrieve

DEMO_PROBE_IDS = (
    "ret_expense_large_cap",
    "ret_expense_sensex",
    "ret_exit_mid_cap",
    "ret_sip_elss",
    "ret_lockin_elss",
    "ret_lockin_silver_miss",
    "ret_benchmark_sensex",
    "ret_riskometer_mid_miss",
)


def _safe_print(text: str = "") -> None:
    encoding = getattr(sys.stdout, "encoding", None) or "utf-8"
    line = (text + "\n").replace("₹", "Rs")
    try:
        sys.stdout.write(line)
    except UnicodeEncodeError:
        sys.stdout.buffer.write(line.encode(encoding, errors="replace"))
        sys.stdout.buffer.flush()


def _rel(path: Path) -> str:
    try:
        return path.relative_to(PROJECT_ROOT).as_posix()
    except ValueError:
        return str(path)


def _as_floats(vector: Any) -> list[float]:
    return [float(x) for x in list(vector)]


def format_vector(vector: Sequence[float], *, dims: int, full: bool) -> str:
    values = list(vector)
    if not values:
        return "[]"
    if full or dims >= len(values):
        body = ", ".join(f"{x:.4f}" for x in values)
        return f"[{body}]  dim={len(values)}"
    shown = values[: max(1, dims)]
    body = ", ".join(f"{x:.4f}" for x in shown)
    return f"[{body}, ...]  dim={len(values)}  showing {len(shown)}"


def load_rows(
    collection: Any,
    *,
    scheme_id: str | None = None,
) -> list[dict[str, Any]]:
    kwargs: dict[str, Any] = {"include": ["embeddings", "documents", "metadatas"]}
    if scheme_id:
        kwargs["where"] = {"scheme_id": scheme_id}
    raw = collection.get(**kwargs)
    ids = raw.get("ids") or []
    embeddings = raw.get("embeddings")
    if embeddings is None:
        embeddings = []
    documents = raw.get("documents") or []
    metadatas = raw.get("metadatas") or []
    rows: list[dict[str, Any]] = []
    for i, chunk_id in enumerate(ids):
        meta = metadatas[i] if i < len(metadatas) else None
        meta = meta or {}
        vec = embeddings[i] if i < len(embeddings) else []
        rows.append(
            {
                "chunk_id": str(chunk_id),
                "scheme_id": str(meta.get("scheme_id") or ""),
                "section": str(meta.get("section") or ""),
                "title": str(meta.get("title") or ""),
                "text": str(documents[i] if i < len(documents) else ""),
                "citation_url": str(meta.get("citation_url") or ""),
                "published_or_as_of": str(meta.get("published_or_as_of") or ""),
                "embedding": _as_floats(vec),
            }
        )
    rows.sort(key=lambda row: (row["scheme_id"], row["chunk_id"]))
    return rows


def print_catalog(rows: Sequence[dict[str, Any]], *, dims: int, full: bool) -> None:
    if not rows:
        _safe_print("No embeddings in the collection.")
        return
    dim = len(rows[0]["embedding"]) if rows[0]["embedding"] else 0
    _safe_print(f"Stored embeddings: {len(rows)} vectors  dim={dim}")
    _safe_print("")
    current_scheme = None
    for i, row in enumerate(rows, start=1):
        if row["scheme_id"] != current_scheme:
            current_scheme = row["scheme_id"]
            _safe_print(f"--- {current_scheme} ---")
        _safe_print(f"{i:02d}. {row['chunk_id']}")
        _safe_print(f"    section={row['section']}  title={row['title']}")
        _safe_print(f"    text={_preview(row['text'], 100)!r}")
        _safe_print(f"    vec={format_vector(row['embedding'], dims=dims, full=full)}")
        _safe_print()


def write_tsv(rows: Sequence[dict[str, Any]], path: Path) -> None:
    dim = max((len(row["embedding"]) for row in rows), default=0)
    path.parent.mkdir(parents=True, exist_ok=True)
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.writer(handle, delimiter="\t")
        header = [
            "chunk_id",
            "scheme_id",
            "section",
            "title",
            "text",
            "citation_url",
            "published_or_as_of",
            *[f"e{i}" for i in range(dim)],
        ]
        writer.writerow(header)
        for row in rows:
            vec = row["embedding"] + [""] * (dim - len(row["embedding"]))
            writer.writerow(
                [
                    row["chunk_id"],
                    row["scheme_id"],
                    row["section"],
                    row["title"],
                    row["text"],
                    row["citation_url"],
                    row["published_or_as_of"],
                    *vec,
                ]
            )


def print_retrieval(
    question: str,
    *,
    scheme_id: str | None,
    collection: Any,
    top_k: int,
    show_query_vec: bool,
    dims: int,
    full: bool,
) -> None:
    filter_label = scheme_id or "(none — unfiltered diagnostic)"
    _safe_print(f"Q: {question}")
    _safe_print(f"   filter scheme_id={filter_label}")
    if show_query_vec:
        ef = get_embedding_function()
        qvec = _as_floats(ef([question])[0])
        _safe_print(f"   query_vec={format_vector(qvec, dims=dims, full=full)}")
    hits = retrieve(
        question,
        scheme_id=scheme_id,
        top_k=top_k,
        collection=collection,
    )
    if not hits:
        _safe_print("   (no hits)")
        _safe_print()
        return
    for hit in hits:
        _safe_print(
            f"   rank={hit.rank}  dist={hit.distance:.4f}  "
            f"section={hit.section}  {hit.chunk_id}"
        )
        _safe_print(f"          {_preview(hit.text, 100)}")
    _safe_print()


def demo_probes(*, all_probes: bool) -> list[Probe]:
    if all_probes:
        return list(FILTERED_PROBES) + list(UNFILTERED_DIAGNOSTICS)
    by_id = {probe.id: probe for probe in FILTERED_PROBES}
    return [by_id[probe_id] for probe_id in DEMO_PROBE_IDS if probe_id in by_id]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Print stored MiniLM embeddings and example retrievals."
    )
    parser.add_argument(
        "--scheme",
        help="Only show stored vectors for this scheme_id.",
    )
    parser.add_argument(
        "--dims",
        type=int,
        default=8,
        help="How many leading vector values to print (default 8).",
    )
    parser.add_argument(
        "--full",
        action="store_true",
        help="Print all 384 dimensions (very wide).",
    )
    parser.add_argument(
        "--embeddings-only",
        action="store_true",
        help="Skip example retrieval.",
    )
    parser.add_argument(
        "--retrieval-only",
        action="store_true",
        help="Skip the stored-vector catalog.",
    )
    parser.add_argument(
        "--all-probes",
        action="store_true",
        help="Run the full retrieve_check probe table, including unfiltered diagnostics.",
    )
    parser.add_argument(
        "--query",
        help="Run one custom question instead of the demo retrieval set.",
    )
    parser.add_argument(
        "--scheme-id",
        help="scheme_id filter for --query (required for the production retrieve path).",
    )
    parser.add_argument(
        "--show-query-vec",
        action="store_true",
        help="Also print the MiniLM vector for each question.",
    )
    parser.add_argument(
        "--top-k",
        type=int,
        default=DEFAULT_TOP_K,
        help="Hits per retrieval example (default 3, max 5).",
    )
    parser.add_argument(
        "--out",
        type=Path,
        help="Write all stored vectors to a TSV file (chunk metadata + e0..e383).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    try:
        opened = open_index(create=False)
    except IndexNotReadyError as exc:
        _safe_print(str(exc))
        return 1

    settings = get_settings()
    _safe_print(f"collection: {COLLECTION_NAME}")
    _safe_print(f"path:       {_rel(opened.path)}")
    _safe_print(f"model:      {settings.embedding_model}  (cosine, normalized)")
    _safe_print(f"count:      {opened.collection.count()}")
    _safe_print("")

    rows = load_rows(opened.collection, scheme_id=args.scheme)
    if args.out:
        out_path = args.out if args.out.is_absolute() else PROJECT_ROOT / args.out
        write_tsv(rows, out_path)
        _safe_print(f"Wrote TSV -> {_rel(out_path)}")
        _safe_print("")

    if not args.retrieval_only:
        print_catalog(rows, dims=args.dims, full=args.full)

    if args.embeddings_only:
        return 0

    _safe_print("=" * 72)
    _safe_print("Example retrieval (MiniLM + scheme_id filter, no Groq)")
    _safe_print("Lower cosine distance = closer. Rank-1 section is the retrieved fact.")
    _safe_print("=" * 72)
    _safe_print("")

    if args.query:
        print_retrieval(
            args.query,
            scheme_id=args.scheme_id,
            collection=opened.collection,
            top_k=args.top_k,
            show_query_vec=args.show_query_vec,
            dims=args.dims,
            full=args.full,
        )
        return 0

    for probe in demo_probes(all_probes=args.all_probes):
        print_retrieval(
            probe.question,
            scheme_id=probe.scheme_id,
            collection=opened.collection,
            top_k=args.top_k,
            show_query_vec=args.show_query_vec,
            dims=args.dims,
            full=args.full,
        )
    return 0


if __name__ == "__main__":
    sys.exit(main())
