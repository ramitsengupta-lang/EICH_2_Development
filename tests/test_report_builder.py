from __future__ import annotations

from datetime import date, datetime

import pytest

from contracts.score_data import ScoreData
from contracts.source_ref import SourceRef
from contracts.validated_data import CompensationRecord, KMPRecord, RecordState, ValidatedEntityRecord
from m8_report_builder.report_builder import build_report


def _src() -> SourceRef:
    return SourceRef(
        source_id="s1",
        source_name="source",
        source_tier="official",
        extraction_method="structured",
        document_date=date(2026, 1, 1),
        fetched_at=datetime(2026, 1, 2),
        url="https://example.org",
    )


def _entity(state: RecordState = RecordState.VALIDATED) -> ValidatedEntityRecord:
    src = _src()
    comp = CompensationRecord(
        kmp_id="K1",
        year=2025,
        compensation_value=1000000.0,
        currency="INR",
        field_sources={"compensation_value": src, "currency": src},
        evidence_sentence="Compensation from annual filing.",
    )
    kmp = KMPRecord(
        kmp_id="K1",
        full_name="Jane Doe",
        canonical_role="Principal",
        raw_role="Principal",
        field_sources={"full_name": src, "canonical_role": src, "raw_role": src},
        staleness_flag=False,
        last_observed_date=date(2026, 1, 1),
        compensation=[comp],
        state=state,
    )
    return ValidatedEntityRecord(
        entity_id="E1",
        entity_name="Entity One",
        entity_type="UNIVERSITY",
        jurisdiction="IN",
        kmp_list=[kmp],
        associated_entities=[],
        relationship_map=[],
        institution_network=[],
        field_sources={"entity_name": src},
        quality_warnings=["VAL_KMP_PROVENANCE_MISSING|kmp_list[0]|missing provenance"] if state == RecordState.PARTIAL else [],
        state=state,
        pipeline_run_id="run-1",
    )


def _score() -> ScoreData:
    return ScoreData(
        pipeline_run_id="run-1",
        entity_id="E1",
        final_score=84.5,
        score_explanation=["Financial data complete", "Leadership data mostly complete"],
        contributing_fields={
            "financial_strength_score": "kmp_list[].compensation[].compensation_value",
            "outcome_strength_score": "kmp_list[].canonical_role",
        },
        rating="A",
    )


def test_build_report_raises_for_quarantined_entity() -> None:
    entity = _entity(RecordState.QUARANTINED)
    score = _score()

    with pytest.raises(ValueError, match="QUARANTINED"):
        build_report(entity, score)


def test_build_report_success_contains_expected_sections() -> None:
    entity = _entity(RecordState.VALIDATED)
    score = _score()

    report = build_report(entity, score)

    assert report["pipeline_run_id"] == "run-1"
    assert report["entity_id"] == "E1"
    assert report["status"] == "success"
    assert report["entity"]["entity_name"] == "Entity One"
    assert report["kmp_summary"]["kmp_count"] == 1
    assert report["kmp_summary"]["compensation_record_count"] == 1
    assert report["score_summary"]["final_score"] == 84.5
    assert report["score_summary"]["contributing_fields"]["financial_strength_score"] == "kmp_list[].compensation[].compensation_value"
    assert report["sections"]["partial_data_warning"] is None


def test_build_report_partial_includes_partial_warning() -> None:
    entity = _entity(RecordState.PARTIAL)
    score = _score()

    report = build_report(entity, score)

    assert report["status"] == "partial"
    assert report["quality"]["state"] == "PARTIAL"
    warning = report["sections"]["partial_data_warning"]
    assert warning is not None
    assert warning["title"] == "Partial Data Notice"
    assert len(warning["warnings"]) == 1
