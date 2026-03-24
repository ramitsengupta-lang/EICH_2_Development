from __future__ import annotations

from copy import deepcopy
from datetime import date, datetime

import pytest

from contracts.source_ref import SourceRef
from contracts.validated_data import CompensationRecord, KMPRecord, RecordState, ValidatedEntityRecord
from m6_validator.validator import build_scoring_payload, validate_entity_record
from m7_scorer.scorer import score


def _src(source_id: str, tier: str, method: str, doc_date: date) -> SourceRef:
    return SourceRef(
        source_id=source_id,
        source_name=f"src-{source_id}",
        source_tier=tier,
        extraction_method=method,
        document_date=doc_date,
        fetched_at=datetime(2026, 1, 1),
        url=None,
    )


def _comp(kmp_id: str, year: int, value: float | None, src: SourceRef, currency: str = "INR") -> CompensationRecord:
    return CompensationRecord(
        kmp_id=kmp_id,
        year=year,
        compensation_value=value,
        currency=currency,
        field_sources={
            "compensation_value": src,
            "currency": src,
        },
    )


def _entity_with_kmps(kmps: list[KMPRecord], state: RecordState = RecordState.VALIDATED) -> ValidatedEntityRecord:
    return ValidatedEntityRecord(
        entity_id="E1",
        entity_name="Entity One",
        entity_type="UNIVERSITY",
        jurisdiction="IN",
        kmp_list=kmps,
        associated_entities=[],
        relationship_map=[],
        institution_network=[],
        field_sources={"entity_name": _src("e1", "authoritative", "structured", date(2026, 1, 1))},
        quality_warnings=[],
        state=state,
        pipeline_run_id="run-1",
    )


def _kmp(kid: str, role: str, src: SourceRef, comp: list[CompensationRecord], state: RecordState = RecordState.VALIDATED) -> KMPRecord:
    return KMPRecord(
        kmp_id=kid,
        full_name=f"Person {kid}",
        canonical_role=role,
        raw_role=role,
        field_sources={
            "full_name": src,
            "canonical_role": src,
            "raw_role": src,
        },
        staleness_flag=False,
        last_observed_date=src.document_date,
        compensation=comp,
        state=state,
    )


def test_quarantined_records_excluded_from_scoring() -> None:
    src = _src("s1", "authoritative", "structured", date(2026, 1, 1))
    k_ok = _kmp("K1", "Principal", src, [_comp("K1", 2025, 1000.0, src)], state=RecordState.VALIDATED)
    k_bad = _kmp("K2", "Director", src, [_comp("K2", 2025, 9000.0, src)], state=RecordState.QUARANTINED)

    payload = _entity_with_kmps([k_ok, k_bad], state=RecordState.PARTIAL)
    scoring_payload = build_scoring_payload(payload)

    assert len(scoring_payload.kmp_list) == 1
    assert scoring_payload.kmp_list[0].kmp_id == "K1"


def test_partial_records_included_with_penalties() -> None:
    good_src = _src("s1", "authoritative", "structured", date(2026, 1, 1))
    weak_src = _src("s2", "web", "ai_inference", date(2026, 1, 1))

    k_good = _kmp("K1", "Principal", good_src, [_comp("K1", 2025, 2000.0, good_src)], state=RecordState.VALIDATED)
    k_partial = _kmp("K2", "Director", weak_src, [_comp("K2", 2025, 2000.0, weak_src)], state=RecordState.PARTIAL)

    validated = _entity_with_kmps([k_good, k_partial], state=RecordState.PARTIAL)
    scored_partial = score(deepcopy(validated))

    validated_clean = _entity_with_kmps([k_good], state=RecordState.VALIDATED)
    scored_clean = score(deepcopy(validated_clean))

    assert scored_partial.final_score < scored_clean.final_score


def test_missing_provenance_produces_warning_and_state_downgrade() -> None:
    src = _src("s1", "official", "pdf_parse", date(2026, 1, 1))
    comp = CompensationRecord(
        kmp_id="K1",
        year=2025,
        compensation_value=1000.0,
        currency="INR",
        field_sources={"currency": src},  # missing compensation_value provenance
    )
    kmp = KMPRecord(
        kmp_id="K1",
        full_name="Person K1",
        canonical_role="Principal",
        raw_role="Principal",
        field_sources={"canonical_role": src},  # missing full_name/raw_role provenance
        staleness_flag=False,
        last_observed_date=date(2026, 1, 1),
        compensation=[comp],
    )
    entity = _entity_with_kmps([kmp], state=RecordState.VALIDATED)

    result = validate_entity_record(entity)

    assert result.validated_payload.state == RecordState.PARTIAL
    assert any(w.startswith("VAL_KMP_PROVENANCE_MISSING") for w in result.validated_payload.quality_warnings)
    assert any(w.startswith("VAL_COMP_PROVENANCE_MISSING") for w in result.validated_payload.quality_warnings)


def test_scoring_has_deterministic_explanations() -> None:
    src = _src("s1", "official", "structured", date(2026, 1, 1))
    k1 = _kmp("K1", "Principal", src, [_comp("K1", 2025, 3000.0, src)], state=RecordState.VALIDATED)
    entity = _entity_with_kmps([k1], state=RecordState.VALIDATED)

    scored = score(entity)

    assert scored.score_explanation == sorted(scored.score_explanation)
    assert all("|" in e for e in scored.score_explanation)
    assert any(e.startswith("FINAL|") for e in scored.score_explanation)


def test_contributing_fields_map_populated() -> None:
    src = _src("s1", "authoritative", "structured", date(2026, 1, 1))
    k1 = _kmp("K1", "Principal", src, [_comp("K1", 2025, 1000.0, src)], state=RecordState.VALIDATED)
    entity = _entity_with_kmps([k1], state=RecordState.VALIDATED)

    scored = score(entity)

    assert "financial_strength_score" in scored.contributing_fields
    assert "outcome_strength_score" in scored.contributing_fields
    assert "final_score" in scored.contributing_fields


def test_same_input_same_score_output() -> None:
    src = _src("s1", "secondary", "pdf_parse", date(2026, 1, 1))
    k1 = _kmp("K1", "Principal", src, [_comp("K1", 2025, 1500.0, src)], state=RecordState.VALIDATED)
    payload = _entity_with_kmps([k1], state=RecordState.VALIDATED)

    s1 = score(deepcopy(payload))
    s2 = score(deepcopy(payload))

    assert s1.final_score == s2.final_score
    assert s1.financial_strength_score == s2.financial_strength_score
    assert s1.outcome_strength_score == s2.outcome_strength_score
    assert s1.score_explanation == s2.score_explanation
    assert s1.contributing_fields == s2.contributing_fields
