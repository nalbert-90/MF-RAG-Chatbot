"""Phase 5 demo walkthrough: factual answer + guardrail refusals (no Groq required).

Usage:
    python -m src.api.demo
    python -m src.api.demo --with-groq
"""

from __future__ import annotations

import argparse
import sys
from dataclasses import dataclass
from pathlib import Path

from src.guardrails.scheme_resolver import resolve_scheme_id
from src.ingest.chunk import CHUNKS_PATH
from src.ingest.embed_index import IndexNotReadyError, embed_index, open_index
from src.rag.groq_client import GroqClient
from src.rag.models import AskResponse
from src.rag.orchestrator import ask

FIXTURE_CHUNKS = Path(__file__).resolve().parents[2] / "tests" / "fixtures" / "chunks.jsonl"


@dataclass(frozen=True)
class DemoStep:
    step: int
    label: str
    question: str
    expected_status: str
    must_include_any: tuple[str, ...] = ()


DEMO_STEPS: tuple[DemoStep, ...] = (
    DemoStep(
        1,
        "Factual — expense ratio (example question 1)",
        "What is the expense ratio of HDFC Large Cap Fund Direct Growth?",
        "answered",
        ("1.02",),
    ),
    DemoStep(
        2,
        "Advisory — should I invest",
        "Should I invest in HDFC Mid Cap Fund Direct Growth?",
        "refused",
    ),
    DemoStep(
        3,
        "Advisory — which is better",
        "Which fund is better?",
        "refused",
    ),
    DemoStep(
        4,
        "Performance — return comparison (ambiguous scheme)",
        "Which fund returned more last year?",
        "refused",
    ),
    DemoStep(
        5,
        "PII — PAN in message",
        "My PAN is ABCDE1234F — what is the expense ratio?",
        "refused",
    ),
    DemoStep(
        6,
        "Out of scope — other AMC",
        "What is the expense ratio of SBI Bluechip Fund?",
        "refused",
    ),
)


def _open_collection():
    try:
        return open_index(create=False).collection
    except IndexNotReadyError:
        chunks_path = CHUNKS_PATH if CHUNKS_PATH.is_file() else FIXTURE_CHUNKS
        if not chunks_path.is_file():
            raise
        from src.config import get_settings

        chroma_path = get_settings().chroma_path_resolved
        embed_index(chunks_path=chunks_path, chroma_path=chroma_path, rebuild=True)
        return open_index(chroma_path=chroma_path, create=False).collection


def _check_step(step: DemoStep, response: AskResponse) -> tuple[bool, str]:
    if response.status != step.expected_status:
        return False, f"expected status={step.expected_status!r}, got {response.status!r}"

    lowered = response.answer.lower()

    if step.expected_status == "answered":
        if not response.citation_url or "groww.in" not in response.citation_url:
            return False, "missing Groww citation_url"
        if step.must_include_any and not any(
            token.lower() in lowered for token in step.must_include_any
        ):
            return False, f"answer missing expected tokens {step.must_include_any}"

    if step.step in {2, 3} and "advice" not in lowered and "facts-only" not in lowered:
        return False, "refusal missing facts-only framing"

    if step.step == 5 and "do not share" not in lowered and "sensitive" not in lowered:
        return False, "PII refusal missing safety wording"

    return True, response.answer[:120].replace("\n", " ")


def run_demo(*, use_groq: bool = False) -> list[tuple[DemoStep, bool, str]]:
    collection = _open_collection()
    groq_client = None
    if use_groq:
        groq_client = GroqClient()

    results: list[tuple[DemoStep, bool, str]] = []
    for step in DEMO_STEPS:
        response = ask(
            step.question,
            groq_client=groq_client,
            use_groq=use_groq and groq_client is not None,
            collection=collection,
        )
        ok, detail = _check_step(step, response)
        scheme_id = resolve_scheme_id(step.question)
        status_bits = [f"status={response.status}"]
        if scheme_id:
            status_bits.append(f"scheme_id={scheme_id}")
        if response.citation_url:
            status_bits.append(f"citation={response.citation_url}")
        results.append((step, ok, f"{'; '.join(status_bits)} — {detail}"))
    return results


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(description="Run the Phase 5 demo question set.")
    parser.add_argument(
        "--with-groq",
        action="store_true",
        help="Use live Groq generation (requires GROQ_API_KEY).",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    print("Mutual Fund FAQ Assistant — demo walkthrough")
    print("Facts-only. No investment advice.")
    print("-" * 60)
    print("Manual UI check: open http://localhost:5173 — disclaimer + 3 examples visible.")
    print("-" * 60)

    try:
        results = run_demo(use_groq=args.with_groq)
    except IndexNotReadyError as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        return 1
    except ValueError as exc:
        print(f"FAIL  {exc}", file=sys.stderr)
        return 1

    failed = 0
    for step, ok, detail in results:
        label = "PASS" if ok else "FAIL"
        print(f"{label}  {step.step}. {step.label}")
        print(f"      Q: {step.question}")
        print(f"      {detail}")
        if not ok:
            failed += 1

    print("-" * 60)
    if failed:
        print(f"{failed} demo step(s) failed.", file=sys.stderr)
        return 1
    print("All demo API paths passed.")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
