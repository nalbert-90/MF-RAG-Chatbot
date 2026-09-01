"""Fact-atom chunking for processed Groww scheme pages (Phase 1 task 4).

Usage:
    python -m src.ingest.chunk
    python -m src.ingest.chunk --scheme hdfc_large_cap_direct_growth

Reads data/processed/{scheme_id}/scheme_page.txt (+ parse_manifest.json)
and writes data/processed/chunks.jsonl. Does not use token windows — each
parsed page is a short packed extract (see docs/implementation_plan.md).
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass, field
from datetime import date, datetime, timezone
from pathlib import Path

from src.config import PROJECT_ROOT
from src.ingest.allowlist import (
    ALLOWED_DOC_TYPE,
    ALLOWED_SOURCE_ORG,
    is_allowlisted_citation_url,
    validate_allowlist,
)
from src.ingest.parse import (
    PARSE_MANIFEST_FILENAME,
    PROCESSED_DIR,
    TEXT_FILENAME,
    processed_dir,
    text_output_path,
)
from src.registry import load_schemes

CHUNKS_FILENAME = "chunks.jsonl"
CHUNKS_PATH = PROCESSED_DIR / CHUNKS_FILENAME

MONTHS = {
    "jan": 1,
    "feb": 2,
    "mar": 3,
    "apr": 4,
    "may": 5,
    "jun": 6,
    "jul": 7,
    "aug": 8,
    "sep": 9,
    "oct": 10,
    "nov": 11,
    "dec": 12,
}

NAV_RE = re.compile(
    r"^NAV:\s*(?P<day>\d{1,2})\s+(?P<mon>[A-Za-z]{3})\s+'(?P<yy>\d{2})\s+"
    r"₹(?P<nav>[\d,.]+)"
)
SIP_RE = re.compile(r"Min\.\s+for\s+SIP\s+₹(?P<sip>[\d,]+)", re.I)
AUM_RE = re.compile(r"Fund size \(AUM\)\s+₹(?P<aum>[\d,.]+)\s+Cr", re.I)
TER_RE = re.compile(r"Expense ratio\s+(?P<ter>[\d.]+%)", re.I)
RATING_RE = re.compile(r"Rating\s+(?P<rating>\d+|--)")
LOCK_IN_RE = re.compile(r"^Lock-in period:\s*(?P<lock>\S+)", re.I)
EXIT_LOAD_RE = re.compile(r"Exit load\s+(?P<load>Nil|of\s+.+?)(?=\s+Stamp duty)", re.I)
PROCESS_RE = re.compile(r"(Stamp duty on investment:\s*.+)$", re.I)
BENCHMARK_RE = re.compile(
    r"^Fund benchmark:?\s*(?P<bench>.+?)(?:\s+Scheme Information Document.*)?$",
    re.I,
)
SID_TAIL_RE = re.compile(r"\s+Scheme Information Document.*$", re.I)
MANAGER_RE = re.compile(
    r"^###\s+[A-Z]{2,}\s+(?P<body>.+?)\s+View details\s*$",
)
CHECK_PAST_DATA_RE = re.compile(r"\s*Check past data\s*$", re.I)
DUP_JULY_2020_RE = re.compile(r"\)\s*from July 1st 2020\s+", re.I)
TAX_LABEL_RE = re.compile(r"\s+Tax implication\s+", re.I)

SKIP_HEADING_PREFIXES = (
    "return calculator",
    "returns and rankings",
    "exit load",
    "stamp duty",
    "tax implication",
    "about",
    "fund house",
    "investment objective",
)

JSONL_FIELDS = (
    "chunk_id",
    "scheme_id",
    "scheme_name",
    "source_org",
    "doc_type",
    "title",
    "citation_url",
    "published_or_as_of",
    "ingested_at",
    "section",
    "text",
)


@dataclass
class Chunk:
    chunk_id: str
    scheme_id: str
    scheme_name: str
    source_org: str
    doc_type: str
    title: str
    citation_url: str
    published_or_as_of: str
    ingested_at: str
    section: str
    text: str


@dataclass
class ChunkResult:
    scheme_id: str
    status: str
    chunk_count: int
    chunks: list[Chunk] = field(default_factory=list)
    error: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _scheme_lookup() -> dict[str, dict]:
    return {scheme["scheme_id"]: scheme for scheme in load_schemes()}


def chunks_jsonl_path(processed_root: Path | None = None) -> Path:
    return (processed_root or PROCESSED_DIR) / CHUNKS_FILENAME


def _normalize_name(value: str) -> str:
    return re.sub(r"[\s\-]+", " ", value).strip().lower()


def _foreign_scheme_names(scheme_id: str) -> list[str]:
    return [
        scheme["name"]
        for scheme in load_schemes()
        if scheme["scheme_id"] != scheme_id
    ]


def _is_foreign_scheme_line(line: str, foreign_names: list[str]) -> bool:
    norm = _normalize_name(line)
    return any(_normalize_name(name) == norm for name in foreign_names)


def _split_preamble_and_headed(text: str) -> tuple[list[str], list[str]]:
    preamble: list[str] = []
    headed: list[str] = []
    in_headed = False
    for raw in text.splitlines():
        line = raw.strip()
        if not line:
            continue
        if not in_headed and line.startswith("###"):
            in_headed = True
        if in_headed:
            headed.append(line)
        else:
            preamble.append(line)
    return preamble, headed


def _parse_nav_date(hero_line: str) -> date | None:
    match = NAV_RE.search(hero_line)
    if not match:
        return None
    month = MONTHS.get(match.group("mon").lower())
    if month is None:
        return None
    year = 2000 + int(match.group("yy"))
    try:
        return date(year, month, int(match.group("day")))
    except ValueError:
        return None


def _as_of_from_manifest(manifest: dict | None) -> str | None:
    if not manifest:
        return None
    parsed_at = manifest.get("parsed_at") or ""
    if len(parsed_at) >= 10 and parsed_at[4] == "-" and parsed_at[7] == "-":
        return parsed_at[:10]
    return None


def _chunk_text(scheme_name: str, fact: str) -> str:
    body = " ".join(fact.split()).strip()
    if not body.endswith("."):
        body += "."
    return f"{scheme_name}. {body}"


def _clean_process_text(raw: str) -> str:
    text = CHECK_PAST_DATA_RE.sub("", raw).strip()
    text = DUP_JULY_2020_RE.sub(") ", text)
    text = TAX_LABEL_RE.sub(". Tax implication: ", text)
    text = " ".join(text.split())
    return text


PERFORMANCE_NOISE = (
    "would've become",
    "historic returns",
    "return calculator",
    "category average",
    "over the past",
    "total investment",
)


def _is_skipped_heading(heading: str) -> bool:
    lowered = heading.lower().lstrip("# ").strip()
    return any(lowered == prefix or lowered.startswith(prefix) for prefix in SKIP_HEADING_PREFIXES)


def _is_performance_noise(text: str) -> bool:
    lowered = text.lower()
    return any(token in lowered for token in PERFORMANCE_NOISE)


def _contains_foreign_scheme(text: str, foreign_names: list[str]) -> bool:
    norm = _normalize_name(text)
    return any(_normalize_name(name) in norm for name in foreign_names)


def _extract_managers(headed_lines: list[str]) -> list[str]:
    managers: list[str] = []
    for line in headed_lines:
        if _is_skipped_heading(line):
            continue
        match = MANAGER_RE.match(line)
        if match:
            managers.append(match.group("body").strip())
    return managers


def chunk_scheme_text(
    text: str,
    *,
    scheme_id: str,
    scheme_name: str,
    citation_url: str,
    parse_manifest: dict | None = None,
    ingested_at: str | None = None,
    foreign_names: list[str] | None = None,
) -> list[Chunk]:
    """Split a processed scheme page into Architecture §5.3 fact-atom chunks."""
    if not is_allowlisted_citation_url(citation_url):
        raise ValueError(
            f"{scheme_id}: citation_url is not an allowlisted Groww scheme URL."
        )

    ingested = ingested_at or _now_iso()
    names = foreign_names if foreign_names is not None else _foreign_scheme_names(scheme_id)
    preamble, headed = _split_preamble_and_headed(text)
    preamble = [line for line in preamble if not _is_foreign_scheme_line(line, names)]

    published: str | None = None
    atoms: list[tuple[str, str, str, str]] = []
    # (chunk_id_suffix, section, title, fact)

    for line in preamble:
        lock = LOCK_IN_RE.match(line)
        if lock:
            atoms.append(
                ("lock_in", "lock_in", "Lock-in period", f"Lock-in period: {lock.group('lock')}")
            )
            continue

        if NAV_RE.match(line):
            nav_match = NAV_RE.match(line)
            assert nav_match is not None
            nav_date = _parse_nav_date(line)
            if nav_date:
                published = nav_date.isoformat()
            atoms.append(
                (
                    "other::nav",
                    "other",
                    "NAV",
                    f"NAV: {nav_match.group('day')} {nav_match.group('mon')} "
                    f"'{nav_match.group('yy')} ₹{nav_match.group('nav')}",
                )
            )
            sip = SIP_RE.search(line)
            if sip:
                atoms.append(
                    ("sip", "sip", "Minimum SIP", f"Min. for SIP ₹{sip.group('sip')}")
                )
            aum = AUM_RE.search(line)
            if aum:
                atoms.append(
                    (
                        "other::aum",
                        "other",
                        "Fund size (AUM)",
                        f"Fund size (AUM) ₹{aum.group('aum')} Cr",
                    )
                )
            ter = TER_RE.search(line)
            if ter:
                atoms.append(
                    (
                        "expense_ratio",
                        "expense_ratio",
                        "Expense ratio",
                        f"Expense ratio {ter.group('ter')}",
                    )
                )
            rating = RATING_RE.search(line)
            if rating:
                atoms.append(
                    ("other::rating", "other", "Rating", f"Rating {rating.group('rating')}")
                )
            continue

        exit_match = EXIT_LOAD_RE.search(line)
        if exit_match:
            load = exit_match.group("load").strip().rstrip(".")
            atoms.append(("exit_load", "exit_load", "Exit load", f"Exit load {load}"))

        process_match = PROCESS_RE.search(line)
        if process_match:
            process = _clean_process_text(process_match.group(1))
            if process:
                atoms.append(
                    ("process", "process", "Stamp duty and tax", process)
                )
            continue

        bench = BENCHMARK_RE.match(SID_TAIL_RE.sub("", line).strip())
        if bench:
            name = bench.group("bench").strip().rstrip(".")
            atoms.append(
                (
                    "benchmark",
                    "benchmark",
                    "Fund benchmark",
                    f"Fund benchmark: {name}",
                )
            )

    managers = _extract_managers(headed)
    if managers:
        joined = "; ".join(managers)
        atoms.append(
            (
                "other::managers",
                "other",
                "Fund management",
                f"Fund managers: {joined}",
            )
        )

    if published is None:
        published = _as_of_from_manifest(parse_manifest) or ingested[:10]

    chunks: list[Chunk] = []
    for suffix, section, title, fact in atoms:
        text_out = _chunk_text(scheme_name, fact)
        if _is_performance_noise(text_out) or _contains_foreign_scheme(text_out, names):
            continue
        chunks.append(
            Chunk(
                chunk_id=f"{scheme_id}::{suffix}",
                scheme_id=scheme_id,
                scheme_name=scheme_name,
                source_org=ALLOWED_SOURCE_ORG,
                doc_type=ALLOWED_DOC_TYPE,
                title=title,
                citation_url=citation_url,
                published_or_as_of=published,
                ingested_at=ingested,
                section=section,
                text=text_out,
            )
        )
    return chunks


def _load_parse_manifest(scheme_id: str, processed_root: Path | None = None) -> dict | None:
    path = processed_dir(scheme_id, processed_root) / PARSE_MANIFEST_FILENAME
    if not path.is_file():
        return None
    return json.loads(path.read_text(encoding="utf-8"))


def chunk_scheme(
    source: dict,
    *,
    processed_root: Path | None = None,
    ingested_at: str | None = None,
) -> ChunkResult:
    scheme_id = source["scheme_id"]
    scheme_meta = _scheme_lookup()[scheme_id]
    text_path = text_output_path(scheme_id, processed_root)

    if not text_path.is_file() or text_path.stat().st_size == 0:
        return ChunkResult(
            scheme_id=scheme_id,
            status="failed",
            chunk_count=0,
            error=(
                f"Missing processed text at data/processed/{scheme_id}/{TEXT_FILENAME}. "
                "Run python -m src.ingest.parse first."
            ),
        )

    try:
        text = text_path.read_text(encoding="utf-8")
        manifest = _load_parse_manifest(scheme_id, processed_root)
        citation_url = (manifest or {}).get("citation_url") or source["citation_url"]
        chunks = chunk_scheme_text(
            text,
            scheme_id=scheme_id,
            scheme_name=scheme_meta["name"],
            citation_url=citation_url,
            parse_manifest=manifest,
            ingested_at=ingested_at,
        )
    except Exception as exc:  # noqa: BLE001 - surface per-scheme failures
        return ChunkResult(
            scheme_id=scheme_id,
            status="failed",
            chunk_count=0,
            error=str(exc),
        )

    if not chunks:
        return ChunkResult(
            scheme_id=scheme_id,
            status="failed",
            chunk_count=0,
            error="No fact-atom chunks extracted from processed text.",
        )

    return ChunkResult(
        scheme_id=scheme_id,
        status="ok",
        chunk_count=len(chunks),
        chunks=chunks,
    )


def chunk_all(
    *,
    scheme_id: str | None = None,
    processed_root: Path | None = None,
    ingested_at: str | None = None,
) -> list[ChunkResult]:
    sources = validate_allowlist()
    if scheme_id:
        sources = [source for source in sources if source["scheme_id"] == scheme_id]
        if not sources:
            raise ValueError(f"Unknown scheme_id: {scheme_id}")
    return [
        chunk_scheme(source, processed_root=processed_root, ingested_at=ingested_at)
        for source in sources
    ]


def _row(chunk: Chunk) -> dict:
    data = asdict(chunk)
    return {key: data[key] for key in JSONL_FIELDS}


def load_chunks_jsonl(path: Path) -> list[dict]:
    if not path.is_file():
        return []
    rows: list[dict] = []
    for line in path.read_text(encoding="utf-8").splitlines():
        line = line.strip()
        if line:
            rows.append(json.loads(line))
    return rows


def write_chunks_jsonl(
    chunks: list[Chunk],
    path: Path,
    *,
    replace_scheme_ids: set[str] | None = None,
) -> Path:
    path.parent.mkdir(parents=True, exist_ok=True)
    rows = [_row(chunk) for chunk in chunks]
    if replace_scheme_ids is not None:
        kept = [
            row
            for row in load_chunks_jsonl(path)
            if row.get("scheme_id") not in replace_scheme_ids
        ]
        rows = kept + rows
    payload = "".join(json.dumps(row, ensure_ascii=False) + "\n" for row in rows)
    path.write_text(payload, encoding="utf-8")
    return path


def persist_results(
    results: list[ChunkResult],
    *,
    processed_root: Path | None = None,
    merge: bool = False,
) -> Path:
    path = chunks_jsonl_path(processed_root)
    chunks = [chunk for result in results if result.status == "ok" for chunk in result.chunks]
    replace = {result.scheme_id for result in results} if merge else None
    return write_chunks_jsonl(chunks, path, replace_scheme_ids=replace)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Chunk processed Groww scheme pages into fact-atom JSONL."
    )
    parser.add_argument("--scheme", help="Chunk a single scheme_id only.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    results = chunk_all(scheme_id=args.scheme)
    failed = 0
    for result in results:
        line = f"{result.scheme_id}: {result.status}"
        if result.status == "ok":
            line += f" ({result.chunk_count} chunks)"
        if result.error:
            line += f" — {result.error}"
        print(line)
        if result.status == "failed":
            failed += 1

    if any(result.status == "ok" for result in results):
        path = persist_results(results, merge=bool(args.scheme))
        total = sum(result.chunk_count for result in results if result.status == "ok")
        try:
            rel = path.relative_to(PROJECT_ROOT).as_posix()
        except ValueError:
            rel = path
        print(f"Wrote {total} chunks -> {rel}")

    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
