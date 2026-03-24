from __future__ import annotations

from datetime import date, datetime

import pytest

from contracts.source_ref import SourceRef
from contracts.validated_data import CompensationRecord, KMPRecord, RecordState
from m5_merger.merge_conflict import MergeConflictError, MergeConflictLog
from m5_merger.merger import Merger


def _src(
    source_id: str,
    tier: str,
    method: str,
    doc_date: date,
    name: str = "source",
) -> SourceRef:
    return SourceRef(
        source_id=source_id,
        source_name=name,
        source_tier=tier,
        extraction_method=method,
        document_date=doc_date,
        fetched_at=datetime(2026, 1, 1),
        url=None,
    )


def _comp(
    kmp_id: str,
    year: int,
    value: float | None,
    currency: str,
    source: SourceRef,
    evidence_sentence: str | None = None,
) -> CompensationRecord:
    return CompensationRecord(
        kmp_id=kmp_id,
        year=year,
        compensation_value=value,
        currency=currency,
        field_sources={
            "compensation_value": source,
            "currency": source,
        },
        evidence_sentence=evidence_sentence,
    )


def _kmp(
    kmp_id: str,
    full_name: str,
    canonical_role: str,
    raw_role: str,
    source: SourceRef,
    compensation: list[CompensationRecord] | None = None,
) -> KMPRecord:
    return KMPRecord(
        kmp_id=kmp_id,
        full_name=full_name,
        canonical_role=canonical_role,
        raw_role=raw_role,
        field_sources={
            "full_name": source,
            "canonical_role": source,
            "raw_role": source,
        },
        compensation=compensation or [],
        state=RecordState.VALIDATED,
    )


def test_structured_value_beats_ai_value() -> None:
    merger = Merger(entity_id="E1")

    authoritative_ai = _src("s1", "authoritative", "ai_inference", date(2026, 1, 5))
    secondary_structured = _src("s2", "secondary", "structured", date(2025, 12, 31))

    records = [
        _comp("K1", 2025, 90.0, "INR", authoritative_ai),
        _comp("K1", 2025, 100.0, "INR", secondary_structured),
    ]

    out = merger.merge_compensation_records(records)

    assert len(out) == 1
    assert out[0].compensation_value == 100.0
    assert out[0].field_sources["compensation_value"].source_id == "s2"


def test_structured_null_does_not_beat_ai_non_null() -> None:
    merger = Merger(entity_id="E1")

    authoritative_structured_null = _src("s1", "authoritative", "structured", date(2026, 1, 10))
    official_ai_non_null = _src("s2", "official", "ai_inference", date(2026, 1, 9))

    records = [
        _comp("K1", 2025, None, "INR", authoritative_structured_null),
        _comp("K1", 2025, 120.0, "INR", official_ai_non_null),
    ]

    out = merger.merge_compensation_records(records)

    assert len(out) == 1
    assert out[0].compensation_value == 120.0
    assert out[0].field_sources["compensation_value"].source_id == "s2"


def test_recency_tie_break_within_same_tier() -> None:
    merger = Merger(entity_id="E1")

    older = _src("s1", "official", "ai_inference", date(2025, 1, 1))
    newer = _src("s2", "official", "ai_inference", date(2025, 12, 1))

    records = [
        _comp("K1", 2025, 200.0, "INR", older),
        _comp("K1", 2025, 250.0, "INR", newer),
    ]

    out = merger.merge_compensation_records(records)

    assert len(out) == 1
    assert out[0].compensation_value == 250.0
    assert out[0].field_sources["compensation_value"].source_id == "s2"


def test_compensation_duplicate_conflict_raises_error() -> None:
    merger = Merger(entity_id="E1", conflict_log=MergeConflictLog("run1", "E1"))

    # Same key, same tier/date/method, conflicting non-null values -> irreconcilable tie.
    s1 = _src("s1", "official", "ai_inference", date(2025, 6, 1))
    s2 = _src("s2", "official", "ai_inference", date(2025, 6, 1))

    records = [
        _comp("K1", 2025, 300.0, "INR", s1),
        _comp("K1", 2025, 350.0, "INR", s2),
    ]

    with pytest.raises(MergeConflictError):
        merger.merge_compensation_records(records)

    assert merger.conflict_log is not None
    assert merger.conflict_log.raised_count >= 1


def test_role_normalization_affects_matching() -> None:
    merger = Merger(entity_id="E1")

    src = _src("s1", "official", "structured", date(2026, 1, 1))
    k1 = _kmp("K1", "Alice Rao", "CEO", "CEO", src)
    k2 = _kmp("K1", "Alice Rao", "Chief Executive Officer", "Chief Executive Officer", src)

    merged = merger.merge_kmp_records([k1, k2])

    assert len(merged) == 1
    assert merged[0].canonical_role == "Chief Executive Officer"


def test_conflict_logging_increments_raised_and_suppressed_counts() -> None:
    log = MergeConflictLog("run1", "E1")
    merger = Merger(entity_id="E1", conflict_log=log)

    # Suppressed conflict via deterministic winner.
    best = _src("s_best", "authoritative", "structured", date(2026, 2, 1))
    weak = _src("s_weak", "secondary", "ai_inference", date(2026, 1, 1))
    merger.merge_compensation_records([
        _comp("K1", 2025, 100.0, "INR", weak),
        _comp("K1", 2025, 110.0, "INR", best),
    ])

    suppressed_after_first = log.suppressed_count
    assert suppressed_after_first >= 1

    # Raised conflict via irreconcilable tie.
    tie1 = _src("s1", "official", "ai_inference", date(2025, 6, 1))
    tie2 = _src("s2", "official", "ai_inference", date(2025, 6, 1))
    with pytest.raises(MergeConflictError):
        merger.merge_compensation_records([
            _comp("K1", 2026, 400.0, "INR", tie1),
            _comp("K1", 2026, 450.0, "INR", tie2),
        ])

    assert log.raised_count >= 1
    assert log.suppressed_count >= suppressed_after_first
