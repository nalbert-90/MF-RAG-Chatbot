"""Fetch allowlisted Groww scheme pages into data/raw/{scheme_id}/.

Usage:
    python -m src.ingest.fetch
    python -m src.ingest.fetch --scheme hdfc_large_cap_direct_growth
    python -m src.ingest.fetch --offline

If Groww blocks the request, place a saved copy of the scheme page at
data/raw/{scheme_id}/scheme_page.html and re-run (see README).
"""

from __future__ import annotations

import argparse
import hashlib
import json
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from pathlib import Path

import httpx

from src.config import PROJECT_ROOT
from src.ingest.allowlist import is_allowlisted_citation_url, validate_allowlist

RAW_DIR = PROJECT_ROOT / "data" / "raw"
HTML_FILENAME = "scheme_page.html"
MANIFEST_FILENAME = "manifest.json"

USER_AGENT = (
    "Mozilla/5.0 (Windows NT 10.0; Win64; x64) "
    "AppleWebKit/537.36 (KHTML, like Gecko) "
    "Chrome/131.0.0.0 Safari/537.36"
)
REQUEST_HEADERS = {
    "User-Agent": USER_AGENT,
    "Accept": "text/html,application/xhtml+xml,application/xml;q=0.9,*/*;q=0.8",
    "Accept-Language": "en-IN,en;q=0.9",
}


@dataclass
class FetchResult:
    scheme_id: str
    citation_url: str
    source_org: str
    doc_type: str
    fetched_at: str
    sha256: str | None
    bytes: int
    path: str
    http_status: int | None
    status: str
    error: str | None = None


def scheme_raw_dir(scheme_id: str, raw_root: Path | None = None) -> Path:
    return (raw_root or RAW_DIR) / scheme_id


def html_path(scheme_id: str, raw_root: Path | None = None) -> Path:
    return scheme_raw_dir(scheme_id, raw_root) / HTML_FILENAME


