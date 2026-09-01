from functools import lru_cache
from pathlib import Path

from dotenv import load_dotenv
from pydantic_settings import BaseSettings, SettingsConfigDict

PROJECT_ROOT = Path(__file__).resolve().parent.parent
REGISTRY_DIR = PROJECT_ROOT / "data" / "registry"

load_dotenv(PROJECT_ROOT / ".env")


class Settings(BaseSettings):
    model_config = SettingsConfigDict(
        env_file=str(PROJECT_ROOT / ".env"),
        env_file_encoding="utf-8",
        extra="ignore",
    )

    groq_api_key: str = ""
    groq_chat_model: str = "qwen/qwen3.6-27b"
    groq_classify_model: str = "openai/gpt-oss-20b"
    chroma_path: str = "data/processed/chroma"
    embedding_model: str = "all-MiniLM-L6-v2"
    groq_chat_temperature: float = 0.1
    groq_classify_temperature: float = 0.2
    groq_chat_max_tokens: int = 256
    retrieval_max_distance: float = 1.15
    retrieval_top_k: int = 3

    @property
    def chroma_path_resolved(self) -> Path:
        path = Path(self.chroma_path)
        if not path.is_absolute():
            path = PROJECT_ROOT / path
        return path


@lru_cache
def get_settings() -> Settings:
    return Settings()
