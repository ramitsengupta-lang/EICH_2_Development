"""
Tests: CLI and trace artifact smoke tests

Covers:
  1. Successful run creates all expected artifacts.
  2. Quarantined run omits score_data.json and report.json.
  3. Fatal run writes errors.json and main() returns exit code 1.
  4. execution_trace.json stage_sequence is stable and deterministic.

All tests use fake stage injection via the _runner_factory parameter of
main() and TemporaryDirectory for artifact isolation.
"""
from __future__ import annotations

import json
import tempfile
from dataclasses import dataclass, field
from datetime import date, datetime
from pathlib import Path

import pytest

from contracts.source_ref import SourceRef
from contracts.validated_data import (
    CompensationRecord,
    KMPRecord,
    RecordState,
    ValidatedEntityRecord,
)
from pipeline.pipeline_runner import PipelineResult, PipelineRunner
from pipeline.trace_writer import write_trace_artifacts
from pipeline.preflight import PreflightResult, run_preflight
from pipeline.cli import main, _deterministic_run_id


# ---------------------------------------------------------------------------
# Shared fakes — identical pattern to test_pipeline_smoke.py
# ---------------------------------------------------------------------------

@dataclass
class _ValidationSummary:
    warnings_count: int = 0
    excluded_from_scoring_count: int = 0


@dataclass
class _ValidationResult:
    validated_payload: ValidatedEntityRecord
    summary: _ValidationSummary


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


def _entity(state: RecordState, run_id: str = "run-test") -> ValidatedEntityRecord:
    src = _src()
    comp = CompensationRecord(
        kmp_id="K1",
        year=2025,
        compensation_value=1_000_000.0,
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
        pipeline_run_id=run_id,
    )


class _FakeRunner:
    """Minimal PipelineRunner stand-in: returns a pre-built PipelineResult."""

    def __init__(self, result: PipelineResult) -> None:
        self._result = result

    def run(self, raw_input, source_urls, pipeline_run_id, ai_fields=None):
        # Mirror the run_id from the caller
        import dataclasses
        return dataclasses.replace(self._result, pipeline_run_id=pipeline_run_id)


def _success_result(run_id: str = "run-success") -> PipelineResult:
    entity = _entity(RecordState.VALIDATED, run_id)
    return PipelineResult(
        pipeline_run_id=run_id,
        validated_data=entity,
        score_data={
            "entity_id": "E1",
            "final_score": 85.0,
            "rating": "A",
        },
        report={"entity_id": "E1", "final_score": 85.0},
        validation_summary=_ValidationSummary(warnings_count=0),
        warnings=[],
        status="success",
        error=None,
        stage_sequence=["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8"],
        stage_timings={
            "M1": 0.001, "M2": 0.002, "M3": 0.003, "M4": 0.004,
            "M5": 0.005, "M6": 0.006, "M7": 0.007, "M8": 0.008,
        },
    )


def _quarantined_result(run_id: str = "run-quarantined") -> PipelineResult:
    entity = _entity(RecordState.QUARANTINED, run_id)
    return PipelineResult(
        pipeline_run_id=run_id,
        validated_data=entity,
        score_data=None,
        report=None,
        validation_summary=_ValidationSummary(warnings_count=2, excluded_from_scoring_count=1),
        warnings=["VAL_ENTITY_REQUIRED_MISSING|entity_name|missing"],
        status="quarantined",
        error=None,
        stage_sequence=["M1", "M2", "M3", "M4", "M5", "M6"],
        stage_timings={
            "M1": 0.001, "M2": 0.002, "M3": 0.003,
            "M4": 0.004, "M5": 0.005, "M6": 0.006,
        },
    )


def _failed_result(run_id: str = "run-failed") -> PipelineResult:
    return PipelineResult(
        pipeline_run_id=run_id,
        validated_data=None,
        score_data=None,
        report=None,
        validation_summary=None,
        warnings=[],
        status="failed",
        error={
            "type": "PipelineStageError",
            "stage": "M2",
            "reason": "Network timeout",
            "details": {"url": "https://example.org"},
        },
        stage_sequence=["M1", "M2"],
        stage_timings={"M1": 0.001, "M2": 0.002},
    )


# ---------------------------------------------------------------------------
# Test 1 — Successful run creates all expected artifacts
# ---------------------------------------------------------------------------

