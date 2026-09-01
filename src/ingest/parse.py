"""Parse and normalize Groww scheme HTML into plain text.

Usage:
    python -m src.ingest.parse
    python -m src.ingest.parse --scheme hdfc_large_cap_direct_growth
"""

from __future__ import annotations

import argparse
import json
import re
import sys
from dataclasses import asdict, dataclass
from datetime import datetime, timezone
from html import unescape
from pathlib import Path

from bs4 import BeautifulSoup, Comment, NavigableString, Tag

from src.config import PROJECT_ROOT
from src.ingest.allowlist import validate_allowlist
from src.ingest.fetch import HTML_FILENAME, MANIFEST_FILENAME, html_path
from src.registry import load_schemes

PROCESSED_DIR = PROJECT_ROOT / "data" / "processed"
TEXT_FILENAME = "scheme_page.txt"
PARSE_MANIFEST_FILENAME = "parse_manifest.json"

NOISE_TAGS = frozenset(
    {"script", "style", "noscript", "svg", "iframe", "header", "footer", "nav"}
)
NOISE_CLASS_SUBSTRINGS = (
    "footerTopSection",
    "compareSimilarFunds",
    "header_",
    "popupContainer",
    "popupBody",
    "rodal",
)
HEADING_PREFIX = {"h1": "# ", "h2": "## ", "h3": "### ", "h4": "#### "}
BLOCK_TAGS = frozenset({"h1", "h2", "h3", "h4", "p", "li", "dt", "dd", "td", "th"})
FACT_DIV_CLASS_HINTS = (
    "fundDetails",
    "investmentObjective",
    "exitLoadStampDutyTax",
    "minimumInvestment",
    "riskometer",
)
FACT_LINE_KEYWORDS = (
    "expense ratio",
    "exit load",
    "minimum sip",
    "min. for sip",
    "fund benchmark",
    "lock-in",
    "lock in",
    "3y lock",
    "riskometer",
    "very high risk",
    "moderately",
    "fund size",
    "nav:",
    "elss",
)
SUMMARY_PATTERN = re.compile(
    r"^The HDFC .+ is rated .+ risk\..+$",
    re.IGNORECASE,
)
EMBEDDED_FACT_PATTERNS = (
    (re.compile(r'"Lock-in period:\s*([^"\\]+)"', re.I), "Lock-in period: {value}"),
    (re.compile(r'"analysis_data":"(\d+)".*?"analysis_type":"LOCK_IN"', re.I), "Lock-in period: {value} years"),
    (re.compile(r'Lock-in period:\s*(\d+Y?)', re.I), "Lock-in period: {value}"),
)

# Site chrome lines that sometimes survive DOM pruning.
BOILERPLATE_LINE_PATTERNS = (
    re.compile(r"^Invest in (stocks|direct mutual funds)", re.I),
    re.compile(r"^Track (upcoming|markets|returns)", re.I),
    re.compile(r"^Filter (based on|funds)", re.I),
    re.compile(r"^Brokerage (calculator|and charges)", re.I),
    re.compile(r"^Download (Groww|from)", re.I),
    re.compile(r"^Customer Support$", re.I),
    re.compile(r"^About Groww$", re.I),
)


@dataclass
class ParseResult:
    scheme_id: str
    scheme_name: str
    citation_url: str
    parsed_at: str
    source_html_path: str
    source_fetched_at: str | None
    source_sha256: str | None
    output_path: str
    line_count: int
    char_count: int
    status: str
    error: str | None = None


def _now_iso() -> str:
    return datetime.now(timezone.utc).replace(microsecond=0).isoformat()


def _scheme_lookup() -> dict[str, dict]:
    return {scheme["scheme_id"]: scheme for scheme in load_schemes()}


def _load_source_manifest(scheme_id: str, raw_root: Path | None = None) -> dict | None:
    manifest_path = html_path(scheme_id, raw_root).parent / MANIFEST_FILENAME
    if not manifest_path.is_file():
        return None
    return json.loads(manifest_path.read_text(encoding="utf-8"))


def _element_classes(element: Tag) -> str:
    attrs = getattr(element, "attrs", None)
    if not attrs:
        return ""
    classes = attrs.get("class") or []
    if isinstance(classes, str):
        return classes
    return " ".join(classes)


def _should_remove_element(element: Tag) -> bool:
    if element.name in NOISE_TAGS:
        return True
    cls = _element_classes(element)
    return any(token in cls for token in NOISE_CLASS_SUBSTRINGS)


def _remove_noise(soup: BeautifulSoup) -> None:
    for comment in soup.find_all(string=lambda text: isinstance(text, Comment)):
        comment.extract()

    to_remove: list[Tag] = []
    for element in soup.find_all(True):
        if not isinstance(element, Tag):
            continue
        if _should_remove_element(element):
            to_remove.append(element)
    for element in to_remove:
        element.decompose()