def _sha256(content: bytes) -> str:
    return hashlib.sha256(content).hexdigest()


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _write_html_and_manifest(
    source: dict,
    content: bytes,
    *,
    raw_root: Path | None,
    fetched_at: str,
    http_status: int | None,
    status: str,
    error: str | None = None,
) -> FetchResult:
    scheme_id = source["scheme_id"]
    dest_dir = scheme_raw_dir(scheme_id, raw_root)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / HTML_FILENAME
    dest.write_bytes(content)

    result = FetchResult(
        scheme_id=scheme_id,
        citation_url=source["citation_url"],
        source_org=source["source_org"],
        doc_type=source["doc_type"],
        fetched_at=fetched_at,
        sha256=_sha256(content) if content else None,
        bytes=len(content),
        path=str(dest.relative_to(raw_root or RAW_DIR).as_posix()),
        http_status=http_status,
        status=status,
        error=error,
    )
    (dest_dir / MANIFEST_FILENAME).write_text(
        json.dumps(asdict(result), indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def _load_manual_html(scheme_id: str, raw_root: Path | None) -> bytes | None:
    path = html_path(scheme_id, raw_root)
    if path.is_file() and path.stat().st_size > 0:
        return path.read_bytes()
    return None


def fetch_one(
    source: dict,
    *,
    client: httpx.Client | None = None,
    raw_root: Path | None = None,
    offline: bool = False,
) -> FetchResult:
    url = source["citation_url"]
    scheme_id = source["scheme_id"]
    fetched_at = _now_iso()

    if not is_allowlisted_citation_url(url):
        raise ValueError(
            f"Refusing to fetch non-allowlisted URL for {scheme_id}: {url}"
        )

    if offline:
        local = _load_manual_html(scheme_id, raw_root)
        if not local:
            return FetchResult(
                scheme_id=scheme_id,
                citation_url=url,
                source_org=source["source_org"],
                doc_type=source["doc_type"],
                fetched_at=fetched_at,
                sha256=None,
                bytes=0,
                path=f"{scheme_id}/{HTML_FILENAME}",
                http_status=None,
                status="failed",
                error=(
                    "offline mode: missing data/raw/"
                    f"{scheme_id}/{HTML_FILENAME}. Save the Groww page HTML there."
                ),
            )
        return _write_html_and_manifest(
            source,
            local,
            raw_root=raw_root,
            fetched_at=fetched_at,
            http_status=None,
            status="manual_fallback",
        )

    close_client = False
    if client is None:
        client = httpx.Client(
            headers=REQUEST_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        )
        close_client = True

    try:
        response = client.get(url)
        if response.status_code == 200 and response.content:
            return _write_html_and_manifest(
                source,
                response.content,
                raw_root=raw_root,
                fetched_at=fetched_at,
                http_status=response.status_code,
                status="ok",
            )

        local = _load_manual_html(scheme_id, raw_root)
        if local:
            return _write_html_and_manifest(
                source,
                local,
                raw_root=raw_root,
                fetched_at=fetched_at,
                http_status=response.status_code,
                status="manual_fallback",
                error=f"HTTP {response.status_code}; used local HTML fallback.",
            )

        return FetchResult(
            scheme_id=scheme_id,
            citation_url=url,
            source_org=source["source_org"],
            doc_type=source["doc_type"],
            fetched_at=fetched_at,
            sha256=None,
            bytes=0,
            path=f"{scheme_id}/{HTML_FILENAME}",
            http_status=response.status_code,
            status="failed",
            error=(
                f"HTTP {response.status_code}. Save the page as "
                f"data/raw/{scheme_id}/{HTML_FILENAME} and re-run."
            ),
        )
    except httpx.HTTPError as exc:
        local = _load_manual_html(scheme_id, raw_root)
        if local:
            return _write_html_and_manifest(
                source,
                local,
                raw_root=raw_root,
                fetched_at=fetched_at,
                http_status=None,
                status="manual_fallback",
                error=f"{exc}; used local HTML fallback.",
            )
        return FetchResult(
            scheme_id=scheme_id,
            citation_url=url,
            source_org=source["source_org"],
            doc_type=source["doc_type"],
            fetched_at=fetched_at,
            sha256=None,
            bytes=0,
            path=f"{scheme_id}/{HTML_FILENAME}",
            http_status=None,
            status="failed",
            error=(
                f"{exc}. Save the page as data/raw/{scheme_id}/{HTML_FILENAME} "
                "and re-run with --offline."
            ),
        )
    finally:
        if close_client:
            client.close()


def fetch_all(
    *,
    scheme_id: str | None = None,
    client: httpx.Client | None = None,
    raw_root: Path | None = None,
    offline: bool = False,
) -> list[FetchResult]:
    sources = validate_allowlist()
    if scheme_id:
        sources = [s for s in sources if s["scheme_id"] == scheme_id]
        if not sources:
            raise ValueError(f"Unknown scheme_id: {scheme_id}")

    results: list[FetchResult] = []
    own_client = client is None and not offline
    http_client = client
    if own_client:
        http_client = httpx.Client(
            headers=REQUEST_HEADERS,
            follow_redirects=True,
            timeout=30.0,
        )
    try:
        for source in sources:
            results.append(
                fetch_one(
                    source,
                    client=http_client,
                    raw_root=raw_root,
                    offline=offline,
                )
            )
    finally:
        if own_client and http_client is not None:
            http_client.close()
    return results


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Fetch allowlisted Groww scheme HTML into data/raw/{scheme_id}/."
    )
    parser.add_argument("--scheme", help="Fetch a single scheme_id only.")
    parser.add_argument(
        "--offline",
        action="store_true",
        help="Do not call Groww; checksum existing local HTML files.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    results = fetch_all(scheme_id=args.scheme, offline=args.offline)
    failed = 0
    for result in results:
        line = f"{result.scheme_id}: {result.status}"
        if result.sha256:
            line += f" sha256={result.sha256[:12]}... ({result.bytes} bytes)"
        if result.error:
            line += f" — {result.error}"
        print(line)
        if result.status == "failed":
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
