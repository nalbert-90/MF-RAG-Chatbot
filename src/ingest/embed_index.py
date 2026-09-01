"""Embed fact-atom chunks into a persistent Chroma collection (Phase 1 task 5).

Usage:
    python -m src.ingest.embed_index
    python -m src.ingest.embed_index --rebuild

Reads data/processed/chunks.jsonl (already fact-atoms) and upserts into
collection groww_scheme_facts. Does not embed raw scheme_page.txt.
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from functools import lru_cache
from pathlib import Path
from typing import Any, Sequence

from src.config import get_settings
from src.ingest.allowlist import (
    ALLOWED_DOC_TYPE,
    ALLOWED_SOURCE_ORG,
    is_allowlisted_citation_url,
    validate_allowlist,
)
from src.ingest.chunk import CHUNKS_PATH, JSONL_FIELDS, load_chunks_jsonl
from src.registry import load_schemes

COLLECTION_NAME = "groww_scheme_facts"
EXPECTED_CHUNK_COUNT = 46
EXPECTED_SCHEME_COUNT = 5
METADATA_KEYS = (
    "scheme_id",
    "scheme_name",
    "source_org",
    "doc_type",
    "section",
    "title",
    "citation_url",
    "published_or_as_of",
    "ingested_at",
)
REQUIRED_SECTIONS = frozenset(
    {"sip", "expense_ratio", "exit_load", "benchmark", "process"}
)
ELSS_SCHEME_ID = "hdfc_elss_tax_saver_direct_growth"


class IndexNotReadyError(RuntimeError):
    """Chroma collection missing or empty (edgecase RT-04)."""


class IndexValidationError(ValueError):
    """chunks.jsonl or collection metadata failed the ingest contract."""


@dataclass
class IndexStats:
    collection: str
    chroma_path: Path
    count: int
    scheme_ids: list[str]
    rebuilt: bool


@dataclass
class OpenIndex:
    client: Any
    collection: Any
    path: Path


def resolve_chroma_path(chroma_path: Path | str | None = None) -> Path:
    if chroma_path is None:
        path = get_settings().chroma_path_resolved
    else:
        path = Path(chroma_path)
        if not path.is_absolute():
            from src.config import PROJECT_ROOT

            path = PROJECT_ROOT / path
    path.mkdir(parents=True, exist_ok=True)
    return path


@lru_cache(maxsize=4)
def get_embedding_function(model_name: str | None = None) -> Any:
    """MiniLM encoder with cosine-normalized vectors. Cached per model name."""
    from chromadb.utils.embedding_functions import SentenceTransformerEmbeddingFunction

    name = model_name or get_settings().embedding_model
    return SentenceTransformerEmbeddingFunction(
        model_name=name,
        device="cpu",
        normalize_embeddings=True,
    )


def chroma_client(chroma_path: Path | str | None = None) -> Any:
    import chromadb
    from chromadb.config import Settings as ChromaSettings

    path = resolve_chroma_path(chroma_path)
    return chromadb.PersistentClient(
        path=str(path.resolve()),
        settings=ChromaSettings(anonymized_telemetry=False, allow_reset=True),
    )


def open_index(
    *,
    chroma_path: Path | str | None = None,
    create: bool = False,
    rebuild: bool = False,
    embedding_function: Any | None = None,
) -> OpenIndex:
    path = resolve_chroma_path(chroma_path)
    client = chroma_client(path)
    if not create and not rebuild:
        names = {collection.name for collection in client.list_collections()}
        if COLLECTION_NAME not in names:
            raise IndexNotReadyError(
                f"Index not ready: collection {COLLECTION_NAME!r} is missing at {path}. "
                "Run `python -m src.ingest.run --rebuild`."
            )
    ef = embedding_function or get_embedding_function()
    if rebuild:
        _delete_collection(client)
        create = True
    if create:
        collection = client.get_or_create_collection(
            name=COLLECTION_NAME,
            embedding_function=ef,
            metadata={"hnsw:space": "cosine"},
        )
    else:
        try:
            collection = client.get_collection(
                name=COLLECTION_NAME,
                embedding_function=ef,
            )
        except Exception as exc:
            raise IndexNotReadyError(
                f"Index not ready: collection {COLLECTION_NAME!r} is missing at {path}. "
                "Run `python -m src.ingest.run --rebuild`."
            ) from exc
        if collection.count() == 0:
            raise IndexNotReadyError(
                f"Index not ready: collection {COLLECTION_NAME!r} at {path} is empty. "
                "Run `python -m src.ingest.run --rebuild`."
            )
    return OpenIndex(client=client, collection=collection, path=path)


def _delete_collection(client: Any) -> None:
    try:
        client.delete_collection(COLLECTION_NAME)
    except Exception:
        pass


def chroma_metadata(row: dict[str, Any]) -> dict[str, str]:
    """Chroma only accepts str/int/float/bool metadata values (no None)."""
    meta: dict[str, str] = {}
    for key in METADATA_KEYS:
        value = row.get(key)
        if value is None:
            raise IndexValidationError(
                f"{row.get('chunk_id')}: metadata {key} must not be empty."
            )
        meta[key] = str(value)
    return meta


def validate_rows(
    rows: Sequence[dict[str, Any]],
    *,
    expected_count: int | None = None,
    require_all_schemes: bool = True,
) -> None:
    validate_allowlist()
    if not rows:
        raise IndexValidationError("chunks.jsonl is empty.")
    if expected_count is not None and len(rows) != expected_count:
        raise IndexValidationError(
            f"Expected {expected_count} chunks, found {len(rows)}."
        )

    ids = [row.get("chunk_id") for row in rows]
    if any(not chunk_id for chunk_id in ids):
        raise IndexValidationError("Every chunk must have a chunk_id.")
    if len(set(ids)) != len(ids):
        raise IndexValidationError("Duplicate chunk_id values in chunks.jsonl.")

    expected_schemes = {scheme["scheme_id"] for scheme in load_schemes()}
    scheme_ids = {row.get("scheme_id") for row in rows}
    if require_all_schemes:
        if scheme_ids != expected_schemes:
            raise IndexValidationError(
                f"Index scheme_id set {sorted(scheme_ids)} != registry {sorted(expected_schemes)}."
            )
        if len(scheme_ids) != EXPECTED_SCHEME_COUNT:
            raise IndexValidationError(
                f"Expected {EXPECTED_SCHEME_COUNT} schemes, found {len(scheme_ids)}."
            )

    by_scheme: dict[str, list[dict[str, Any]]] = {}
    for row in rows:
        for field in JSONL_FIELDS:
            if field != "title" and not row.get(field):
                raise IndexValidationError(
                    f"{row.get('chunk_id')}: missing {field}."
                )
        if row.get("scheme_id") not in expected_schemes:
            raise IndexValidationError(
                f"{row.get('chunk_id')}: unknown scheme_id {row.get('scheme_id')!r}."
            )
        if row.get("source_org") != ALLOWED_SOURCE_ORG:
            raise IndexValidationError(
                f"{row.get('chunk_id')}: source_org must be {ALLOWED_SOURCE_ORG}."
            )
        if row.get("doc_type") != ALLOWED_DOC_TYPE:
            raise IndexValidationError(
                f"{row.get('chunk_id')}: doc_type must be {ALLOWED_DOC_TYPE}."
            )
        url = row.get("citation_url") or ""
        if not is_allowlisted_citation_url(url):
            raise IndexValidationError(
                f"{row.get('chunk_id')}: citation_url {url!r} is not allowlisted."
            )
        if not (row.get("text") or "").strip():
            raise IndexValidationError(f"{row.get('chunk_id')}: empty text.")
        if row.get("section") == "riskometer":
            raise IndexValidationError(
                f"{row.get('chunk_id')}: do not index a fabricated riskometer atom."
            )
        by_scheme.setdefault(row["scheme_id"], []).append(row)

    if not require_all_schemes:
        return

    for scheme_id, scheme_rows in by_scheme.items():
        sections = {row["section"] for row in scheme_rows}
        missing = REQUIRED_SECTIONS - sections
        if missing:
            raise IndexValidationError(f"{scheme_id}: missing sections {sorted(missing)}.")
        if scheme_id == ELSS_SCHEME_ID:
            if "lock_in" not in sections:
                raise IndexValidationError(f"{scheme_id}: expected lock_in atom.")
        elif "lock_in" in sections:
            raise IndexValidationError(f"{scheme_id}: unexpected lock_in atom.")


def load_index_rows(chunks_path: Path | None = None) -> list[dict[str, Any]]:
    path = Path(chunks_path) if chunks_path is not None else CHUNKS_PATH
    rows = load_chunks_jsonl(path)
    if not rows:
        raise IndexValidationError(
            f"No chunks at {path}. Run `python -m src.ingest.chunk` first."
        )
    return rows


def upsert_chunks(
    rows: Sequence[dict[str, Any]],
    *,
    chroma_path: Path | str | None = None,
    rebuild: bool = False,
    embedding_function: Any | None = None,
    expected_count: int | None = None,
    require_all_schemes: bool = True,
) -> IndexStats:
    validate_rows(
        rows,
        expected_count=expected_count,
        require_all_schemes=require_all_schemes,
    )
    opened = open_index(
        chroma_path=chroma_path,
        create=True,
        rebuild=rebuild,
        embedding_function=embedding_function,
    )
    ids = [str(row["chunk_id"]) for row in rows]
    documents = [str(row["text"]) for row in rows]
    metadatas = [chroma_metadata(row) for row in rows]
    opened.collection.upsert(ids=ids, documents=documents, metadatas=metadatas)
    count = opened.collection.count()
    if count != len(rows):
        raise IndexValidationError(
            f"Collection has {count} vectors but jsonl has {len(rows)}. "
            "Re-run with --rebuild to drop stale ids."
        )
    scheme_ids = sorted({row["scheme_id"] for row in rows})
    return IndexStats(
        collection=COLLECTION_NAME,
        chroma_path=opened.path,
        count=count,
        scheme_ids=scheme_ids,
        rebuilt=rebuild,
    )


def embed_index(
    *,
    chunks_path: Path | None = None,
    chroma_path: Path | str | None = None,
    rebuild: bool = False,
    embedding_function: Any | None = None,
    expected_count: int | None = None,
    require_all_schemes: bool = True,
) -> IndexStats:
    rows = load_index_rows(chunks_path)
    return upsert_chunks(
        rows,
        chroma_path=chroma_path,
        rebuild=rebuild,
        embedding_function=embedding_function,
        expected_count=expected_count,
        require_all_schemes=require_all_schemes,
    )


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Embed chunks.jsonl into Chroma collection groww_scheme_facts."
    )
    parser.add_argument(
        "--rebuild",
        action="store_true",
        help="Delete the collection first so dropped atoms cannot linger.",
    )
    parser.add_argument(
        "--chunks",
        type=Path,
        default=None,
        help="Path to chunks.jsonl (default: data/processed/chunks.jsonl).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    stats = embed_index(chunks_path=args.chunks, rebuild=args.rebuild)
    from src.config import PROJECT_ROOT

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
