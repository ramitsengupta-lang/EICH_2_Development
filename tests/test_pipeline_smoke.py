from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime

from contracts.source_ref import SourceRef
from contracts.validated_data import CompensationRecord, KMPRecord, RecordState, ValidatedEntityRecord
from pipeline.pipeline_runner import PipelineRunner


@dataclass
class _ValidationSummary:
    warnings_count: int = 0
    excluded_from_scoring_count: int = 0


@dataclass
class _ValidationResult:
    validated_payload: ValidatedEntityRecord
    summary: _ValidationSummary


class _CallTracker:
    def __init__(self) -> None:
        self.calls: list[str] = []

    def add(self, name: str) -> None:
        self.calls.append(name)


def _src(source_id: str = "s1", tier: str = "official", method: str = "structured") -> SourceRef:
    return SourceRef(
        source_id=source_id,
        source_name="source",
        source_tier=tier,
        extraction_method=method,
        document_date=date(2026, 1, 1),
        fetched_at=datetime(2026, 1, 2),
        url="https://example.org",
    )


def _entity(state: RecordState) -> ValidatedEntityRecord:
    src = _src()
    comp = CompensationRecord(
        kmp_id="K1",
        year=2025,
        compensation_value=1000.0,
        currency="INR",
        field_sources={"compensation_value": src, "currency": src},
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
        quality_warnings=[],
        state=state,
        pipeline_run_id="run-1",
    )


class FakeM1:
    def __init__(self, tracker: _CallTracker) -> None:
        self.tracker = tracker

    def resolve_entity(self, raw_input: dict) -> object:
        self.tracker.add("M1")

        class _Identity:
            entity_id = raw_input.get("entity_id", "E1")

        return _Identity()


class FakeM2:
    def __init__(self, tracker: _CallTracker) -> None:
        self.tracker = tracker

    def acquire_sources(self, entity_id: str, source_urls: list[str]) -> list[dict]:
        self.tracker.add("M2")
        return [{"entity_id": entity_id, "url": "dummy"}]


class FakeM3:
    def __init__(self, tracker: _CallTracker) -> None:
        self.tracker = tracker

    def extract(self, evidence: dict) -> list[dict]:
        self.tracker.add("M3")
        return [{"kind": "structured", "evidence": evidence}]


class FakeM4:
    def __init__(self, tracker: _CallTracker) -> None:
        self.tracker = tracker

    def extract(self, evidence: dict, fields: list[str]) -> list[dict]:
        self.tracker.add("M4")
        return [{"kind": "ai", "fields": fields, "evidence": evidence}]


class FakeM5Merger:
    def __init__(self, tracker: _CallTracker, state: RecordState) -> None:
        self.tracker = tracker
        self.state = state

    def merge_entity_records(self, entity_records: list[dict], pipeline_run_id: str) -> ValidatedEntityRecord:
        self.tracker.add("M5")
        merged = _entity(self.state)
        merged.pipeline_run_id = pipeline_run_id
        return merged


class FakeM6:
    def __init__(self, tracker: _CallTracker, state: RecordState) -> None:
        self.tracker = tracker
        self.state = state

    def validate_entity_record(self, entity_record: ValidatedEntityRecord) -> _ValidationResult:
        self.tracker.add("M6")
        entity_record.state = self.state
        summary = _ValidationSummary(
            warnings_count=1 if self.state != RecordState.VALIDATED else 0,
            excluded_from_scoring_count=1 if self.state == RecordState.QUARANTINED else 0,
        )
        if self.state != RecordState.VALIDATED:
            entity_record.quality_warnings.append(f"state={self.state.value}")
        return _ValidationResult(validated_payload=entity_record, summary=summary)


class FakeM7:
    def __init__(self, tracker: _CallTracker) -> None:
        self.tracker = tracker

    def score_from_validation_result(self, result: _ValidationResult) -> dict:
        self.tracker.add("M7")
        payload = result.validated_payload
        return {
            "pipeline_run_id": payload.pipeline_run_id,
            "entity_id": payload.entity_id,
            "final_score": 42.0 if payload.state == RecordState.PARTIAL else 84.0,
            "state": payload.state.value,
            "contributing_fields": {
                "financial_strength_score": "kmp_list[].compensation[].compensation_value",
                "outcome_strength_score": "kmp_list[].canonical_role",
            },
        }


