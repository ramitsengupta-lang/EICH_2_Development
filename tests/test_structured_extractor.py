from __future__ import annotations

from datetime import date, datetime

from contracts.source_ref import SourceRef
from contracts.validated_data import RecordState
from m3_structured_extractor.structured_extractor import extract


def _source_ref(method: str = "pdf_parse") -> SourceRef:
    return SourceRef(
        source_id="src-1",
        source_name="registry",
        source_tier="official",
        extraction_method=method,
        document_date=date(2026, 1, 1),
        fetched_at=datetime(2026, 1, 2),
        url="https://example.org",
    )


def test_extract_returns_validated_entity_for_identifiable_payload() -> None:
    raw_input = {
        "entity_id": "E1",
        "entity_name": "Entity One",
        "entity_type": "UNIVERSITY",
        "jurisdiction": "IN",
        "kmp_records": [
            {
                "kmp_id": "K1",
                "full_name": "Jane Doe",
                "canonical_role": "Principal",
                "raw_role": "Principal",
                "last_observed_date": "2026-01-01",
            }
        ],
        "compensation_records": [
            {
                "kmp_id": "K1",
                "year": 2025,
                "compensation_value": 1200000,
                "currency": "INR",
            }
        ],
    }

    # source_ref intentionally starts non-structured; extractor must enforce structured
    records = extract(raw_input, _source_ref("pdf_parse"))

    assert len(records) == 1
    entity = records[0]
    assert entity.entity_id == "E1"
    assert entity.state == RecordState.VALIDATED
    assert len(entity.kmp_list) == 1
    assert entity.kmp_list[0].compensation[0].year == 2025

    # All entity field sources must be structured
    assert all(src.extraction_method == "structured" for src in entity.field_sources.values())



def test_extract_missing_required_fields_marks_partial_not_quarantined() -> None:
    raw_input = {
        "entity_id": "E2",
        "entity_name": "Entity Two",
        # missing entity_type and jurisdiction
    }

    records = extract(raw_input, _source_ref("structured"))

    assert len(records) == 1
    entity = records[0]
    assert entity.state == RecordState.PARTIAL
    assert entity.state != RecordState.QUARANTINED
    assert len(entity.quality_warnings) == 2



def test_extract_returns_one_record_per_identifiable_entity() -> None:
    raw_input = {
        "entities": [
            {
                "entity_id": "E10",
                "entity_name": "Alpha Institute",
                "entity_type": "UNIVERSITY",
                "jurisdiction": "IN",
            },
            {
                "entity_name": "Beta School",
                "entity_type": "SCHOOL",
                "jurisdiction": "IN",
            },
            {
                # not identifiable: no entity_id/entity_name
                "entity_type": "COLLEGE",
                "jurisdiction": "IN",
            },
        ]
    }

    records = extract(raw_input, _source_ref())

    assert len(records) == 2
    assert [record.entity_id for record in records] == ["E10", "BETASCHOOL"]
    assert all(record.state in {RecordState.VALIDATED, RecordState.PARTIAL} for record in records)
