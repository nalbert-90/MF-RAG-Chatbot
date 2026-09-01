# Re-ingest playbook (manual refresh)

How to refresh the five allowlisted **Groww** scheme pages when NAV, expense ratios, exit loads, or other on-page facts change.

> **Footer semantics:** `Last updated from sources: <date>` reflects the **NAV / as-of date** parsed from the Groww page (`published_or_as_of`), not live market ticks. Re-ingest when you need answers aligned with the latest Groww snapshot.

For an **automated daily** run at **10:00 AM IST**, see the GitHub Actions workflow [`.github/workflows/daily-ingest.yml`](../.github/workflows/daily-ingest.yml) (Phase 6). Manual on-demand trigger: **Actions → Daily ingest → Run workflow**.

---

## When to re-ingest

- Groww updates TER, exit load, SIP minimum, lock-in, benchmark, or NAV date on a scheme page
- Parse/chunk logic changed in `src/ingest/`
- Retrieval probes (`retrieve_check`) fail after a Groww HTML layout change
- You need demo answers to match freshly downloaded pages

---

## Full pipeline (local)

Run from the project root with the virtual environment active.

### 1. Fetch raw HTML

```bash
python -m src.ingest.fetch
```

Downloads each allowlisted page to `data/raw/{scheme_id}/scheme_page.html` with checksum + timestamp in `manifest.json`.

**If Groww blocks the bot:** save the page from your browser as `data/raw/{scheme_id}/scheme_page.html`, then:

```bash
python -m src.ingest.fetch --offline
```

See [`data/raw/README.md`](../data/raw/README.md).

### 2. Parse & normalize

```bash
python -m src.ingest.parse
```

Writes `data/processed/{scheme_id}/scheme_page.txt` and `parse_manifest.json`.

### 3. Chunk (fact-atoms)

```bash
python -m src.ingest.run --chunk
```

Writes `data/processed/chunks.jsonl` (one row per fact atom, not token windows).

### 4. Embed + upsert Chroma

```bash
python -m src.ingest.run --rebuild
```

Rebuilds collection `groww_scheme_facts` under `CHROMA_PATH` (default `data/processed/chroma`). Stable `chunk_id` values allow upsert; `--rebuild` drops stale atoms.

**One-liner after fetch + parse:**

```bash
python -m src.ingest.run --chunk --rebuild
```

### 5. Gate — retrieval probes

```bash
python -m src.ingest.retrieve_check
pytest tests/test_retrieval_facts.py -m "not integration"
```

Pass = expected `section` at **rank 1** on the filtered probe table (see `implementation_plan.md` Phase 1).

### 6. Smoke the API path

```bash
python -m src.api.smoke_e2e
python -m src.api.demo
```

Restart the API (`.\scripts\run_api.ps1`) so the retriever picks up the new index if it was already running.

---

## Single-scheme refresh

```bash
python -m src.ingest.fetch --scheme hdfc_large_cap_direct_growth
python -m src.ingest.parse --scheme hdfc_large_cap_direct_growth
python -m src.ingest.run --chunk --scheme hdfc_large_cap_direct_growth
python -m src.ingest.run --rebuild
```

---

## Verify metadata after re-ingest

- [ ] Chroma `count()` matches expected atom count (46 in the current snapshot)
- [ ] Every chunk `citation_url` is one of the five Groww URLs in `data/registry/schemes.yaml`
- [ ] `published_or_as_of` reflects the NAV date on the page (or parse fallback)
- [ ] No `section=riskometer` rows unless the parser now extracts riskometer text
- [ ] Collision probes still pass (Sensex vs Silver TER `0.22%`; Mid vs Large exit load `1%` / 1 year)

---

## Troubleshooting

| Symptom | Likely cause | Action |
|---------|--------------|--------|
| Fetch HTTP 403 / empty HTML | Groww bot block | Browser save + `--offline` |
| Parse yields empty `scheme_page.txt` | HTML layout change | Update `src/ingest/parse.py` selectors |
| Wrong TER after re-ingest | Stale raw HTML or chunk regex drift | Re-fetch; inspect `scheme_page.txt`; fix `chunk.py` |
| `retrieve_check` rank-1 miss | Embedding collision or filter bug | Run `--diagnostics`; confirm `scheme_id` filter |
| API still shows old footer date | API started before re-ingest | Restart uvicorn |

---

## What re-ingest does **not** do

- Does not call Groq (embeddings are local MiniLM)
- Does not change guardrails, UI, or API routes
- Does not add schemes beyond the five HDFC Groww pages in the allowlist
