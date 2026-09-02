from typing import Any

from groq import Groq

from src.config import get_settings
from src.rag.output_sanitize import sanitize_model_output


def _reasoning_kwargs_for_answer(model: str) -> dict[str, str]:
    """Disable Qwen thinking mode for short grounded answers (Groq reasoning API)."""
    name = model.lower()
    if "qwen" in name and ("3.6" in name or "3.8" in name):
        return {"reasoning_effort": "none", "reasoning_format": "hidden"}
    return {}


class GroqClient:
    """Thin wrapper around the official Groq SDK."""

    def __init__(self, api_key: str | None = None) -> None:
        settings = get_settings()
        key = settings.groq_api_key if api_key is None else api_key
        if not key or not str(key).strip():
            raise ValueError(
                "GROQ_API_KEY is missing or empty. Add your key to .env as "
                "GROQ_API_KEY=... and save the file (unsaved editor changes are "
                "not read by the CLI)."
            )
        self._client = Groq(api_key=key.strip())
        self._settings = settings

    def chat(
        self,
        messages: list[dict[str, str]],
        *,
        model: str | None = None,
        temperature: float | None = None,
        max_tokens: int | None = None,
        for_answer: bool = True,
    ) -> str:
        model_name = model or self._settings.groq_chat_model
        create_kwargs: dict[str, Any] = {
            "model": model_name,
            "messages": messages,
            "temperature": (
                temperature
                if temperature is not None
                else self._settings.groq_chat_temperature
            ),
            "max_tokens": max_tokens or self._settings.groq_chat_max_tokens,
        }
        if for_answer:
            create_kwargs.update(_reasoning_kwargs_for_answer(model_name))

        response = self._client.chat.completions.create(**create_kwargs)
        content = response.choices[0].message.content
        if not content or not content.strip():
            raise RuntimeError("Groq returned an empty response.")
        cleaned = sanitize_model_output(content)
        if not cleaned:
            raise RuntimeError("Groq returned only reasoning content with no answer.")
        return cleaned.strip()

    def classify(self, messages: list[dict[str, str]], **kwargs: Any) -> str:
        settings = get_settings()
        return self.chat(
            messages,
            model=kwargs.pop("model", settings.groq_classify_model),
            temperature=kwargs.pop(
                "temperature", settings.groq_classify_temperature
            ),
            max_tokens=kwargs.pop("max_tokens", 64),
            for_answer=False,
        )


def get_groq_client() -> GroqClient:
    return GroqClient()
