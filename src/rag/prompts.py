"""Grounded answer prompt templates for Groq generation."""

from __future__ import annotations

from src.rag.retriever import RetrievalHit

ANSWER_SYSTEM_PROMPT = """You are a facts-only mutual fund FAQ assistant.
Answer using ONLY the provided context snippets from curated Groww scheme pages.
Rules:
- Write only the factual answer in plain sentences (for example: "The expense ratio is 1.02%.").
- Maximum 3 short sentences.
- No investment advice, recommendations, comparisons, or return calculations.
- Do not invent numbers, dates, or URLs.
- If the context does not contain the answer, reply exactly: I do not have that fact in the curated sources.
- Use plain language suitable for retail investors.
- Do not include a Source line or footer — the system adds those."""

STRICT_RETRY_SUFFIX = (
    "\n\nImportant: Your previous answer was invalid. "
    "Answer in at most 3 sentences using ONLY the context. "
    "No advice phrases. If the fact is missing, say you do not have it in the curated sources."
)


def format_context_block(hits: list[RetrievalHit]) -> str:
    lines: list[str] = []
    for hit in hits:
        lines.append(
            f"- [{hit.section}] (as of {hit.published_or_as_of}) {hit.text}"
        )
    return "\n".join(lines)


def build_answer_messages(
    question: str,
    hits: list[RetrievalHit],
    *,
    strict_retry: bool = False,
) -> list[dict[str, str]]:
    context = format_context_block(hits)
    user_content = (
        f"Question: {question.strip()}\n\n"
        f"Context:\n{context}\n\n"
        "Answer the question using only the context above."
    )
    if strict_retry:
        user_content += STRICT_RETRY_SUFFIX

    return [
        {"role": "system", "content": ANSWER_SYSTEM_PROMPT},
        {"role": "user", "content": user_content},
    ]
