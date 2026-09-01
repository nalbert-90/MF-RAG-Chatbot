from pathlib import Path
from typing import Any

import yaml

from src.config import REGISTRY_DIR


def load_yaml(name: str) -> dict[str, Any]:
    path = REGISTRY_DIR / name
    with path.open(encoding="utf-8") as handle:
        return yaml.safe_load(handle)


def load_schemes() -> list[dict[str, Any]]:
    data = load_yaml("schemes.yaml")
    return data.get("schemes", [])


def load_sources_allowlist() -> dict[str, Any]:
    return load_yaml("sources_allowlist.yaml")


def load_educational_links() -> dict[str, Any]:
    return load_yaml("educational_links.yaml")
