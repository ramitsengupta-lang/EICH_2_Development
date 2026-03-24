from __future__ import annotations

from datetime import date, datetime

from contracts.score_data import ScoreData
from contracts.source_ref import SourceRef
from contracts.validated_data import CompensationRecord, KMPRecord, RecordState, ValidatedEntityRecord
from m8_report_builder.report_builder import build_report


def _source_ref() -> SourceRef:
    return SourceRef(
        source_id="src-1",
        source_name="example.org",
        source_tier="official",
        extraction_method="structured",
        document_date=date(2026, 1, 1),
        fetched_at=datetime(2026, 1, 2),
        url="https://example.org/source",
    )


def _validated_entity() -> ValidatedEntityRecord:
    src = _source_ref()
    compensation = CompensationRecord(
        kmp_id="K1",
        year=2025,
        compensation_value=1000000.0,
        currency="INR",
        field_sources={"compensation_value": src, "currency": src},
        evidence_sentence="Compensation listed in filing.",
    )
    kmp = KMPRecord(
        kmp_id="K1",
        full_name="Jane Doe",
        canonical_role="Principal",
        raw_role="Principal",
        field_sources={"full_name": src, "canonical_role": src, "raw_role": src},
        staleness_flag=False,
        last_observed_date=date(2026, 1, 1),
        compensation=[compensation],
        state=RecordState.VALIDATED,
    )
    return ValidatedEntityRecord(
        entity_id="E1",
        entity_name="Entity One",
        entity_type="Institution",
        jurisdiction="IN",
        kmp_list=[kmp],
        associated_entities=[],
        relationship_map=[],
        institution_network=[],
        field_sources={"entity_name": src},
        quality_warnings=[],
        state=RecordState.VALIDATED,
        pipeline_run_id="run-smoke",
    )


def _score_data() -> ScoreData:
    return ScoreData(
        pipeline_run_id="run-smoke",
        entity_id="E1",
        final_score=88.0,
        score_explanation=["Smoke test score explanation"],
        contributing_fields={"financial_strength_score": "kmp_list[].compensation[].compensation_value"},
        rating="A",
    )


def test_smoke_e2e_build_report_returns_required_top_level_sections() -> None:
    entity = _validated_entity()
    score = _score_data()

    report = build_report(entity, score)

    assert isinstance(report, dict)
    assert "header" in report
    assert "eich_score_summary" in report
    assert "report_accuracy" in report
