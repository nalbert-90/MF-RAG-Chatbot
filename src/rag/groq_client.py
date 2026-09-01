from typing import Any

from groq import Groq

from src.config import get_settings
from src.rag.output_sanitize import sanitize_model_output


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
    ) -> str:
        response = self._client.chat.completions.create(
            model=model or self._settings.groq_chat_model,
            messages=messages,
            temperature=(
                temperature
                if temperature is not None
                else self._settings.groq_chat_temperature
            ),
            max_tokens=max_tokens or self._settings.groq_chat_max_tokens,
        )
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
        )


def get_groq_client() -> GroqClient:
    return GroqClient()
