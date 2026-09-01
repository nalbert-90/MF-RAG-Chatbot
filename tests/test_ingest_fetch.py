import json
from pathlib import Path

import httpx
import pytest

from src.ingest.allowlist import validate_allowlist
from src.ingest.fetch import HTML_FILENAME, MANIFEST_FILENAME, fetch_all, fetch_one


def _source(scheme_id: str = "hdfc_large_cap_direct_growth") -> dict:
    return next(s for s in validate_allowlist() if s["scheme_id"] == scheme_id)


def _client(status: int = 200, body: bytes = b"<html>groww scheme</html>") -> httpx.Client:
    def handler(request: httpx.Request) -> httpx.Response:
        return httpx.Response(status, content=body)

    return httpx.Client(transport=httpx.MockTransport(handler))


def test_fetch_writes_html_checksum_and_timestamp(tmp_path: Path) -> None:
    source = _source()
    result = fetch_one(source, client=_client(), raw_root=tmp_path)

    html = tmp_path / source["scheme_id"] / HTML_FILENAME
    manifest_path = tmp_path / source["scheme_id"] / MANIFEST_FILENAME
    assert result.status == "ok"
    assert html.is_file()
    assert html.read_bytes() == b"<html>groww scheme</html>"
    assert result.sha256
    assert result.bytes == len(b"<html>groww scheme</html>")
    assert result.fetched_at
    assert result.http_status == 200

    manifest = json.loads(manifest_path.read_text(encoding="utf-8"))
    assert manifest["citation_url"] == source["citation_url"]
    assert manifest["sha256"] == result.sha256
    assert manifest["fetched_at"] == result.fetched_at


def test_fetch_rejects_non_allowlisted_url(tmp_path: Path) -> None:
    source = _source()
    bad = {**source, "citation_url": "https://www.hdfcfund.com/not-allowed"}
    with pytest.raises(ValueError, match="non-allowlisted"):
        fetch_one(bad, client=_client(), raw_root=tmp_path)


def test_fetch_uses_manual_fallback_when_blocked(tmp_path: Path) -> None:
    source = _source()
    dest = tmp_path / source["scheme_id"]
    dest.mkdir(parents=True)
    (dest / HTML_FILENAME).write_bytes(b"<html>saved locally</html>")

    result = fetch_one(source, client=_client(status=403), raw_root=tmp_path)
    assert result.status == "manual_fallback"
    assert result.sha256
    assert (tmp_path / source["scheme_id"] / HTML_FILENAME).read_bytes() == (
        b"<html>saved locally</html>"
    )


def test_fetch_offline_requires_local_html(tmp_path: Path) -> None:
    source = _source()
    failed = fetch_one(source, raw_root=tmp_path, offline=True)
    assert failed.status == "failed"

    dest = tmp_path / source["scheme_id"]
    dest.mkdir(parents=True)
    (dest / HTML_FILENAME).write_bytes(b"<html>manual</html>")
    ok = fetch_one(source, raw_root=tmp_path, offline=True)
    assert ok.status == "manual_fallback"
    assert ok.http_status is None


def test_fetch_all_covers_five_schemes(tmp_path: Path) -> None:
    results = fetch_all(client=_client(), raw_root=tmp_path)
    assert len(results) == 5
    assert {r.status for r in results} == {"ok"}
    assert all((tmp_path / r.scheme_id / HTML_FILENAME).is_file() for r in results)
