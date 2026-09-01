"""Groq-backed grounded answer generation."""

from __future__ import annotations

from typing import Any

from src.rag.prompts import build_answer_messages
from src.rag.retriever import RetrievalHit


def generate_answer(
    question: str,
    hits: list[RetrievalHit],
    groq_client: Any,
    *,
    strict_retry: bool = False,
) -> str:
    messages = build_answer_messages(
        question,
        hits,
        strict_retry=strict_retry,
    )
    return groq_client.chat(messages)
