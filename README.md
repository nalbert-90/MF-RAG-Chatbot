# Mutual Fund FAQ Assistant

Facts-only RAG chatbot for HDFC mutual fund schemes. Answers objective questions using curated **Groww** scheme pages — no investment advice.

> **Facts-only. No investment advice.**

## Overview

This project builds a lightweight Retrieval-Augmented Generation (RAG) assistant that:

- Answers factual queries (expense ratio, exit load, SIP minimum, lock-in, riskometer, benchmark, etc.)
- Cites a single Groww scheme page URL per answer
- Refuses advisory, comparative, and PII-bearing questions

See [`docs/problem_statement.md`](docs/problem_statement.md), [`docs/Architecture.md`](docs/Architecture.md), and [`docs/implementation_plan.md`](docs/implementation_plan.md).

## Prerequisites

- Python 3.11+
- Node.js 20+ (for the React UI)
- A [Groq API key](https://console.groq.com/keys)

## Setup

```bash
# Clone and enter the project
cd "MF RAG Chatbot"

# Create virtual environment
python -m venv .venv

# Activate (Windows PowerShell)
.\.venv\Scripts\Activate.ps1

# Install dependencies
pip install -r requirements.txt

# Configure environment
copy .env.example .env
# Edit .env and set GROQ_API_KEY=your_key_here
```

## Verify Phase 0 (Groq smoke test)

```bash
# Unit tests (no API key required)
pytest -m "not integration"

# Live Groq integration (requires GROQ_API_KEY in .env)
pytest tests/test_groq_smoke.py
# or
python -m src.rag.smoke
```

## Fetch Groww scheme pages (Phase 1)

Downloads the five allowlisted Groww HTML pages to `data/raw/{scheme_id}/`
(with SHA-256 checksum and fetch timestamp in `manifest.json`).

```bash
python -m src.ingest.fetch
```

If Groww blocks the request, save each scheme page from the browser as
`data/raw/{scheme_id}/scheme_page.html` and run:

```bash
python -m src.ingest.fetch --offline
```

Details: [`data/raw/README.md`](data/raw/README.md).

## Parse Groww HTML (Phase 1)

Converts fetched HTML to normalized plain text at
`data/processed/{scheme_id}/scheme_page.txt`.

```bash
python -m src.ingest.parse
```

Requires raw HTML from the fetch step above.

## Chunk + tag (Phase 1)

Splits each processed page into fact-atom chunks (expense ratio, SIP, exit
load, and so on — not token windows) and writes `data/processed/chunks.jsonl`.

```bash
python -m src.ingest.chunk
```

Requires `scheme_page.txt` from the parse step above.

## Embed + index (Phase 1)

Upserts `data/processed/chunks.jsonl` into the local Chroma collection
`groww_scheme_facts` (MiniLM embeddings, cosine space).

```bash
python -m src.ingest.run
python -m src.ingest.run --rebuild   # drop stale ids, then re-add
```

`--rebuild` deletes the collection first so dropped fact-atoms cannot linger.
The index lives at `CHROMA_PATH` (default `data/processed/chroma`).

## Offline retrieval check (Phase 1)

Runs the filtered probe table (expense ratio, exit load, SIP, lock-in,
benchmark, process) against the index. No Groq call. Pass = expected
`section` at rank 1 when `scheme_id` is filtered.

```bash
python -m src.ingest.retrieve_check
python -m src.ingest.retrieve_check --diagnostics   # unfiltered mix (not gated)
pytest tests/test_retrieval_facts.py
```

## Inspect embeddings + example retrieval

Print stored MiniLM vectors (first 8 dimensions by default) and a few
example retrieve calls against the same index. No Groq.

```bash
python -m src.ingest.inspect
python -m src.ingest.inspect --scheme hdfc_elss_tax_saver_direct_growth
python -m src.ingest.inspect --query "What is the expense ratio of HDFC Large Cap Fund Direct Growth?" --scheme-id hdfc_large_cap_direct_growth --show-query-vec
python -m src.ingest.inspect --out data/processed/embeddings.tsv
```

`--full` prints all 384 dimensions. `--retrieval-only` / `--embeddings-only` skip the other half.

## Run API + UI (Phase 4)

### Quick start (run scripts)

From the project root with the venv active:

**Terminal 1 — API**

```powershell
# Windows PowerShell
.\scripts\run_api.ps1
```

```bash
# macOS / Linux
./scripts/run_api.sh
```

Equivalent manual command:

```bash
uvicorn src.api.main:app --reload --host 127.0.0.1 --port 8000
```

**Terminal 2 — React UI**

```powershell
# Windows PowerShell
.\scripts\run_ui.ps1
```

```bash
# macOS / Linux
./scripts/run_ui.sh
```

Equivalent manual command:

```bash
cd frontend
npm install
npm run dev
```

Open [http://localhost:5173](http://localhost:5173). The UI loads schemes and example questions from the API, shows all five HDFC funds in the sidebar, and keeps the disclaimer visible.

Optional: set `VITE_API_BASE_URL=http://127.0.0.1:8000` in `frontend/.env` if not using the Vite proxy.

### Smoke E2E (API)

Verifies a factual answer (expense ratio) and an advisory refusal through the same `POST /api/v1/ask` path the UI uses. No live Groq key required when the vector index is built.

```bash
# In-process (no server needed)
python -m src.api.smoke_e2e

# Against a running API
python -m src.api.smoke_e2e --base-url http://127.0.0.1:8000
```

Requires `python -m src.ingest.run --rebuild` first if `data/processed/chroma` is empty.

Pytest equivalent:

```bash
pytest tests/test_smoke_e2e.py
pytest tests/test_api.py
```

## Architecture & Groq role

High-level flow (see [`docs/Architecture.md`](docs/Architecture.md)):

```text
User question → intent classifier → guardrails (refuse / redirect) OR
  scheme resolver → filtered retrieval (Chroma + MiniLM) → Groq answer → format validators
```

| Component | Technology | Role |
|-----------|------------|------|
| Corpus | Five Groww scheme HTML pages | Sole source of scheme facts |
| Embeddings | Local `all-MiniLM-L6-v2` | Chunk + query vectors (no Groq) |
| Vector store | Chroma (`groww_scheme_facts`) | Filtered retrieval by `scheme_id` |
| Intent classify | Groq (`GROQ_CLASSIFY_MODEL`) | Ambiguous advisory / scope labels |
| Answer generate | Groq (`GROQ_CHAT_MODEL`) | ≤3-sentence grounded answer from retrieved atoms |
| Citations | Metadata (`citation_url` in chunks) | System-owned Groww URL — model must not invent links |

Groq is used only for **classification** and **generation**. Embeddings stay local. AMFI/SEBI URLs appear on **refusal** paths only, not in the retrieval corpus.

## Environment variables

Copy `.env.example` to `.env`. Key settings:

| Variable | Purpose |
|----------|---------|
| `GROQ_API_KEY` | Required for live Groq answers (optional for rule-only / no-Groq fallback) |
| `GROQ_CHAT_MODEL` | Answer generation model |
| `GROQ_CLASSIFY_MODEL` | Intent classification model |
| `CHROMA_PATH` | Persistent Chroma directory (default `data/processed/chroma`) |
| `EMBEDDING_MODEL` | Sentence-transformers model (default `all-MiniLM-L6-v2`) |
| `RETRIEVAL_MAX_DISTANCE` | Cosine distance ceiling for sufficient evidence |
| `RETRIEVAL_TOP_K` | Retrieved chunks per question (default `3`) |

## Testing

```bash
# CI default — no live Groq, uses tests/fixtures/chunks.jsonl for index tests
pytest -m "not integration"

# API + smoke + eval contracts
pytest tests/test_api.py tests/test_smoke_e2e.py tests/test_eval_contracts.py

# Live Groq end-to-end (requires GROQ_API_KEY + index)
pytest -m integration

# Demo walkthrough script (no server)
python -m src.api.demo
.\scripts\demo.ps1
```

See [`docs/eval.md`](docs/eval.md) for the full evaluation plan and [`docs/demo.md`](docs/demo.md) for the pre-demo checklist.

## Re-ingest (refresh Groww data)

When NAV, TER, or exit loads change on Groww, re-run the ingest pipeline locally. Footer dates track page as-of metadata, not live ticks.

```bash
python -m src.ingest.fetch
python -m src.ingest.parse
python -m src.ingest.run --chunk --rebuild
python -m src.ingest.retrieve_check
```

Full playbook: [`docs/reingest.md`](docs/reingest.md).

## Daily refresh (Phase 6 — GitHub Actions)

The **Daily ingest** workflow runs automatically every day at **10:00 AM IST** (04:30 UTC) and can be triggered manually from the Actions tab.

Pipeline (same as manual re-ingest):

```text
fetch → parse → chunk → embed (--rebuild) → retrieve_check → pytest gate
```

Local equivalent:

```bash
./scripts/daily_ingest.sh
# or
python -m src.ingest.pipeline --strict-fetch
```

### Publish strategy (artifact)

On success, the workflow uploads a GitHub Actions **artifact** containing:

- `data/processed/chroma/` — rebuilt Chroma index
- `data/processed/chunks.jsonl` — fact-atom corpus

**Deploying the updated index:** download the latest `chroma-index-*` artifact from Actions and copy `chroma/` + `chunks.jsonl` into your host’s `data/processed/` (or set `CHROMA_PATH` accordingly), then restart the API.

Artifacts are retained for 14 days. No `GROQ_API_KEY` is required on this job.

Workflow file: [`.github/workflows/daily-ingest.yml`](.github/workflows/daily-ingest.yml)

## Known limitations

By design (see Architecture §11):

1. **Narrow corpus** — only five HDFC schemes on Groww; other AMCs/schemes are out of scope.
2. **No live market data** — no portfolio advice, tax personalization, or return forecasting.
3. **Stale risk** — expense ratios and loads change on Groww; footer reflects last ingested page as-of date until re-ingest.
4. **Groww-only scheme sources** — AMC PDFs and aggregators other than the five allowlisted Groww URLs are excluded.
5. **Single citation** — one Groww URL per answer; limited multi-document synthesis.
6. **LLM non-determinism** — mitigated by grounding + validators, not eliminated.
7. **Thin process answers** — statement-download workflows are not invented if absent from the page.
8. **HTML layout dependency** — Groww markup changes can break parsing until ingest is updated.
9. **Riskometer gap** — not present in the current parsed corpus; risk-level questions fail closed.

## Project layout

```text
MF RAG Chatbot/
├── data/registry/     # schemes, Groww allowlist, educational links
├── docs/              # problem statement, architecture, plan, demo, reingest
├── frontend/          # React + Vite chat UI (Phase 4)
├── scripts/           # run_api, run_ui, demo, daily_ingest helpers
├── src/
│   ├── api/           # FastAPI app (Phase 4)
│   ├── ingest/        # fetch, parse, chunk, embed, retrieve_check, inspect
│   ├── config.py      # settings from .env
│   ├── registry.py    # YAML loaders
│   └── rag/           # Groq client + retriever + orchestrator
└── tests/
```

## Schemes in scope (HDFC via Groww)

| Scheme | Groww page |
|--------|------------|
| HDFC Mid Cap Fund - Direct Growth | [link](https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth) |
| HDFC Silver ETF FoF - Direct Growth | [link](https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth) |
| HDFC BSE Sensex Index Fund - Direct Growth | [link](https://groww.in/mutual-funds/hdfc-bse-sensex-index-fund-direct-growth) |
| HDFC Large Cap Fund - Direct Growth | [link](https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth) |
| HDFC ELSS Tax Saver Fund - Direct Plan Growth | [link](https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth) |

## Roadmap

| Phase | Status |
|-------|--------|
| P0 — Foundations | Done |
| P1 — Corpus & ingest | Done |
| P2 — Guardrails | Done |
| P3 — RAG path | Done |
| P4 — API + UI | Done |
| P5 — Hardening | Done |
| P6 — Daily ingest scheduler | Done |

## Disclaimer

This assistant provides facts from curated public sources only. It does **not** provide investment advice, recommendations, or return calculations.

**Facts-only. No investment advice.**