def _content_root(soup: BeautifulSoup) -> Tag:
    for selector in (
        "div.pw14MainWrapper",
        "div.layout-main",
        "main",
        "body",
    ):
        node = soup.select_one(selector)
        if node is not None:
            return node
    return soup


def _normalize_line(line: str) -> str:
    line = unescape(line)
    line = line.replace("\u00a0", " ")
    line = re.sub(r"\s+", " ", line).strip()
    return line


def _is_boilerplate(line: str) -> bool:
    if len(line) < 3:
        return True
    return any(pattern.search(line) for pattern in BOILERPLATE_LINE_PATTERNS)


def _dedupe_lines(lines: list[str]) -> list[str]:
    deduped: list[str] = []
    previous: str | None = None
    for line in lines:
        if line == previous:
            continue
        deduped.append(line)
        previous = line
    return deduped


def _is_fact_line(line: str) -> bool:
    lowered = line.lower()
    return any(keyword in lowered for keyword in FACT_LINE_KEYWORDS) or bool(
        SUMMARY_PATTERN.match(line)
    )


def _extract_short_fact_spans(root: Tag) -> list[str]:
    lines: list[str] = []
    for element in root.find_all(["span", "a"]):
        if not isinstance(element, Tag):
            continue
        text = _normalize_line(element.get_text(" ", strip=True))
        if not text or len(text) > 120:
            continue
        lowered = text.lower()
        if any(
            keyword in lowered
            for keyword in ("lock-in", "lock in", "3y lock", "very high risk", "elss")
        ):
            lines.append(text)
    return lines


def _extract_scheme_fact_divs(root: Tag) -> list[str]:
    lines: list[str] = []
    for element in root.find_all("div"):
        if not isinstance(element, Tag):
            continue
        cls = _element_classes(element)
        if not any(hint in cls for hint in FACT_DIV_CLASS_HINTS):
            continue
        text = _normalize_line(element.get_text(" ", strip=True))
        if not text or len(text) > 500 or _is_boilerplate(text):
            continue
        if _is_fact_line(text) or "fundDetails" in cls:
            lines.append(text)
    return lines


def _extract_label_value_rows(root: Tag) -> list[str]:
    lines: list[str] = []
    for element in root.find_all("div"):
        if not isinstance(element, Tag):
            continue
        cls = _element_classes(element)
        if not any(token in cls for token in ("Row", "row", "benchmark", "exitLoad")):
            continue
        parts = [
            _normalize_line(child.get_text(" ", strip=True))
            for child in element.find_all(["span", "p"], recursive=False)
            if child.get_text(strip=True)
        ]
        if len(parts) >= 2:
            lines.append(f"{parts[0]}: {parts[1]}")
    return lines


def _drop_holdings_section(lines: list[str]) -> list[str]:
    cleaned: list[str] = []
    skipping = False
    for line in lines:
        if line.startswith("## Holdings"):
            skipping = True
            continue
        if skipping and line.startswith("#"):
            skipping = False
        if skipping:
            continue
        cleaned.append(line)
    return cleaned


def _extract_blocks(root: Tag) -> list[str]:
    lines: list[str] = []
    seen: set[str] = set()

    for line in _extract_scheme_fact_divs(root):
        if line not in seen:
            seen.add(line)
            lines.append(line)

    for line in _extract_short_fact_spans(root):
        if line not in seen:
            seen.add(line)
            lines.append(line)

    for element in root.find_all(BLOCK_TAGS):
        if not isinstance(element, Tag):
            continue
        text = _normalize_line(element.get_text(" ", strip=True))
        if not text or _is_boilerplate(text):
            continue
        prefix = HEADING_PREFIX.get(element.name, "")
        line = f"{prefix}{text}" if prefix else text
        if line in seen:
            continue
        seen.add(line)
        lines.append(line)

    for line in _extract_label_value_rows(root):
        if line not in seen:
            seen.add(line)
            lines.append(line)

    if lines:
        return _drop_holdings_section(lines)

    fallback = _normalize_line(root.get_text("\n", strip=True))
    return _drop_holdings_section(
        [line for line in (_normalize_line(part) for part in fallback.split("\n")) if line]
    )


def _extract_embedded_fact_lines(html: str) -> list[str]:
    lines: list[str] = []
    for pattern, template in EMBEDDED_FACT_PATTERNS:
        match = pattern.search(html)
        if not match:
            continue
        value = match.group(1).strip()
        line = _normalize_line(template.format(value=value))
        if line not in lines:
            lines.append(line)
    return lines


def _collapse_substring_lines(lines: list[str]) -> list[str]:
    return [
        line
        for line in lines
        if not any(line != other and line in other for other in lines)
    ]


def html_to_text(html: str) -> str:
    """Convert Groww scheme HTML to normalized plain text."""
    if not html or not html.strip():
        raise ValueError("HTML content is empty.")

    soup = BeautifulSoup(html, "html.parser")
    _remove_noise(soup)
    root = _content_root(soup)
    lines = _extract_embedded_fact_lines(html)
    lines.extend(_extract_blocks(root))
    lines = _dedupe_lines(lines)
    lines = _collapse_substring_lines(lines)

    if not lines:
        raise ValueError("No text extracted from HTML after cleanup.")

    return "\n".join(lines) + "\n"


