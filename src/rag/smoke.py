"""Groq connectivity smoke test.

Usage:
    python -m src.rag.smoke
"""

from src.rag.groq_client import GroqClient


def main() -> None:
    client = GroqClient()
    reply = client.chat(
        [
            {"role": "system", "content": "Reply with exactly one word: pong"},
            {"role": "user", "content": "ping"},
        ],
        max_tokens=16,
        temperature=0.0,
    )
    print(reply)


if __name__ == "__main__":
    main()
