# Raw Groww scheme pages

Fetched HTML lives in `data/raw/{scheme_id}/scheme_page.html` with a
`manifest.json` (SHA-256 checksum + fetch timestamp).

These files are gitignored. Re-fetch after clone:

```bash
python -m src.ingest.fetch
```

## Manual download fallback

If Groww blocks the bot (HTTP 403/401 or an empty challenge page):

1. Open the scheme URL from `data/registry/sources_allowlist.yaml` in a browser.
2. Save the page as HTML (`Ctrl+S` → Webpage, HTML only).
3. Copy it to `data/raw/{scheme_id}/scheme_page.html`.
4. Re-run:

```bash
python -m src.ingest.fetch --offline
```

`--offline` checksums local files only and does not call Groww.
If a live fetch fails but a local HTML file already exists, fetch uses that
copy automatically (`status: manual_fallback`).
