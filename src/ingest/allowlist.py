"""Groww citation allowlist helpers (Architecture §5.1–5.3)."""

from __future__ import annotations

from urllib.parse import urlparse

from src.registry import load_educational_links, load_schemes, load_sources_allowlist

ALLOWED_CITATION_HOST = "groww.in"
ALLOWED_SOURCE_ORG = "groww"
ALLOWED_DOC_TYPE = "scheme_page"


def normalize_citation_url(url: str) -> str:
    parsed = urlparse((url or "").strip())
    host = parsed.netloc.lower().removeprefix("www.")
    path = parsed.path.rstrip("/")
    return f"https://{host}{path}"


def citation_host(url: str) -> str:
    return urlparse((url or "").strip()).netloc.lower().removeprefix("www.")


def load_allowlisted_sources() -> list[dict]:
    data = load_sources_allowlist()
    return list(data.get("sources") or [])


def allowlisted_citation_urls() -> set[str]:
    return {
        normalize_citation_url(source["citation_url"])
        for source in load_allowlisted_sources()
    }


def excluded_citation_hosts() -> set[str]:
    data = load_sources_allowlist()
    hosts = {
        host.lower().removeprefix("www.")
        for host in data.get("excluded_citation_hosts") or []
    }
    hosts.update(
        citation_host(link["url"])
        for link in load_educational_links().get("educational_links") or []
        if link.get("url")
    )
    return hosts


def is_allowlisted_citation_url(url: str) -> bool:
    if citation_host(url) != ALLOWED_CITATION_HOST:
        return False
    return normalize_citation_url(url) in allowlisted_citation_urls()


def validate_allowlist() -> list[dict]:
    """Raise ValueError if the registry is incomplete or cites a banned host."""
    schemes = load_schemes()
    sources = load_allowlisted_sources()
    data = load_sources_allowlist()

    if data.get("allowed_domains") != [ALLOWED_CITATION_HOST]:
        raise ValueError(
            f"allowed_domains must be [{ALLOWED_CITATION_HOST!r}] only."
        )
    if len(schemes) != 5 or len(sources) != 5:
        raise ValueError("Allowlist must contain exactly five HDFC schemes.")

    scheme_ids = {scheme["scheme_id"] for scheme in schemes}
    source_ids = {source["scheme_id"] for source in sources}
    if scheme_ids != source_ids:
        raise ValueError("schemes.yaml and sources_allowlist.yaml scheme_id sets differ.")

    scheme_urls = {
        scheme["scheme_id"]: normalize_citation_url(scheme["groww_url"])
        for scheme in schemes
    }
    banned = excluded_citation_hosts()

    for source in sources:
        if source.get("source_org") != ALLOWED_SOURCE_ORG:
            raise ValueError(f"{source.get('scheme_id')}: source_org must be groww.")
        if source.get("doc_type") != ALLOWED_DOC_TYPE:
            raise ValueError(f"{source.get('scheme_id')}: doc_type must be scheme_page.")
        url = source.get("citation_url") or ""
        host = citation_host(url)
        if host in banned or host != ALLOWED_CITATION_HOST:
            raise ValueError(
                f"{source.get('scheme_id')}: citation_url host {host!r} is not allowed."
            )
        normalized = normalize_citation_url(url)
        if normalized != scheme_urls[source["scheme_id"]]:
            raise ValueError(
                f"{source['scheme_id']}: citation_url must match schemes.yaml groww_url."
            )
        if not is_allowlisted_citation_url(url):
            raise ValueError(f"{source['scheme_id']}: citation_url is not allowlisted.")

    return sources
