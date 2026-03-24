from __future__ import annotations

import hashlib

from m1_identifier.identifier import identify


def test_identify_normalizes_fields() -> None:
    raw_input = {
        "entity_name": "  alpha education trust  ",
        "entity_type": "trust",
        "jurisdiction": "maharashtra",
    }

    result = identify(raw_input)

    assert result["entity_name"] == "Alpha Education Trust"
    assert result["entity_type"] == "Trust"
    assert result["jurisdiction"] == "MAHARASHTRA"
    assert result["_identified"] is True


def test_identify_generates_deterministic_entity_id_when_missing() -> None:
    raw_input = {
        "entity_name": "Entity One",
        "entity_type": "institution",
        "jurisdiction": "Karnataka",
    }

    result = identify(raw_input)

    expected = hashlib.sha256("Entity OneKARNATAKA".encode("utf-8")).hexdigest()[:16]
    assert result["entity_id"] == expected


def test_identify_preserves_existing_entity_id() -> None:
    raw_input = {
        "entity_id": "EXISTING-ID-123",
        "entity_name": "  beta college ",
        "entity_type": "university",
        "jurisdiction": "tamil nadu",
    }

    result = identify(raw_input)

    assert result["entity_id"] == "EXISTING-ID-123"
    assert result["entity_name"] == "Beta College"
    assert result["entity_type"] == "Institution"
    assert result["jurisdiction"] == "TAMIL NADU"
    assert result["_identified"] is True
