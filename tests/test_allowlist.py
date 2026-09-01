from src.ingest.allowlist import (
    is_allowlisted_citation_url,
    normalize_citation_url,
    validate_allowlist,
)
from src.registry import load_educational_links, load_schemes, load_sources_allowlist


def test_validate_allowlist_passes() -> None:
    sources = validate_allowlist()
    assert len(sources) == 5


def test_allowlist_is_exactly_five_groww_urls() -> None:
    schemes = load_schemes()
    sources = load_sources_allowlist()["sources"]
    scheme_urls = {s["scheme_id"]: normalize_citation_url(s["groww_url"]) for s in schemes}
    for source in sources:
        assert is_allowlisted_citation_url(source["citation_url"])
        assert scheme_urls[source["scheme_id"]] == normalize_citation_url(
            source["citation_url"]
        )


def test_educational_links_are_not_citation_urls() -> None:
    edu = load_educational_links()
    for link in edu["educational_links"]:
        assert not is_allowlisted_citation_url(link["url"])
    assert not is_allowlisted_citation_url(edu["default_refusal_link"])


def test_excluded_hosts_rejected() -> None:
    banned = [
        "https://www.hdfcfund.com/mutual-fund/hdfc-large-cap-fund",
        "https://www.moneycontrol.com/mutual-funds/hdfc-large-cap",
        "https://www.amfiindia.com/investor-corner",
        "https://groww.in/mutual-funds/some-other-fund",
        "https://www.valueresearchonline.com/funds/123",
    ]
    for url in banned:
        assert not is_allowlisted_citation_url(url)
