from __future__ import annotations

import hashlib

from m2_source_acquirer.source_acquirer import acquire


def test_acquire_empty_urls_returns_empty_list() -> None:
    result = acquire("E1", [])
    assert result == []


def test_acquire_infers_tier_and_domain_and_structured_method() -> None:
    urls = [
        "https://www.mca.gov.in/filing",
        "https://naac.gov.in/records",
        "https://www.wikipedia.org/wiki/Test",
        "https://example.com/page",
    ]

    refs = acquire("E1", urls)

    assert len(refs) == 4
    assert refs[0].source_tier == "authoritative"
    assert refs[1].source_tier == "official"
    assert refs[2].source_tier == "secondary"
    assert refs[3].source_tier == "web"

    assert all(ref.extraction_method == "structured" for ref in refs)
    assert refs[0].source_name == "www.mca.gov.in"
    assert refs[1].source_name == "naac.gov.in"


def test_acquire_source_id_is_deterministic_sha256_prefix() -> None:
    entity_id = "ENTITY-123"
    url = "https://ugc.ac.in/some-path"

    refs = acquire(entity_id, [url])

    expected_id = hashlib.sha256(f"{entity_id}{url}".encode("utf-8")).hexdigest()[:16]
    assert len(refs) == 1
    assert refs[0].source_id == expected_id