def processed_dir(scheme_id: str, processed_root: Path | None = None) -> Path:
    return (processed_root or PROCESSED_DIR) / scheme_id


def text_output_path(scheme_id: str, processed_root: Path | None = None) -> Path:
    return processed_dir(scheme_id, processed_root) / TEXT_FILENAME


def parse_html_content(
    html: str,
    *,
    scheme_id: str,
    scheme_name: str,
    citation_url: str,
    source_html_path: str,
    source_manifest: dict | None = None,
    processed_root: Path | None = None,
) -> ParseResult:
    text = html_to_text(html)
    dest_dir = processed_dir(scheme_id, processed_root)
    dest_dir.mkdir(parents=True, exist_ok=True)
    dest = dest_dir / TEXT_FILENAME
    dest.write_text(text, encoding="utf-8")

    result = ParseResult(
        scheme_id=scheme_id,
        scheme_name=scheme_name,
        citation_url=citation_url,
        parsed_at=_now_iso(),
        source_html_path=source_html_path,
        source_fetched_at=(source_manifest or {}).get("fetched_at"),
        source_sha256=(source_manifest or {}).get("sha256"),
        output_path=str(dest.relative_to(processed_root or PROCESSED_DIR).as_posix()),
        line_count=len(text.splitlines()),
        char_count=len(text),
        status="ok",
    )
    (dest_dir / PARSE_MANIFEST_FILENAME).write_text(
        json.dumps(asdict(result), indent=2) + "\n",
        encoding="utf-8",
    )
    return result


def parse_scheme(
    source: dict,
    *,
    raw_root: Path | None = None,
    processed_root: Path | None = None,
) -> ParseResult:
    scheme_id = source["scheme_id"]
    scheme_meta = _scheme_lookup()[scheme_id]
    html_file = html_path(scheme_id, raw_root)

    if not html_file.is_file() or html_file.stat().st_size == 0:
        return ParseResult(
            scheme_id=scheme_id,
            scheme_name=scheme_meta["name"],
            citation_url=source["citation_url"],
            parsed_at=_now_iso(),
            source_html_path=str(html_file),
            source_fetched_at=None,
            source_sha256=None,
            output_path=str(text_output_path(scheme_id, processed_root)),
            line_count=0,
            char_count=0,
            status="failed",
            error=(
                f"Missing raw HTML at data/raw/{scheme_id}/{HTML_FILENAME}. "
                "Run python -m src.ingest.fetch first."
            ),
        )

    try:
        html = html_file.read_text(encoding="utf-8", errors="replace")
        return parse_html_content(
            html,
            scheme_id=scheme_id,
            scheme_name=scheme_meta["name"],
            citation_url=source["citation_url"],
            source_html_path=str(
                html_file.relative_to(raw_root or html_file.parents[2]).as_posix()
            ),
            source_manifest=_load_source_manifest(scheme_id, raw_root),
            processed_root=processed_root,
        )
    except Exception as exc:  # noqa: BLE001 - surface parse failures per scheme
        return ParseResult(
            scheme_id=scheme_id,
            scheme_name=scheme_meta["name"],
            citation_url=source["citation_url"],
            parsed_at=_now_iso(),
            source_html_path=str(html_file),
            source_fetched_at=(_load_source_manifest(scheme_id, raw_root) or {}).get(
                "fetched_at"
            ),
            source_sha256=(_load_source_manifest(scheme_id, raw_root) or {}).get(
                "sha256"
            ),
            output_path=str(text_output_path(scheme_id, processed_root)),
            line_count=0,
            char_count=0,
            status="failed",
            error=str(exc),
        )


def parse_all(
    *,
    scheme_id: str | None = None,
    raw_root: Path | None = None,
    processed_root: Path | None = None,
) -> list[ParseResult]:
    sources = validate_allowlist()
    if scheme_id:
        sources = [source for source in sources if source["scheme_id"] == scheme_id]
        if not sources:
            raise ValueError(f"Unknown scheme_id: {scheme_id}")
    return [
        parse_scheme(source, raw_root=raw_root, processed_root=processed_root)
        for source in sources
    ]


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Parse Groww scheme HTML into normalized plain text."
    )
    parser.add_argument("--scheme", help="Parse a single scheme_id only.")
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    results = parse_all(scheme_id=args.scheme)
    failed = 0
    for result in results:
        line = f"{result.scheme_id}: {result.status}"
        if result.status == "ok":
            line += f" ({result.line_count} lines, {result.char_count} chars)"
        if result.error:
            line += f" — {result.error}"
        print(line)
        if result.status == "failed":
            failed += 1
    return 1 if failed else 0


if __name__ == "__main__":
    sys.exit(main())
