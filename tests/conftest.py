import os
from pathlib import Path

import pytest
from dotenv import load_dotenv

load_dotenv(Path(__file__).resolve().parents[1] / ".env")


def pytest_configure(config: pytest.Config) -> None:
    config.addinivalue_line(
        "markers",
        "integration: tests that call the live Groq API (require GROQ_API_KEY).",
    )


def groq_api_key_configured() -> bool:
    if os.getenv("GROQ_API_KEY", "").strip():
        return True
    try:
        from src.config import get_settings

        return bool(get_settings().groq_api_key.strip())
    except Exception:
        return False