class FakeM8:
    def __init__(self, tracker: _CallTracker) -> None:
        self.tracker = tracker

    def build_report(self, validated_data: ValidatedEntityRecord, score_data: dict) -> dict:
        self.tracker.add("M8")
        return {
            "entity_id": validated_data.entity_id,
            "run_id": validated_data.pipeline_run_id,
            "final_score": score_data["final_score"],
            "state": validated_data.state.value,
        }


def _runner_for_state(state: RecordState, tracker: _CallTracker) -> PipelineRunner:
    return PipelineRunner(
        identifier_stage=FakeM1(tracker),
        source_acquirer_stage=FakeM2(tracker),
        structured_extractor_stage=FakeM3(tracker),
        ai_extractor_stage=FakeM4(tracker),
        merger_stage_factory=lambda entity_id: FakeM5Merger(tracker, state),
        validator_stage=FakeM6(tracker, state),
        scorer_stage=FakeM7(tracker),
        report_builder_stage=FakeM8(tracker),
        clock=lambda: datetime(2026, 1, 1, 0, 0, 0),
    )


def test_happy_path_runs_all_stages_and_produces_report() -> None:
    tracker = _CallTracker()
    runner = _runner_for_state(RecordState.VALIDATED, tracker)

    result = runner.run(
        raw_input={"entity_id": "E1"},
        source_urls=["https://example.org/source"],
        pipeline_run_id="run-happy",
        ai_fields=["kmp_role"],
    )

    assert result.status == "success"
    assert result.score_data is not None
    assert result.report is not None
    assert result.stage_sequence == ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8"]
    assert tracker.calls == ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8"]


def test_quarantined_path_skips_scoring_and_report() -> None:
    tracker = _CallTracker()
    runner = _runner_for_state(RecordState.QUARANTINED, tracker)

    result = runner.run(
        raw_input={"entity_id": "E1"},
        source_urls=["https://example.org/source"],
        pipeline_run_id="run-quarantined",
        ai_fields=["kmp_role"],
    )

    assert result.status == "quarantined"
    assert result.score_data is None
    assert result.report is None
    assert result.stage_sequence == ["M1", "M2", "M3", "M4", "M5", "M6"]
    assert tracker.calls == ["M1", "M2", "M3", "M4", "M5", "M6"]


def test_partial_path_produces_score_and_report() -> None:
    tracker = _CallTracker()
    runner = _runner_for_state(RecordState.PARTIAL, tracker)

    result = runner.run(
        raw_input={"entity_id": "E1"},
        source_urls=["https://example.org/source"],
        pipeline_run_id="run-partial",
        ai_fields=["kmp_role"],
    )

    assert result.status == "partial"
    assert result.score_data is not None
    assert result.report is not None
    assert result.stage_sequence == ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8"]


def test_deterministic_repeatability_same_input_same_outputs() -> None:
    tracker_1 = _CallTracker()
    tracker_2 = _CallTracker()

    runner_1 = _runner_for_state(RecordState.VALIDATED, tracker_1)
    runner_2 = _runner_for_state(RecordState.VALIDATED, tracker_2)

    kwargs = {
        "raw_input": {"entity_id": "E1"},
        "source_urls": ["https://example.org/source"],
        "pipeline_run_id": "run-repeat",
        "ai_fields": ["kmp_role"],
    }

    r1 = runner_1.run(**kwargs)
    r2 = runner_2.run(**kwargs)

    assert r1.status == r2.status
    assert r1.score_data == r2.score_data
    assert r1.report == r2.report
    assert r1.warnings == r2.warnings


def test_stage_order_exact_m1_to_m8() -> None:
    tracker = _CallTracker()
    runner = _runner_for_state(RecordState.VALIDATED, tracker)

    _ = runner.run(
        raw_input={"entity_id": "E1"},
        source_urls=["https://example.org/source"],
        pipeline_run_id="run-order",
        ai_fields=["kmp_role"],
    )

    assert tracker.calls == ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8"]
