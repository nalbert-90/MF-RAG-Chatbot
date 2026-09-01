# Implementation Plan: Mutual Fund FAQ Assistant

Phase-wise plan to build the facts-only RAG chatbot defined in [`problem_statement.md`](./problem_statement.md) and [`Architecture.md`](./Architecture.md).

**Source of truth for corpus & citations:** [`Architecture.md`](./Architecture.md) §5 and ADR — the five **Groww scheme page URLs** are the entire scheme corpus, retrieval grounding, and `citation_url` set.

**LLM provider:** [Groq](https://groq.com) (OpenAI-compatible Chat Completions API)  
**Primary principle:** Accuracy over intelligence — grounded, cited, facts-only answers from allowlisted Groww pages.

---

## Locked tech decisions

| Layer | Choice | Notes |
|-------|--------|-------|
| LLM | **Groq** | Classification + grounded answer generation |
| Groq models (v1 defaults) | `llama-3.3-70b-versatile` (answers) · `llama-3.1-8b-instant` (intent classify) | Override via `.env` |
| Embeddings | Local `sentence-transformers` (`all-MiniLM-L6-v2`) | Keeps Groq usage chat-only; no embedding dependency on Groq |
| Vector store | Chroma (persistent local dir) | Lightweight, file-backed |
| API | FastAPI + uvicorn | `POST /api/v1/ask` and helpers |
| UI | Streamlit | Minimal chat; welcome, 3 examples, disclaimer |
| Config | `.env` + YAML registries | `GROQ_API_KEY`, model names, paths |
| Language | Python 3.11+ | Single codebase for ingest + API + UI |
| Corpus & citations | **Groww `groww.in` scheme pages** (five HDFC funds) | Metadata injects `citation_url`; models must not invent links |
| Refusal education | AMFI / SEBI investor-education URLs | **Not** used as scheme-fact citations or retrieval corpus |

Groww scheme URLs are **the product corpus and the only scheme-fact citation source**. Other aggregators, blogs, and AMC/AMFI/SEBI pages are **out of the retrieval corpus**. AMFI/SEBI links appear only on advisory / out-of-scope **refusal** paths (Architecture §5.2, §11.4).

---

## Phase overview

| Phase | Name | Goal | Exit criteria (summary) |
|-------|------|------|-------------------------|
| **P0** | Foundations | Repo, config, Groq smoke test | Project runs; Groq hello-world works |
| **P1** | Corpus & ingest | 5 Groww scheme pages indexed with metadata | Retrieval returns relevant chunks offline |
| **P2** | Guardrails | Classify / refuse / PII / format rules | Advisory & PII queries never hit open generation |
| **P3** | RAG path | Retrieve → Groq generate → cite Groww URL → footer | Golden factual Q&A passes format + grounding |
| **P4** | API + UI | Ship minimal compliant interface | End-to-end ask from UI |
| **P5** | Hardening | Tests, README, limitations, re-ingest | Demo-ready + documented |
| **P6** | Daily ingest scheduler | GitHub Actions cron runs full ingest pipeline | Corpus + Chroma refreshed daily without manual steps |

Suggested sequence is strict for P0→P3; P4 can start API stubs in parallel with late P3; P5 runs continuously as tests are added; **P6** follows P1 (ingest CLI) and can ship in parallel with P5 once the offline pipeline is stable. Maps to Architecture §13.

---

## Phase 0 — Foundations

**Objective:** Scaffold the repo and prove Groq connectivity before any RAG work. (Architecture §8, §13 P0)

### Tasks

1. **Create repository layout** (per Architecture §8)
   - `docs/`, `data/raw/` (Groww HTML), `data/processed/`, `data/registry/`
   - `src/ingest/`, `src/rag/`, `src/guardrails/`, `src/api/`, `src/ui/`
   - `tests/`, `.env.example`, `requirements.txt`, `README.md` skeleton
2. **Python environment**
   - Create venv; pin dependencies: `fastapi`, `uvicorn`, `groq`, `chromadb`, `sentence-transformers`, `beautifulsoup4` (Groww HTML), `pypdf` (optional), `streamlit`, `pydantic`, `pyyaml`, `python-dotenv`, `httpx`, `pytest`
3. **Config & secrets**
   - `.env.example` with:
     - `GROQ_API_KEY=`
     - `GROQ_CHAT_MODEL=llama-3.3-70b-versatile`
     - `GROQ_CLASSIFY_MODEL=llama-3.1-8b-instant`
     - `CHROMA_PATH=data/processed/chroma`
     - `EMBEDDING_MODEL=all-MiniLM-L6-v2`
   - Load via `python-dotenv`; never commit `.env`
4. **Scheme & source registries (stubs)**
   - `data/registry/schemes.yaml` — five HDFC schemes + `scheme_id`s + **Groww citation URLs** (Architecture §5.1)
   - `data/registry/sources_allowlist.yaml` — the same five `groww.in` scheme page URLs (`source_org: groww`, `doc_type: scheme_page`)
   - `data/registry/educational_links.yaml` — AMFI + SEBI investor-education URLs for **refusals only**
5. **Groq client module**
   - `src/rag/groq_client.py`: thin wrapper around official `groq` SDK
   - Support `chat(messages, model, temperature, max_tokens)`
   - Defaults: low temperature for factual answers (`~0.1–0.2`); slightly higher OK for classify if needed
6. **Smoke test**
   - Script or pytest: call Groq with a fixed prompt; assert non-empty response
7. **README skeleton**
   - Project one-liner, how to get a Groq API key, setup steps placeholder, disclaimer

### Deliverables

- Runnable project skeleton  
- Working `GROQ_API_KEY` integration  
- Registries present with Groww allowlist URLs

### Acceptance criteria

- [ ] `pytest tests/test_groq_smoke.py` passes with a valid key  
- [ ] `.env.example` documents all required vars  
- [ ] No secrets in git  

### Estimated effort

0.5–1 day

---

## Phase 1 — Corpus definition & ingestion

**Objective:** Fetch and index the five allowlisted **Groww scheme pages** in Chroma (Architecture §5).

### Schemes in scope (Groww corpus)

| Scheme ID | Scheme | Category | Citation URL |
|-----------|--------|----------|--------------|
| `hdfc_mid_cap_direct_growth` | HDFC Mid Cap Fund - Direct Growth | Mid Cap | https://groww.in/mutual-funds/hdfc-mid-cap-fund-direct-growth |
| `hdfc_silver_etf_fof_direct_growth` | HDFC Silver ETF FoF - Direct Growth | Commodity / FoF | https://groww.in/mutual-funds/hdfc-silver-etf-fof-direct-growth |
| `hdfc_bse_sensex_index_direct_growth` | HDFC BSE Sensex Index Fund - Direct Growth | Index | https://groww.in/mutual-funds/hdfc-bse-sensex-index-fund-direct-growth |
| `hdfc_large_cap_direct_growth` | HDFC Large Cap Fund - Direct Growth | Large Cap | https://groww.in/mutual-funds/hdfc-large-cap-fund-direct-growth |
| `hdfc_elss_tax_saver_direct_growth` | HDFC ELSS Tax Saver Fund - Direct Plan Growth | ELSS | https://groww.in/mutual-funds/hdfc-elss-tax-saver-fund-direct-plan-growth |

Curated allowlist = **these five URLs only** (not an open web crawl). Every indexed chunk’s `citation_url` **must** be the Groww URL for that `scheme_id`. `source_org` is always `groww`; `doc_type` is `scheme_page` (Architecture §5.3).

### Tasks

1. **Finalize allowlist**
   - Record the five Groww URLs above in `sources_allowlist.yaml` (`allowed_domains: [groww.in]`)
   - Keep AMFI/SEBI URLs in `educational_links.yaml` for refusals — **do not** add them as scheme-fact `citation_url`s
   - Explicitly **exclude** other aggregators, blogs, and AMC PDF hosts from scheme-fact citations
2. **Fetch & store raw docs**
   - `src/ingest/fetch.py` — download each Groww scheme **HTML** to `data/raw/{scheme_id}/` with checksum + fetch timestamp
   - Manual download / saved-HTML fallback documented if Groww blocks bots (Architecture §5.4)
3. **Parse & normalize**
   - Groww HTML → plain text (`src/ingest/parse.py`, BeautifulSoup)
   - Light cleanup (nav/chrome/headers/footers noise reduction where practical)
4. **Chunk + tag** (see **Chunking strategy** below — do **not** use Architecture §4.5’s 400–800 token windows on this corpus)
   - Input: `data/processed/{scheme_id}/scheme_page.txt` + `parse_manifest.json`
   - Heading-aware region split → fact-atom extract on packed preamble lines → drop empty/duplicate/performance/cross-scheme noise
   - Attach metadata per Architecture §5.3: `scheme_id`, `source_org=groww`, `doc_type=scheme_page`, `citation_url` (Groww URL), `published_or_as_of`, `section`
   - Write `data/processed/chunks.jsonl`
5. **Embed + upsert Chroma** (see **Retrieval strategy** below — do **not** treat Architecture §4.5’s unfiltered top-k as the happy path)
   - Input: `data/processed/chunks.jsonl` (46 fact-atoms; do not re-embed raw `scheme_page.txt`)
   - `src/ingest/embed_index.py`: local MiniLM (`all-MiniLM-L6-v2`) on the `text` field only
   - Collection `groww_scheme_facts`, cosine space, persist under `CHROMA_PATH`
   - Document id = `chunk_id`; upsert so re-ingest replaces in place (`--rebuild` deletes the collection first so dropped atoms cannot linger)
   - CLI: `python -m src.ingest.run` (chunk if needed → embed → upsert)
6. **Offline retrieval check** (same **Retrieval strategy** — this is the P1 gate, not a Groq call)
   - `python -m src.ingest.retrieve_check` (and later `tests/test_retrieval_facts.py`): embed each probe query with the same MiniLM; search with **required** `scheme_id` + `source_org=groww` + `doc_type=scheme_page` filters; print top-3 (`chunk_id`, `section`, distance)
   - Hit@1 on the filtered probe table (expense ratio, exit load, SIP, lock-in, benchmark, process) including the known collisions (Sensex vs Silver TER `0.22%`; Mid vs Large exit load `1%` / 1 year)
   - Unfiltered search is a **diagnostic only** — expect scheme mix on SIP / stamp-duty / shared TER; do not use it as the pass criterion
   - Riskometer: index has **no** `section=riskometer` atom; probes must miss (fail-closed), not retrieve a fabricated risk chunk

### Chunking strategy (from `data/processed/`)

Architecture §4.5’s ~400–800 token windows with 50–100 token overlap **do not apply** to this corpus. Each parsed Groww page is a short, structured extract — not a long PDF. Token windows would index the whole page as one blob and mix TER/SIP with historic returns.

**Observed corpus (parse manifests, 2026-08-30):**

| `scheme_id` | Lines | Chars | Distinctive preamble |
|-------------|-------|-------|----------------------|
| `hdfc_mid_cap_direct_growth` | 48 | 1354 | SIP ₹100 · TER 0.74% · exit load 1% / 1 year |
| `hdfc_silver_etf_fof_direct_growth` | 47 | 1273 | SIP ₹100 · TER 0.22% · exit load 1% / 15 days · 2-year tax slab |
| `hdfc_bse_sensex_index_direct_growth` | 48 | 1311 | SIP ₹100 · TER 0.22% · exit load 0.25% / 3 days |
| `hdfc_large_cap_direct_growth` | 47 | 1333 | SIP ₹100 · TER 1.02% · exit load 1% / 1 year |
| `hdfc_elss_tax_saver_direct_growth` | 49 | 1291 | **`Lock-in period: 3Y`** · SIP ₹500 · TER 1.19% · exit load Nil |

Whole page ≈ 250–350 tokens. Implement in `src/ingest/chunk.py`; emit `data/processed/chunks.jsonl`.

#### Page layout (same for all five)

Split each `scheme_page.txt` at the first `###` heading into **preamble** vs **headed sections**.

**Preamble (almost all v1 facts live here)** — 3–4 dense lines, not markdown:

1. Optional `Lock-in period: 3Y` (ELSS only).
2. Packed hero strip, one line: `NAV: {dd Mon 'yy} ₹{nav} Min. for SIP ₹{n} Fund size (AUM) ₹{aum} Cr Expense ratio {pct}% Rating {n|--}`.
3. Packed charges paragraph: `Exit load … Stamp duty on investment: 0.005% … Tax implication … Check past data`.
4. `Fund benchmark {name} Scheme Information Document(SID)`.
5. Occasional **cross-scheme leak** (drop it): Mid Cap and Large Cap files contain a stray `HDFC ELSS Tax Saver Fund Direct Plan Growth` line.

**Headed sections (`###` / `####` from the parser):**

| Heading | What is in the file | Index? |
|---------|---------------------|--------|
| `### Return calculator` | Period / rupee / % rows (historic SIP illustration) | **No** — performance; would tempt generation |
| `### Returns and rankings` | Unlabeled `%` lists + category average | **No** |
| `### Exit load, stamp duty and tax` plus empty `####` children | Headings only; body already in preamble line 3 | **No** |
| `### Fund management` | Manager name + tenure lines | Yes → `section=other` |
| `### About …` / `#### Investment Objective` | Heading only (empty body) | **No** |
| `### Fund house` + trailing `Fund benchmark:` | Duplicate of preamble benchmark | **No** |

#### Fact-atom inventory (one chunk per row, per scheme)

Do **not** keep the hero strip or charges paragraph as a single chunk. MiniLM will otherwise rank a mixed NAV/SIP/TER/AUM line for every fact query.

| `section` | Extract from | Example (Sensex page) | Schemes |
|-----------|--------------|----------------------|---------|
| `lock_in` | Leading `Lock-in period:` line | `Lock-in period: 3Y` | ELSS only |
| `sip` | Hero: `Min. for SIP ₹…` | `Min. for SIP ₹100` | All five |
| `expense_ratio` | Hero: `Expense ratio …%` | `Expense ratio 0.22%` | All five |
| `exit_load` | Charges paragraph, load sentence only | `Exit load of 0.25% if redeemed within 3 days` | All five |
| `process` | Same paragraph: stamp duty + tax implication | `Stamp duty … 0.005%` + `If you redeem within one year…` | All five |
| `benchmark` | First `Fund benchmark` line; strip `Scheme Information Document(SID)` | `BSE Sensex Total Return Index` | All five |
| `other` (NAV) | Hero: `NAV: {date} ₹{value}` | `NAV: 28 Aug '26 ₹739.71` | All five |
| `other` (AUM) | Hero: `Fund size (AUM)` | `Fund size (AUM) ₹8,657.46 Cr` | All five |
| `other` (rating) | Hero: `Rating` | `Rating 1` / `Rating --` | All five |
| `other` (managers) | `### Fund management` body | `Arun Agarwal Aug 2020 - Present` | All five |

`riskometer` is **not** in any current `scheme_page.txt`. Do **not** invent a chunk. Retrieval for risk-level questions must fail closed until parse extracts it.

Suggested extract patterns (preamble is packed, not labeled fields):

```text
NAV:           ^NAV: (\d{1,2} [A-Za-z]{3} '\d{2}) ₹([\d,.]+)
SIP:           Min\. for SIP ₹([\d,]+)
AUM:           Fund size \(AUM\) ₹([\d,.]+) Cr
TER:           Expense ratio ([\d.]+%)
Rating:        Rating (\d+|--)
Lock-in:       ^Lock-in period:\s*(\S+)
Exit load:     Exit load (Nil|of .+?)(?=\s+Stamp duty)
Stamp+tax:     Stamp duty on investment: .+$
Benchmark:     Fund benchmark:?\s*(.+?)(?:\s+Scheme Information Document)?$
```

`published_or_as_of`: parse the NAV date (`28 Aug '26` → `2026-08-28`). Fallback: date of `parse_manifest.json` → `parsed_at`.

#### Chunk text & metadata rules

1. **Prefix every chunk** with `{scheme_name}.` so embeddings disambiguate five pages that share similar TER/SIP phrasing.
   - Example: `HDFC BSE Sensex Index Fund - Direct Growth. Expense ratio 0.22%.`
2. **No sliding-window overlap.** If two facts share a source line, emit two chunks (source-line duplication is intended; 50–100 token overlap is not).
3. **Stable `chunk_id`:** `{scheme_id}::{section}` or `{scheme_id}::{section}::{atom}` (e.g. `hdfc_large_cap_direct_growth::other::nav`) so re-ingest upserts cleanly.
4. **Drop** any line that is the display name of a *different* `scheme_id` (ELSS widget leak on Mid Cap / Large Cap pages).
5. **Drop** `###` / `####` headings with no following body.
6. **Do not index** `Return calculator` or `Returns and rankings`. Performance queries are a redirect path (Architecture §4.3, §6.3), not a generate-from-chunk path.
7. Metadata on every row must match Architecture §5.3 (`source_org=groww`, `doc_type=scheme_page`, allowlisted `citation_url`, `section` from the table above).

Worked example — Sensex hero line  
`NAV: 28 Aug '26 ₹739.71 Min. for SIP ₹100 Fund size (AUM) ₹8,657.46 Cr Expense ratio 0.22% Rating 1`  
→ five chunks (`other::nav`, `sip`, `other::aum`, `expense_ratio`, `other::rating`), not one mixed document.

Confirmed volume from `chunks.jsonl` (ingested 2026-08-31): **46 vectors** — 9 atoms × 4 schemes + 10 on ELSS (`lock_in`). After a `scheme_id` filter the candidate set is 9–10 documents; `top_k=3` (eval hit@5) is enough. Unfiltered `top_k` over all 46 is **not** the v1 happy path — see **Retrieval strategy**.

### Retrieval strategy (from `data/processed/chunks.jsonl`)

Architecture §4.5’s “embed question → optional metadata filters → top-k” is too weak for this index. The chunker already split facts; MiniLM still cannot tell five HDFC Direct Growth pages apart from the fact phrasing alone.

**Why:** 46 short, similarly worded atoms. Scheme-name prefixes on `text` are a weak prior. Several **values are identical across schemes**, so cosine nearest-neighbour without a `scheme_id` filter will confidently return the wrong fund.

#### Index inventory (do not re-chunk at embed time)

| `scheme_id` | Atoms | Distinctive values in this snapshot |
|-------------|-------|-------------------------------------|
| `hdfc_mid_cap_direct_growth` | 9 | TER **0.74%** · exit load **1% / 1 year** · SIP ₹100 · NIFTY Midcap 150 TRI |
| `hdfc_silver_etf_fof_direct_growth` | 9 | TER **0.22%** · exit load **1% / 15 days** · **2-year** tax slab · Domestic Price of Silver · `Rating --` |
| `hdfc_bse_sensex_index_direct_growth` | 9 | TER **0.22%** · exit load **0.25% / 3 days** · BSE Sensex TRI |
| `hdfc_large_cap_direct_growth` | 9 | TER **1.02%** · exit load **1% / 1 year** · SIP ₹100 · NIFTY 100 TRI |
| `hdfc_elss_tax_saver_direct_growth` | 10 | **`lock_in` 3Y** · SIP **₹500** · TER **1.19%** · exit load **Nil** · NIFTY 500 TRI |

No `riskometer` row exists. NAV / AUM / rating / managers live under `section=other` with `chunk_id` suffixes `::nav`, `::aum`, `::rating`, `::managers`. `published_or_as_of` is **2026-08-28** (NAV date) on every current row.

#### Cross-scheme collisions (unfiltered MiniLM will mix these)

| Shared phrasing / value | Schemes | Wrong-scheme risk (edgecase RT-02) |
|-------------------------|---------|-------------------------------------|
| `Min. for SIP ₹100` | Mid, Silver, Sensex, Large (ELSS is ₹500) | SIP query without filter |
| `Expense ratio 0.22%` | **Silver and Sensex** | TER query without filter — highest-risk collision |
| `Exit load of 1% if redeemed within 1 year` | **Mid and Large** | Exit-load query without filter |
| Stamp duty `0.005%` (July 1st, 2020) | All five | Process / stamp-duty query |
| 1-year 20% / 12.5% tax implication | Mid, Sensex, Large, ELSS (Silver is 2-year slab) | Tax query without filter |
| `Rating 5` | Mid and ELSS | Rating query without filter |

Within one scheme the nine/ten atoms are semantically distinct (TER vs SIP vs exit load vs benchmark). **Filtered** retrieval is easy; **unfiltered** retrieval is unsafe. That is the whole v1 strategy: resolve scheme, then search a 9–10 document subspace.

Unique atoms that can hit even unfiltered (still filter in production): ELSS `lock_in`, ELSS SIP ₹500, ELSS exit load Nil, Sensex exit load 0.25%/3 days, Silver 15-day load, unique TERs (0.74 / 1.02 / 1.19), unique benchmarks, unique NAVs.

#### Embed + Chroma contract (`src/ingest/embed_index.py`)

| Setting | v1 choice | Why |
|---------|-----------|-----|
| Source | `data/processed/chunks.jsonl` only | Already fact-atoms; embedding whole `scheme_page.txt` would undo task 4 |
| Model | `EMBEDDING_MODEL` / `all-MiniLM-L6-v2` (384-d, local) | Same model at query time; no Groq embeddings |
| Embedded field | `text` as stored (scheme-name prefix included) | Do not concatenate metadata into the vector |
| Collection | `groww_scheme_facts` | One collection; five schemes via metadata |
| Space | **cosine** | MiniLM sentence embeddings |
| Persist | `CHROMA_PATH` → `data/processed/chroma` | File-backed; gitignore the dir |
| Document id | `chunk_id` (e.g. `hdfc_large_cap_direct_growth::expense_ratio`) | Stable upsert / IG-04 |
| Metadata on every vector | `scheme_id`, `scheme_name`, `source_org`, `doc_type`, `section`, `title`, `citation_url`, `published_or_as_of`, `ingested_at` | Chroma `where` filters; citation ownership stays in metadata. Values must be str/int/float/bool |
| Not indexed | AMFI/SEBI URLs, raw HTML, performance headings, empty docs | Architecture §5.2 / chunking drop rules |

Rebuild CLI:

```text
python -m src.ingest.run              # upsert 46 ids from chunks.jsonl
python -m src.ingest.run --rebuild    # delete collection, then add (stale atoms cannot linger)
```

Assert after upsert: `count() == 46`; exactly five distinct `scheme_id`s; every `citation_url` is one of the five Groww allowlist URLs; `source_org=groww`; `doc_type=scheme_page`; **zero** documents with `section=riskometer`.

#### Query-time retrieve contract (P1 check + what P3 reuses)

Implement once (`src/ingest/embed_index.py` query helper or a thin `src/rag/retriever.py` stub that P3 will own). **No Groq** on this path.

```text
embed(query) with the same MiniLM
→ Chroma query
     where: source_org=groww AND doc_type=scheme_page
            AND scheme_id=<resolved>     # required when scheme is known
     n_results: 3 (allow 5 to match eval hit@5)
→ return hits: text, chunk_id, section, scheme_id, citation_url, published_or_as_of, distance
```

| Rule | Do | Do not |
|------|----|--------|
| Scheme known | **Always** `where.scheme_id` | Rely on scheme-name prefix in the vector to pick the fund |
| Scheme unknown (P3 later) | Unfiltered search is diagnostic / last resort; P3 should refuse ambiguous “HDFC fund” (edgecase SC-05) rather than answer from a mixed top-k | Treat unfiltered rank-1 as grounded |
| `section` filter | Leave **off** at query time — the user does not send a section; MiniLM ranks TER vs SIP inside the 9-atom scheme set | Pre-filter `section=expense_ratio` in v1 (hides misses; P1 must prove ranking works) |
| Reranker | Skip in P1 (9–10 candidates) | Add a cross-encoder for this corpus size |
| Threshold | P1 gate is **rank-1 `section` match** on the probe table, not a guessed cosine cutoff | Ship an uncalibrated numeric threshold as the only control |
| Citation | Take `citation_url` + `published_or_as_of` from the best **kept** hit’s metadata | Let a later LLM invent a URL |
| Empty / missing index | Fail with “index not ready” (edgecase RT-04) | Fall through to Groq |

P3 may add a calibrated cosine-distance cutoff on this same helper (below cutoff → insufficient-evidence refusal). Do not invent the cutoff in P1.

#### Offline probe table (`src/ingest/retrieve_check.py`)

Run **with** `scheme_id` filter. Pass = expected `section` (and `chunk_id` where listed) at **rank 1**. Print top-3 + distance for debugging.

| Probe question (natural language) | `scheme_id` filter | Rank-1 `section` | Rank-1 `chunk_id` | Snapshot cue (do not hard-code as the only assert) |
|-----------------------------------|--------------------|------------------|-------------------|-----------------------------------------------------|
| What is the expense ratio of HDFC Large Cap Fund Direct Growth? | `hdfc_large_cap_direct_growth` | `expense_ratio` | `…::expense_ratio` | 1.02% |
| What is the expense ratio of HDFC BSE Sensex Index Fund Direct Growth? | `hdfc_bse_sensex_index_direct_growth` | `expense_ratio` | `…::expense_ratio` | 0.22% — **must not** be Silver’s chunk |
| What is the expense ratio of HDFC Silver ETF FoF Direct Growth? | `hdfc_silver_etf_fof_direct_growth` | `expense_ratio` | `…::expense_ratio` | 0.22% — **must not** be Sensex’s chunk |
| What is the exit load for HDFC Mid Cap Fund Direct Growth? | `hdfc_mid_cap_direct_growth` | `exit_load` | `…::exit_load` | 1% / 1 year — **must not** be Large Cap |
| What is the exit load for HDFC Large Cap Fund Direct Growth? | `hdfc_large_cap_direct_growth` | `exit_load` | `…::exit_load` | 1% / 1 year — **must not** be Mid Cap |
| What is the exit load for HDFC BSE Sensex Index Fund Direct Growth? | `hdfc_bse_sensex_index_direct_growth` | `exit_load` | `…::exit_load` | 0.25% / 3 days |
| What is the exit load for HDFC ELSS Tax Saver Fund? | `hdfc_elss_tax_saver_direct_growth` | `exit_load` | `…::exit_load` | Nil |
| What is the minimum SIP for HDFC ELSS Tax Saver Fund? | `hdfc_elss_tax_saver_direct_growth` | `sip` | `…::sip` | ₹500 (the non-₹100 SIP) |
| What is the minimum SIP for HDFC Mid Cap Fund Direct Growth? | `hdfc_mid_cap_direct_growth` | `sip` | `…::sip` | ₹100 |
| What is the lock-in period for HDFC ELSS Tax Saver Fund? | `hdfc_elss_tax_saver_direct_growth` | `lock_in` | `…::lock_in` | 3Y |
| What is the lock-in for HDFC Silver ETF FoF? | `hdfc_silver_etf_fof_direct_growth` | — | — | **Miss** — no `lock_in` atom on this scheme (edgecase SC-07) |
| What is the benchmark of HDFC BSE Sensex Index Fund Direct Growth? | `hdfc_bse_sensex_index_direct_growth` | `benchmark` | `…::benchmark` | BSE Sensex Total Return Index |
| What is the stamp duty on HDFC Silver ETF FoF Direct Growth? | `hdfc_silver_etf_fof_direct_growth` | `process` | `…::process` | 0.005% + two-year tax slab |
| What is the risk level / riskometer of HDFC Mid Cap Fund? | `hdfc_mid_cap_direct_growth` | — | — | **Miss** — no riskometer in the index |

**Unfiltered diagnostics** (print, do not gate P1): the same TER `0.22%`, SIP ₹100, stamp-duty, and 1%/1-year exit-load questions **without** `scheme_id`. Expect mixed `scheme_id`s in top-3. That output is the evidence that P3 must keep the filter on.

**Must not appear** in any hit’s `text`: Return calculator rupee/% rows, unlabeled rankings `%` lists, or the ELSS display name on Mid/Large chunks (already dropped at chunk time; retrieval check is the backstop).

Suggested output per probe: query, filter, rank, distance, `chunk_id`, `section`, `scheme_id`, first 80 chars of `text`.

### Fact coverage checklist (must be retrievable from Groww pages)

Present in current `data/processed/*/scheme_page.txt` (chunk these):

- [ ] Expense ratio (hero strip)
- [ ] Exit load (charges paragraph)
- [ ] Minimum SIP (hero strip; ₹100 except ELSS ₹500)
- [ ] ELSS lock-in (`Lock-in period: 3Y` on ELSS page only)
- [ ] Benchmark (preamble `Fund benchmark` line)
- [ ] Stamp duty + tax implication (`section=process`; on-page capital-gains text — not a statements-download how-to)

Absent from current processed text (fail closed; do not index placeholders):

- [ ] Riskometer — **not extracted**; parse gap, not a chunking choice
- [ ] Statements / capital gains **download process** — tax *rates* are on-page; “how do I download the report?” is still insufficient-evidence / education-link (Architecture §5.5, §11.7)

### Deliverables

- Allowlisted Groww sources YAML  
- Raw HTML + processed corpus  
- `data/processed/chunks.jsonl` (fact-atom rows, not whole-page windows)  
- Populated Chroma index (`groww_scheme_facts`, 46 vectors)  
- Ingest CLI + offline retrieval-check script

### Acceptance criteria

- [ ] All five schemes represented in the index  
- [ ] Every chunk has a valid allowlisted Groww `citation_url` and `published_or_as_of` (NAV date or ingest as-of)  
- [ ] Chroma `count() == 46`; upsert is by `chunk_id`; `--rebuild` does not leave stale ids  
- [ ] Filtered retrieval: expense ratio, exit load, SIP, lock-in, benchmark, and process probes return the matching `section` at **rank 1** (see probe table)  
- [ ] Collision probes: Sensex TER query does not rank Silver’s `expense_ratio` first (and vice versa); Mid Cap exit-load query does not rank Large Cap’s `exit_load` first (and vice versa)  
- [ ] Silver lock-in probe and all riskometer probes miss — no `lock_in` on Silver, no `riskometer` section in the index  
- [ ] No chunk `text` contains historic-return calculator rows or unlabeled ranking `%` lists  
- [ ] No chunk from Mid Cap / Large Cap contains the ELSS scheme display name  
- [ ] No `citation_url` outside the five Groww scheme URLs  
- [ ] Riskometer queries do not retrieve a fabricated risk chunk  

### Estimated effort

1.5–3 days (mostly Groww HTML parsing quality + layout selectors; chunking itself is regex-on-preamble, not a generic splitter)

---

## Phase 2 — Guardrails & response rules

**Objective:** Ensure advisory, comparative, performance-calc, PII, and out-of-scope queries never produce investment advice. (Architecture §4.3, §6.2–6.4)

### Tasks

1. **PII detector (rules-first)**
   - Regex/heuristics for PAN, Aadhaar, account-like numbers, OTP, email, phone
   - On hit → `pii_risk` refusal; do not log raw message body
2. **Intent classifier**
   - Labels: `factual` | `advisory` | `performance` | `pii_risk` | `out_of_scope`
   - Hybrid:
     - Fast rules/keywords for obvious advice (“should I”, “which is better”, “recommend”)
     - Groq `GROQ_CLASSIFY_MODEL` with a strict JSON label schema for ambiguous cases
   - `src/guardrails/classifier.py`
3. **Refusal / redirect templates**
   - Advisory & out-of-scope: polite facts-only refusal + AMFI/SEBI educational link  
   - Performance: no calculations/comparisons; **redirect to the scheme’s Groww page URL only** (Architecture §4.3, §6.3)  
   - PII: warn user not to share sensitive data  
   - `src/guardrails/refusals.py`
4. **Response format validators**
   - Max 3 sentences  
   - Exactly one citation URL (system-injected Groww URL when `answered`)  
   - Footer: `Last updated from sources: <YYYY-MM-DD>`  
   - Advisory phrase blocklist (“you should”, “I recommend”, “better than”, etc.)  
   - `src/guardrails/validators.py`
5. **Unit tests**
   - `tests/test_guardrails.py` — advisory, comparison, PII, performance fixtures  
   - `tests/test_response_format.py` — sentence count, citation, footer

### Groq classify prompt contract (sketch)

```text
Return ONLY JSON: {"intent":"<one of: factual|advisory|performance|pii_risk|out_of_scope>"}
You classify mutual-fund user questions for a facts-only assistant.
Advisory = asks what to buy/sell or which is better.
Performance = asks to compute/compare returns.
...
```

### Deliverables

- Guardrails package  
- Refusal copy + educational links  
- Passing unit tests for non-factual paths

### Acceptance criteria

- [ ] “Should I invest in this fund?” → `refused` + educational link  
- [ ] “Which fund is better?” → `refused`  
- [ ] Return-comparison queries → `redirected` to the relevant **Groww scheme page URL**, no computed returns  
- [ ] Message containing PAN-like pattern → `pii_risk` refusal  
- [ ] Validators reject >3 sentences and advisory phrasing  

### Estimated effort

1–1.5 days

---

## Phase 3 — RAG orchestration (Groq-backed)

**Objective:** Wire retrieve → grounded Groq generation → validate → format for factual queries. (Architecture §4.4–4.7, §6.1)

### Tasks

1. **Retriever**
   - Reuse the P1 query helper: same MiniLM + collection `groww_scheme_facts`  
   - When `scheme_id` is resolved: **required** Chroma `where` filter `{scheme_id, source_org=groww, doc_type=scheme_page}` (unfiltered search mixes Silver/Sensex TER and Mid/Large exit load — see P1 Retrieval strategy)  
   - `top_k=3` (max 5); do not filter on `section` at query time  
   - Calibrate a cosine-distance cutoff on the P1 probe distances; below threshold → insufficient-evidence refusal  
   - `src/rag/retriever.py`
2. **Scheme resolver**
   - Map query text to one of five `scheme_id`s (alias list in YAML)  
   - If unresolved / ambiguous (“HDFC fund”) → refuse to pick a scheme (edgecase SC-05); do **not** answer from an unfiltered mixed top-k
3. **Prompt templates**
   - System prompt: facts-only, use context only, ≤3 sentences, no advice, no invented numbers/URLs  
   - User payload: question + retrieved chunks (text + citation metadata)  
   - Citation URL and last-updated date **owned by the orchestrator**, not trusted from the model  
   - `src/rag/prompts.py`
4. **Generator via Groq**
   - Call `GROQ_CHAT_MODEL` with low temperature and capped `max_tokens`  
   - `src/rag/generator.py`
5. **Orchestrator**
   - Flow: classify → (refuse | retrieve → generate → validate → retry once → format)  
   - Pick **one** primary citation from best chunk metadata (always that scheme’s Groww URL)  
   - Attach footer date from chunk `published_or_as_of`  
   - `src/rag/orchestrator.py`
6. **Golden Q&A set**
   - At least one question per fact type × representative schemes  
   - `tests/fixtures/golden_qa.json`  
   - `tests/test_retrieval_facts.py` + optional live Groq integration test (mark `@pytest.mark.integration`)

### API-shaped internal result

```json
{
  "status": "answered | refused | redirected",
  "answer": "...",
  "citation_url": "https://groww.in/mutual-funds/...",
  "last_updated": "YYYY-MM-DD",
  "disclaimer": "Facts-only. No investment advice."
}
```

### Deliverables

- End-to-end CLI: `python -m src.rag.ask "What is the expense ratio of ...?"`  
- Golden tests for factual path  
- Documented Groq model env vars

### Acceptance criteria

- [ ] Factual answers ≤3 sentences with exactly one **Groww** citation + last-updated footer  
- [ ] Answers grounded in retrieved Groww-page context (spot-check against live pages in Architecture §5.1)  
- [ ] No Groq answer path for advisory intents  
- [ ] Insufficient retrieval → safe refusal, not hallucination  
- [ ] Disclaimer string present on every response object  

### Estimated effort

2–3 days

---

## Phase 4 — API & minimal UI

**Objective:** Expose the orchestrator through FastAPI and a Streamlit chat UI that meets problem-statement UX requirements. (Architecture §4.1–4.2)

### Tasks

1. **FastAPI app**
   - `POST /api/v1/ask` — body `{ "question": "..." }`  
   - `GET /api/v1/health`  
   - `GET /api/v1/schemes` — from `schemes.yaml`  
   - `GET /api/v1/examples` — three fixed factual example questions  
   - Stateless; no user/session DB  
   - `src/api/main.py`
2. **Streamlit UI**
   - Persistent visible disclaimer: **Facts-only. No investment advice.**  
   - Welcome message describing HDFC facts-only scope (Groww-curated corpus)  
   - Three clickable example questions  
   - Chat input; render answer, Groww citation link, last-updated footer  
   - Browser-memory only (no transcript persistence)  
   - `src/ui/app.py`
3. **Run scripts**
   - `uvicorn src.api.main:app --reload`  
   - `streamlit run src/ui/app.py`  
   - Document both in README
4. **Smoke E2E**
   - Manual script: UI/API → factual answer + advisory refusal

### Example questions (suggested)

1. What is the expense ratio of HDFC Large Cap Fund Direct Growth?  
2. What is the exit load for HDFC Mid Cap Fund Direct Growth?  
3. What is the lock-in period for HDFC ELSS Tax Saver Fund?

### Deliverables

- Running API + UI  
- UX elements required by the problem statement

### Acceptance criteria

- [ ] Welcome + 3 examples + always-visible disclaimer  
- [ ] Factual ask returns cited Groww answer in UI  
- [ ] Advisory ask shows polite refusal + educational link  
- [ ] No login, no PII collection fields  

### Estimated effort

1–1.5 days

---

## Phase 5 — Hardening, docs & demo readiness

**Objective:** Make the project evaluable, reproducible, and honest about limits. (Architecture §10–11)

### Tasks

1. **Test suite completion**
   - Guardrails, format, retrieval, optional Groq integration tests  
   - CI-friendly: unit tests run without Groq; integration tests skip if `GROQ_API_KEY` missing
2. **README (deliverable)**
   - Setup (venv, `.env`, Groq key)  
   - Selected AMC + schemes + Groww citation URLs  
   - Architecture overview (link to `Architecture.md`) + Groq role  
   - Ingest + run instructions  
   - Known limitations (Architecture §11)  
   - Disclaimer snippet
3. **Re-ingest playbook (manual)**
   - How to refresh Groww scheme pages when numbers change (same steps as P6, run locally)  
   - Reminder that footer date tracks page as-of / ingest metadata, not live market data  
   - Point to **P6** for the automated daily schedule
4. **Eval pass**
   - Manual checklist from Architecture §10.2  
   - Fix citation domain leaks (must be one of the five Groww URLs), verbose answers, weak refusals
5. **Optional polish**
   - Basic latency logging (intent, scheme_id, ms) without raw PII  
   - Docker Compose (api + ui) if time permits — not required for v1

### Deliverables

- Complete README  
- Test suite green (unit)  
- Demo script / sample questions list  

### Acceptance criteria

- [ ] New developer can run ingest (or use checked-in index) + API + UI from README alone  
- [ ] Success criteria from problem statement demonstrable in a walkthrough  
- [ ] Known limitations documented (narrow Groww corpus, stale risk, AMFI/SEBI not in retrieval, HTML layout dependency, etc.)  

### Estimated effort

1–2 days

---

## Phase 6 — Daily ingest scheduler (GitHub Actions)

**Objective:** Run the full offline ingest pipeline on a fixed daily schedule so NAV, expense ratios, exit loads, and other Groww page facts stay current without manual re-ingest. (Architecture §12 optional scheduled re-ingest; extends P1 ingest CLI.)

### Why GitHub Actions

- No extra host or cron daemon to operate for v1  
- Version-controlled workflow next to the ingest code it runs  
- Built-in logs, failure notifications (repo watch / email), and manual `workflow_dispatch` for on-demand refresh  
- Groq is **not** required on this path — only fetch, parse, chunk, local MiniLM embed, and Chroma upsert

### Pipeline (daily run)

Run the same sequence documented in README / P1, end to end:

| Step | Module | Purpose |
|------|--------|---------|
| 1. Fetch | `python -m src.ingest.fetch` | Scrape (or refresh) the five allowlisted Groww scheme HTML pages → `data/raw/{scheme_id}/` |
| 2. Parse | `python -m src.ingest.parse` | Normalize HTML → `data/processed/{scheme_id}/scheme_page.txt` + `parse_manifest.json` |
| 3. Chunk | `python -m src.ingest.run --chunk` | Fact-atom chunking → `data/processed/chunks.jsonl` |
| 4. Embed + upsert | `python -m src.ingest.run --rebuild` | MiniLM embeddings → Chroma collection `groww_scheme_facts` under `CHROMA_PATH` |
| 5. Gate | `python -m src.ingest.retrieve_check` | Offline probe table must pass (P1 acceptance); fail the job if rank-1 sections regress |

Optional wrapper: `scripts/daily_ingest.sh` (or `python -m src.ingest.pipeline`) that chains the five steps and exits non-zero on any failure — keeps the workflow YAML thin.

### Tasks

1. **Scheduled workflow**
   - Add `.github/workflows/daily-ingest.yml`  
   - Trigger: `schedule` cron (e.g. `0 2 * * *` UTC — adjust to IST off-peak after Groww NAV publish window)  
   - Trigger: `workflow_dispatch` for manual runs  
   - `permissions: contents: read` unless publishing artifacts/commits
2. **Job environment**
   - `ubuntu-latest`, Python 3.11+  
   - Cache pip / Hugging Face model download for `all-MiniLM-L6-v2` (first run is slow)  
   - Env from workflow: `CHROMA_PATH`, `EMBEDDING_MODEL` (no `GROQ_API_KEY` on this job)
3. **Groww fetch resilience**
   - Respect existing `fetch.py` checksum + manifest behaviour  
   - On HTTP block / empty HTML: fail the job with a clear log line (do not silently index stale raw files)  
   - Document `--offline` fallback for local recovery only — scheduled job should **not** use offline mode by default
4. **Post-ingest validation**
   - Run `retrieve_check` (and optionally `pytest tests/test_retrieval_facts.py -m "not integration"`) as a hard gate  
   - Assert Chroma `count()` matches expected atom count (46 in current snapshot; allow manifest-driven expected count if layout changes)  
   - Assert every `citation_url` remains one of the five Groww allowlist URLs
5. **Publish updated index**
   - Choose one v1 strategy and document in README:
     - **A — Artifact:** upload `data/processed/chroma/` (+ optional `chunks.jsonl`) as a GitHub Actions artifact; deployment job or host pulls latest artifact before API start  
     - **B — Git LFS / committed processed outputs:** commit `chunks.jsonl` + Chroma dir on success (noisy; only if team accepts binary churn)  
     - **C — Remote volume:** workflow SSH/rsync or cloud CLI syncs `CHROMA_PATH` to the machine/container serving the API  
   - Recommended for demo: **A or C** — keep git history free of large binary churn
6. **Failure alerting**
   - Workflow `concurrency` group (e.g. `daily-ingest`) so overlapping runs cancel or queue  
   - On failure: GitHub notification; optional step to open a GitHub Issue with log excerpt (no PII)  
   - Success summary job output: ingest timestamp, Chroma count, min/max `published_or_as_of` across chunks
7. **Docs**
   - README section: “Daily refresh”, cron time, how deployed API picks up new index  
   - Cross-link from P5 re-ingest playbook

### Workflow sketch

```yaml
name: Daily ingest

on:
  schedule:
    - cron: "0 2 * * *"   # 02:00 UTC daily — tune for IST / NAV window
  workflow_dispatch:

concurrency:
  group: daily-ingest
  cancel-in-progress: false

jobs:
  ingest:
    runs-on: ubuntu-latest
    steps:
      - uses: actions/checkout@v4
      - uses: actions/setup-python@v5
        with:
          python-version: "3.11"
          cache: pip
      - run: pip install -r requirements.txt
      - run: python -m src.ingest.fetch
      - run: python -m src.ingest.parse
      - run: python -m src.ingest.run --chunk --rebuild
      - run: python -m src.ingest.retrieve_check
      - run: pytest tests/test_retrieval_facts.py -m "not integration" --tb=short
      # - publish chroma artifact or sync to deployment target (see task 5)
```

### Deliverables

- `.github/workflows/daily-ingest.yml` (and optional `scripts/daily_ingest.sh`)  
- Documented publish strategy for updated Chroma + processed corpus  
- README “Daily refresh” section  
- At least one successful scheduled or manual `workflow_dispatch` run logged in Actions

### Acceptance criteria

- [ ] Workflow runs on cron without manual intervention  
- [ ] Each successful run executes fetch → parse → chunk → embed/upsert → `retrieve_check`  
- [ ] Failed fetch, parse, chunk, embed, or probe regression fails the workflow (no partial silent success)  
- [ ] Updated Chroma is available to the serving environment per the chosen publish strategy  
- [ ] `published_or_as_of` / `ingested_at` metadata advances when Groww NAV date changes  
- [ ] No secrets required beyond what fetch needs (none for v1); `GROQ_API_KEY` not used on this job  
- [ ] Manual re-ingest playbook (P5) and automated schedule (P6) stay in sync — same commands, same gates

### Estimated effort

0.5–1 day (workflow + artifact/sync wiring; add 0.5 day if deployment hook to a live host is non-trivial)

---

## Cross-cutting conventions

### Groq usage policy

| Call site | Model env var | Temperature | Purpose |
|-----------|---------------|-------------|---------|
| Intent classify | `GROQ_CLASSIFY_MODEL` | ≤0.2 | JSON intent label only |
| Answer generate | `GROQ_CHAT_MODEL` | ≤0.2 | ≤3-sentence grounded fact answer |
| Embeddings | *(local)* | n/a | Never send corpus bulk-embed through Groq |

- Cap `max_tokens` on answers to discourage long outputs.  
- On Groq API errors: return a safe error message; do not bypass guardrails.  
- Do not stream advisory content; refusals are template-based and can skip Groq entirely when rules match.

### Privacy

- No persistence of chat logs by default  
- PII path: classify/refuse without writing user text to disk  
- Log only coarse metadata (intent, scheme_id, latency, status)

### Response contract (every path)

```text
Status: answered | refused | redirected
Body: ≤3 sentences (answered) or polite refusal/redirect copy
Source: exactly one Groww scheme URL when answered
        (AMFI/SEBI education URL on refuse; Groww scheme URL on performance redirect)
Footer: Last updated from sources: <YYYY-MM-DD>
Disclaimer: Facts-only. No investment advice.
```

Formatter shape for answered (Architecture §4.7):

```text
<1–3 factual sentences>

Source: <groww_scheme_url>
Last updated from sources: <YYYY-MM-DD>
```

---

## Milestone checklist (demo day)

- [ ] Five HDFC schemes searchable from the Groww corpus  
- [ ] Groq-powered factual answers with one allowlisted Groww citation + last-updated footer  
- [ ] Advisory / “which is better” politely refused with AMFI/SEBI link  
- [ ] Performance comparison does not compute returns (redirect to Groww scheme page)  
- [ ] PII-like input refused  
- [ ] Streamlit UI: welcome, 3 examples, visible disclaimer  
- [ ] README explains setup with `GROQ_API_KEY`  
- [ ] Daily ingest workflow refreshes Groww corpus (P6)

---

## Suggested calendar (compact)

| Day | Focus |
|-----|--------|
| Day 1 | P0 + start P1 Groww allowlist/fetch |
| Day 2–3 | P1 ingest/index + retrieval checks |
| Day 4 | P2 guardrails + tests |
| Day 5–6 | P3 RAG + golden Q&A |
| Day 7 | P4 API + Streamlit UI |
| Day 8 | P5 README, eval, demo dry-run |
| Day 9 | P6 GitHub Actions daily ingest + publish wiring |

Adjust up if Groww HTML parsing or bot-block workarounds are slow (common on P1). P6 can start once P1 `retrieve_check` passes, even if P4/P5 are still in flight.

---

## Out of scope for v1 (do not schedule)

- User accounts, portfolios, KYC, OTP flows  
- Multi-AMC expansion beyond the five HDFC schemes on Groww  
- Return calculators, fund “scoring”, or recommendation engines  
- Citing aggregators **other than** the five allowlisted Groww scheme URLs  
- Indexing AMC factsheets / SID / KIM as scheme-fact sources (Architecture: Groww-only corpus)  
- Fine-tuning models on Groq  

---

## Summary

Implement in seven phases: **foundation + Groq smoke test → Groww corpus/index → guardrails → Groq RAG orchestration → FastAPI/Streamlit UI → harden & document → daily GitHub Actions ingest**. Groq is used only for **intent classification** and **grounded answer generation**; embeddings stay local and **citations are metadata-owned Groww URLs** so the product remains facts-only, citeable, and aligned with [`Architecture.md`](./Architecture.md). **P6** keeps the Chroma index fresh by re-running scrape → normalize → chunk → embed → upsert on a daily schedule.
