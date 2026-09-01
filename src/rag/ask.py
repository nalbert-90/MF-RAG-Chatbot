"""CLI entry point for end-to-end factual Q&A."""

from __future__ import annotations

import argparse
import json
import sys

from src.rag.groq_client import GroqClient
from src.rag.models import AskResponse
from src.rag.orchestrator import ask


def _print_response(response: AskResponse) -> None:
    payload = response.to_dict()
    print(json.dumps(payload, indent=2, ensure_ascii=False))
    print()
    if response.status == "answered" and response.citation_url:
        print(f"Source: {response.citation_url}")
    if response.last_updated:
        print(f"Last updated from sources: {response.last_updated}")
    print(response.disclaimer)


def _parse_args(argv: list[str] | None = None) -> argparse.Namespace:
    parser = argparse.ArgumentParser(
        description="Ask a factual question about curated HDFC Groww scheme pages."
    )
    parser.add_argument("question", nargs="+", help="Natural-language question")
    parser.add_argument(
        "--no-groq",
        action="store_true",
        help="Skip Groq generation; use deterministic fallback from retrieval.",
    )
    return parser.parse_args(argv)


def main(argv: list[str] | None = None) -> int:
    args = _parse_args(argv)
    question = " ".join(args.question).strip()
    if not question:
        print("Question must not be empty.", file=sys.stderr)
        return 1

    groq_client = None
    use_groq = not args.no_groq
    if use_groq:
        try:
            groq_client = GroqClient()
        except ValueError as exc:
            print(exc, file=sys.stderr)
            return 1

    response = ask(question, groq_client=groq_client, use_groq=use_groq)
    _print_response(response)
    return 0


if __name__ == "__main__":
    sys.exit(main())