def test_successful_run_creates_all_artifacts(tmp_path: Path) -> None:
    """A success result must produce execution_trace, pipeline_result,
    validation_summary, score_data, and report — no errors.json."""
    result = _success_result("run-success")
    written = write_trace_artifacts(
        result=result,
        output_dir=tmp_path,
        run_started_at="2026-01-01T00:00:00+00:00",
        run_finished_at="2026-01-01T00:00:01+00:00",
        run_duration_seconds=1.0,
    )

    # All five success artifacts must be present
    assert "execution_trace" in written
    assert "pipeline_result" in written
    assert "validation_summary" in written
    assert "score_data" in written
    assert "report" in written

    # errors.json must NOT be written for a success result
    assert "errors" not in written
    assert not (tmp_path / "errors.json").exists()

    # Verify execution_trace contents are machine-readable and stable
    trace = json.loads((tmp_path / "execution_trace.json").read_text())
    assert trace["pipeline_run_id"] == "run-success"
    assert trace["status"] == "success"
    assert trace["stage_sequence"] == ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8"]
    assert isinstance(trace["stage_timings"], dict)
    assert trace["warnings_count"] == 0


# ---------------------------------------------------------------------------
# Test 2 — Quarantined run omits score_data and report
# ---------------------------------------------------------------------------

def test_quarantined_run_omits_score_and_report_artifacts(tmp_path: Path) -> None:
    """A quarantined result must omit score_data.json and report.json
    but still produce execution_trace, pipeline_result, and validation_summary."""
    result = _quarantined_result("run-quarantined")
    written = write_trace_artifacts(
        result=result,
        output_dir=tmp_path,
        run_started_at="2026-01-01T00:00:00+00:00",
        run_finished_at="2026-01-01T00:00:01+00:00",
        run_duration_seconds=1.0,
    )

    assert "execution_trace" in written
    assert "pipeline_result" in written
    assert "validation_summary" in written

    # These must NOT be written
    assert "score_data" not in written
    assert "report" not in written
    assert not (tmp_path / "score_data.json").exists()
    assert not (tmp_path / "report.json").exists()

    # Stage sequence must stop at M6
    trace = json.loads((tmp_path / "execution_trace.json").read_text())
    assert trace["status"] == "quarantined"
    assert trace["stage_sequence"] == ["M1", "M2", "M3", "M4", "M5", "M6"]


# ---------------------------------------------------------------------------
# Test 3 — Fatal run writes errors.json and CLI returns exit code 1
# ---------------------------------------------------------------------------

def test_fatal_run_writes_errors_json_and_exits_nonzero(tmp_path: Path) -> None:
    """A failed result must produce errors.json; the CLI must return exit code 1."""
    # ---- trace_writer produces errors.json ----
    result = _failed_result("run-failed")
    written = write_trace_artifacts(
        result=result,
        output_dir=tmp_path / "trace",
        run_started_at="2026-01-01T00:00:00+00:00",
        run_finished_at="2026-01-01T00:00:00.5+00:00",
        run_duration_seconds=0.5,
    )

    assert "errors" in written
    errors = json.loads((tmp_path / "trace" / "errors.json").read_text())
    assert errors["type"] == "PipelineStageError"
    assert errors["stage"] == "M2"

    # ---- CLI returns exit code 1 ----
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"entity_id": "E1"}), encoding="utf-8")

    fake_result = _failed_result()

    def factory():
        return _FakeRunner(fake_result)

    exit_code = main(
        argv=[
            str(input_file),
            "--output-dir", str(tmp_path / "cli_out"),
            "--run-id", "run-failed",
        ],
        _runner_factory=factory,
    )

    assert exit_code == 1

    # errors.json must exist in the CLI output directory
    errors_path = tmp_path / "cli_out" / "run-failed" / "errors.json"
    assert errors_path.exists(), f"errors.json not found at {errors_path}"
    cli_errors = json.loads(errors_path.read_text())
    assert cli_errors["stage"] == "M2"


# ---------------------------------------------------------------------------
# Test 4 — execution_trace stage_sequence is stable across identical runs
# ---------------------------------------------------------------------------

def test_execution_trace_stage_order_is_deterministic(tmp_path: Path) -> None:
    """Same input must produce identical stage_sequence in execution_trace
    across two independent CLI invocations."""
    input_file = tmp_path / "input.json"
    input_file.write_text(json.dumps({"entity_id": "E-stable"}), encoding="utf-8")

    def factory():
        return _FakeRunner(_success_result())

    # First run
    exit1 = main(
        argv=[
            str(input_file),
            "--output-dir", str(tmp_path / "out1"),
            "--run-id", "run-stable",
        ],
        _runner_factory=factory,
    )
    # Second run
    exit2 = main(
        argv=[
            str(input_file),
            "--output-dir", str(tmp_path / "out2"),
            "--run-id", "run-stable",
        ],
        _runner_factory=factory,
    )

    assert exit1 == 0
    assert exit2 == 0

    trace1 = json.loads(
        (tmp_path / "out1" / "run-stable" / "execution_trace.json").read_text()
    )
    trace2 = json.loads(
        (tmp_path / "out2" / "run-stable" / "execution_trace.json").read_text()
    )

    assert trace1["stage_sequence"] == trace2["stage_sequence"]
    assert trace1["stage_sequence"] == ["M1", "M2", "M3", "M4", "M5", "M6", "M7", "M8"]
    assert trace1["status"] == trace2["status"] == "success"
