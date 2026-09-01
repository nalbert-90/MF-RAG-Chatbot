import pytest

from src.config import PROJECT_ROOT, get_settings
from src.registry import load_educational_links, load_schemes, load_sources_allowlist


def test_project_layout_exists() -> None:
    expected_dirs = [
        "docs",
        "data/raw",
        "data/processed",
        "data/registry",
        "src/ingest",
        "src/rag",
        "src/guardrails",
        "src/api",
        "src/ui",
        "tests",
    ]
    for relative in expected_dirs:
        assert (PROJECT_ROOT / relative).is_dir(), f"Missing directory: {relative}"


def test_gitignore_excludes_secrets() -> None:
    content = (PROJECT_ROOT / ".gitignore").read_text(encoding="utf-8")
    assert ".env" in content.splitlines() or any(
        line.strip() == ".env" for line in content.splitlines()
    )


def test_env_example_documents_required_vars() -> None:
    content = (PROJECT_ROOT / ".env.example").read_text(encoding="utf-8")
    for var in (
        "GROQ_API_KEY",
        "GROQ_CHAT_MODEL",
        "GROQ_CLASSIFY_MODEL",
        "CHROMA_PATH",
        "EMBEDDING_MODEL",
    ):
        assert var in content


def test_schemes_registry_has_five_groww_urls() -> None:
    schemes = load_schemes()
    assert len(schemes) == 5
    for scheme in schemes:
        assert scheme["scheme_id"]
        assert scheme["groww_url"].startswith("https://groww.in/mutual-funds/")


def test_sources_allowlist_matches_schemes() -> None:
    schemes = {s["scheme_id"] for s in load_schemes()}
    allowlist = load_sources_allowlist()
    source_ids = {entry["scheme_id"] for entry in allowlist["sources"]}
    assert schemes == source_ids
    assert allowlist["allowed_domains"] == ["groww.in"]
    for entry in allowlist["sources"]:
        assert entry["citation_url"].startswith("https://groww.in/mutual-funds/")
        assert entry["source_org"] == "groww"
        assert entry["doc_type"] == "scheme_page"


def test_educational_links_present() -> None:
    links = load_educational_links()
    assert links["default_refusal_link"]
    assert len(links["educational_links"]) >= 2


def test_settings_defaults(monkeypatch: pytest.MonkeyPatch) -> None:
    from src.config import Settings

    monkeypatch.delenv("GROQ_CHAT_MODEL", raising=False)
    monkeypatch.delenv("GROQ_CLASSIFY_MODEL", raising=False)
    settings = Settings(
        groq_api_key="",
        _env_file=None,
    )
    assert settings.groq_chat_model == "qwen/qwen3.6-27b"
    assert settings.groq_classify_model == "openai/gpt-oss-20b"
    assert settings.embedding_model == "all-MiniLM-L6-v2"
    assert settings.chroma_path == "data/processed/chroma"
    get_settings.cache_clear()
