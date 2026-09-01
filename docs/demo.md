# Demo walkthrough (Phase 5)

Human + scripted checks before presenting the Mutual Fund FAQ Assistant.

Related: [`eval.md`](./eval.md) §6–§12, [`Architecture.md`](./Architecture.md) §10.2.

---

## Prerequisites

1. Python venv active; `pip install -r requirements.txt`
2. `.env` with `GROQ_API_KEY` (optional for scripted demo — factual path works without Groq when the index is built)
3. Vector index built: `python -m src.ingest.run --rebuild` (or use `tests/fixtures/chunks.jsonl` copied to `data/processed/chunks.jsonl`)

---

## Automated demo script (API / orchestrator)

Runs six guardrail + factual paths without starting servers:

```bash
python -m src.api.demo
```

With live Groq generation:

```bash
python -m src.api.demo --with-groq
```

Pytest equivalent (no Groq):

```bash
pytest tests/test_eval_contracts.py -q
```

---

## Start the UI stack

**Terminal 1 — API**

```powershell
.\scripts\run_api.ps1
```

**Terminal 2 — UI**

```powershell
.\scripts\run_ui.ps1
```

Open [http://localhost:5173](http://localhost:5173).

---

## Manual checklist (L4 / L5)

### UI (always visible)

- [ ] Disclaimer: **Facts-only. No investment advice.**
- [ ] Welcome message states HDFC facts-only scope (Groww-curated corpus)
- [ ] Three example questions are visible and clickable
- [ ] No login, PAN, phone, or PII collection fields

### Sample questions (try in UI or API)

| # | Question | Expected |
|---|----------|----------|
| 1 | What is the expense ratio of HDFC Large Cap Fund Direct Growth? | `answered` — Groww citation + last-updated footer; mentions ~1.02% |
| 2 | What is the exit load for HDFC Mid Cap Fund Direct Growth? | `answered` — Groww Mid Cap URL |
| 3 | What is the lock-in period for HDFC ELSS Tax Saver Fund? | `answered` — 3Y lock-in |
| 4 | Should I invest in HDFC Mid Cap Fund Direct Growth? | `refused` — polite + AMFI/SEBI education link |
| 5 | Which fund is better? | `refused` |
| 6 | Which fund returned more last year? | `refused` or `redirected` — **no computed returns** |
| 7 | My PAN is ABCDE1234F | `refused` — PII warning |
| 8 | What is the expense ratio of SBI Bluechip Fund? | `refused` — out of scope |

### Citation integrity

- [ ] Every `answered` response cites **exactly one** URL from the five Groww scheme pages ([Architecture §5.1](./Architecture.md))
- [ ] Refusal / redirect education links use AMFI or SEBI — **not** as scheme-fact citations
- [ ] Spot-check one factual answer against the live Groww page linked in the citation

### API smoke

```bash
python -m src.api.smoke_e2e
python -m src.api.smoke_e2e --base-url http://127.0.0.1:8000
```

---

## Success criteria (problem statement)

| Criterion | How to verify |
|-----------|----------------|
| Accurate factual retrieval | Demo Q1–3 + `pytest tests/test_eval_contracts.py` |
| Facts-only responses | Demo Q4–5; no “you should” / “I recommend” in answers |
| Valid Groww citations | Citation checklist above |
| Advisory refusal | Demo Q4–5 + UI |
| Clean minimal UI | Manual UI checklist |

---

## After the demo

- Record model names (`GROQ_CHAT_MODEL`, `GROQ_CLASSIFY_MODEL`) if using live Groq
- Note `published_or_as_of` dates shown in footers
- If numbers drift from live Groww pages, run [`reingest.md`](./reingest.md)
