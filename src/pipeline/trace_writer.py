"""
Module: trace_writer
Architecture: Orchestration layer — trace artifact output

Writes deterministic, machine-readable trace artifacts for a pipeline run.
All output files are JSON with stable key ordering (sort_keys=True).

Artifact map:
  execution_trace.json   — stage order, timings, overall status
  pipeline_result.json   — run id, status, warnings, error
  validation_summary.json — validator counters (when available)
  score_data.json         — scoring output (when scoring ran)
  report.json             — report output (when report was built)
  errors.json             — error detail (only on fatal failure)
"""
from __future__ import annotations

import json
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from enum import Enum
from pathlib import Path
from typing import Any


# ---------------------------------------------------------------------------
# JSON serialization helpers
# ---------------------------------------------------------------------------

def _to_json_safe(obj: Any) -> Any:
    """Recursively convert an arbitrary object to a JSON-serializable structure."""
    if obj is None or isinstance(obj, (bool, int, float, str)):
        return obj
    if isinstance(obj, (datetime, date)):
        return obj.isoformat()
    if isinstance(obj, Enum):
        return obj.value
    if is_dataclass(obj) and not isinstance(obj, type):
        return {f.name: _to_json_safe(getattr(obj, f.name)) for f in fields(obj)}
    if isinstance(obj, dict):
        return {str(k): _to_json_safe(v) for k, v in obj.items()}
    if isinstance(obj, (list, tuple)):
        return [_to_json_safe(item) for item in obj]
    if hasattr(obj, "__dict__"):
        return {
            k: _to_json_safe(v)
            for k, v in vars(obj).items()
            if not k.startswith("_")
        }
    return str(obj)


def _write_json(path: Path, payload: Any) -> Path:
    with open(path, "w", encoding="utf-8") as fh:
        json.dump(_to_json_safe(payload), fh, indent=2, sort_keys=True)
    return path


# ---------------------------------------------------------------------------
# Public API
# ---------------------------------------------------------------------------

def write_trace_artifacts(
    result: Any,
    output_dir: Path,
    run_started_at: str,
    run_finished_at: str,
    run_duration_seconds: float,
) -> dict[str, Path]:
    """
    Write all trace artifacts for a completed pipeline run.

    Returns a mapping of artifact_name -> absolute Path for every file written.
    Files are only created when the corresponding data is present (e.g.,
    score_data.json is skipped when scoring was gated by quarantine).
    """
    output_dir.mkdir(parents=True, exist_ok=True)
    written: dict[str, Path] = {}

    # --- execution_trace.json ---
    trace_payload: dict[str, Any] = {
        "pipeline_run_id": result.pipeline_run_id,
        "run_started_at": run_started_at,
        "run_finished_at": run_finished_at,
        "run_duration_seconds": run_duration_seconds,
        "status": result.status,
        "stage_sequence": result.stage_sequence,
        "stage_timings": getattr(result, "stage_timings", {}),
        "warnings_count": len(result.warnings),
    }
    written["execution_trace"] = _write_json(
        output_dir / "execution_trace.json", trace_payload
    )

    # --- pipeline_result.json ---
    result_payload: dict[str, Any] = {
        "error": result.error,
        "pipeline_run_id": result.pipeline_run_id,
        "stage_sequence": result.stage_sequence,
        "status": result.status,
        "warnings": result.warnings,
    }
    written["pipeline_result"] = _write_json(
        output_dir / "pipeline_result.json", result_payload
    )

    # --- validation_summary.json (when validator ran) ---
    if result.validation_summary is not None:
        written["validation_summary"] = _write_json(
            output_dir / "validation_summary.json",
            _to_json_safe(result.validation_summary),
        )

    # --- score_data.json (when scoring ran) ---
    if result.score_data is not None:
        written["score_data"] = _write_json(
            output_dir / "score_data.json",
            _to_json_safe(result.score_data),
        )

    # --- report.json (when report was built) ---
    if result.report is not None:
        written["report"] = _write_json(
            output_dir / "report.json",
            _to_json_safe(result.report),
        )

    # --- errors.json (only on fatal failure) ---
    if result.status == "failed" and result.error is not None:
        written["errors"] = _write_json(
            output_dir / "errors.json",
            result.error,
        )

    return written
