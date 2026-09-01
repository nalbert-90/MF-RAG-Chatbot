from pathlib import Path

import pytest

from src.ingest.fetch import HTML_FILENAME
from src.ingest.parse import (
    PARSE_MANIFEST_FILENAME,
    TEXT_FILENAME,
    html_to_text,
    parse_all,
    parse_html_content,
    parse_scheme,
)
from src.ingest.allowlist import validate_allowlist

SAMPLE_HTML = """
<html>
  <body>
    <header class="header_nav">Site navigation should be removed</header>
    <div class="pw14MainWrapper">
      <h1>HDFC Large Cap Fund Direct Growth</h1>
      <p>Equity · Large Cap · Very High Risk</p>
      <h3>Minimum investments</h3>
      <p>Minimum SIP Investment is set to Rs 100.</p>
      <h3>Expense ratio</h3>
      <p>Expense ratio: 0.92% (Direct Plan)</p>
      <h3>Exit load, stamp duty and tax</h3>
      <h4>Exit load</h4>
      <p>Exit load of 1% if redeemed within 1 year.</p>
      <div class="investmentObjective_benchmarkRow">
        <span>Fund benchmark</span>
        <span>NIFTY 100 Total Return Index</span>
      </div>
      <p>The HDFC Large Cap Fund Direct Growth is rated Very High risk.</p>
    </div>
    <footer class="footerTopSection_wrapper">Download Groww app</footer>
  </body>
</html>
"""

NAV_NOISE = "Invest in stocks, ETFs, IPOs with fast orders"


@pytest.fixture
def raw_html(tmp_path: Path) -> Path:
    scheme_id = "hdfc_large_cap_direct_growth"
    dest = tmp_path / scheme_id
    dest.mkdir(parents=True)
    (dest / HTML_FILENAME).write_text(SAMPLE_HTML, encoding="utf-8")
    return tmp_path


def test_html_to_text_extracts_facts_and_headings() -> None:
    text = html_to_text(SAMPLE_HTML)
    assert "# HDFC Large Cap Fund Direct Growth" in text
    assert "Expense ratio: 0.92%" in text
    assert "Exit load of 1%" in text
    assert "Fund benchmark" in text
    assert "Minimum SIP Investment" in text
    assert "Very High risk" in text
    assert NAV_NOISE not in text
    assert "Download Groww app" not in text


def test_html_to_text_rejects_empty_input() -> None:
    with pytest.raises(ValueError, match="empty"):
        html_to_text("   ")


def test_parse_scheme_writes_processed_text(raw_html: Path, tmp_path: Path) -> None:
    source = next(
        s for s in validate_allowlist() if s["scheme_id"] == "hdfc_large_cap_direct_growth"
    )
    result = parse_scheme(source, raw_root=raw_html, processed_root=tmp_path)

    assert result.status == "ok"
    assert result.line_count > 5
    out = tmp_path / source["scheme_id"] / TEXT_FILENAME
    manifest = tmp_path / source["scheme_id"] / PARSE_MANIFEST_FILENAME
    assert out.is_file()
    assert manifest.is_file()
    assert "0.92%" in out.read_text(encoding="utf-8")


def test_parse_all_with_local_sample(raw_html: Path, tmp_path: Path) -> None:
    source = next(
        s for s in validate_allowlist() if s["scheme_id"] == "hdfc_large_cap_direct_growth"
    )
    result = parse_scheme(source, raw_root=raw_html, processed_root=tmp_path)
    assert result.status == "ok"

    missing = parse_scheme(
        next(s for s in validate_allowlist() if s["scheme_id"] == "hdfc_mid_cap_direct_growth"),
        raw_root=raw_html,
        processed_root=tmp_path,
    )
    assert missing.status == "failed"
    assert "Missing raw HTML" in (missing.error or "")


def test_parse_live_corpus_if_present() -> None:
    raw_root = Path("data/raw")
    processed_root = Path("data/processed")
    if not (raw_root / "hdfc_large_cap_direct_growth" / HTML_FILENAME).is_file():
        pytest.skip("Live Groww HTML not fetched")

    results = parse_all(raw_root=raw_root, processed_root=processed_root)
    assert len(results) == 5
    assert all(result.status == "ok" for result in results)

    large_cap = (
        processed_root / "hdfc_large_cap_direct_growth" / TEXT_FILENAME
    ).read_text(encoding="utf-8")
    assert "Expense ratio" in large_cap or "0." in large_cap
    assert "Exit load" in large_cap
    assert "benchmark" in large_cap.lower()
    assert NAV_NOISE not in large_cap

    elss = (
        processed_root / "hdfc_elss_tax_saver_direct_growth" / TEXT_FILENAME
    ).read_text(encoding="utf-8")
    elss_lower = elss.lower()
    assert "lock" in elss_lower or "elss" in elss_lower
