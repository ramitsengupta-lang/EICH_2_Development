"""
Module: report_builder
Architecture: M8 — Report Builder

Assembles the final report from validated_data and score_data only.
No re-fetching, no AI reasoning, no access to M2/M3/M4 at this stage.

Invariants (non-negotiable):
  - report_builder.py has zero imports from M2, M3, or M4.
  - Inputs are ValidatedEntityRecord (VALIDATED or PARTIAL state) and ScoreData.
  - QUARANTINED records must never reach this module.
  - PARTIAL records render with an explicit partial-data warning section.
  - Output formats for Phase 1: JSON + Markdown.

Downstream contract is unchanged from EICH 1:
  build_report(validated_data, score_data) → Report
"""
from __future__ import annotations

from dataclasses import asdict, is_dataclass
from datetime import date, datetime
from enum import Enum
from typing import Any

from contracts.score_data import ScoreData
from contracts.validated_data import RecordState, ValidatedEntityRecord


def build_report(entity: ValidatedEntityRecord, score: ScoreData) -> dict[str, Any]:
    """
    Assemble the final report dictionary from validated entity data and score data.

    Raises:
        ValueError: if the entity state is QUARANTINED.
    """
    if entity.state == RecordState.QUARANTINED:
        raise ValueError("Cannot build report for QUARANTINED entity")

    kmp_records = _resolve_kmp_records(entity)
    compensation_records = _resolve_compensation_records(entity, kmp_records)
    metadata = _resolve_metadata(entity)

    quality_warnings = sorted(getattr(entity, "quality_warnings", []))
    state_value = _state_value(entity.state)

    report: dict[str, Any] = {
        "pipeline_run_id": entity.pipeline_run_id or score.pipeline_run_id,
        "entity_id": entity.entity_id,
        "status": "partial" if entity.state == RecordState.PARTIAL else "success",
        "header": {
            "entity_id": entity.entity_id,
            "entity_name": entity.entity_name,
            "pipeline_run_id": entity.pipeline_run_id or score.pipeline_run_id,
            "status": "partial" if entity.state == RecordState.PARTIAL else "success",
        },
        "entity": _build_entity_section(entity, metadata),
        "kmp_summary": _build_kmp_summary_section(kmp_records, compensation_records),
        "eich_score_summary": _build_score_section(score),
        "score_summary": _build_score_section(score),
        "provenance_summary": _build_provenance_section(entity, kmp_records, compensation_records),
        "quality": {
            "state": state_value,
            "is_partial": entity.state == RecordState.PARTIAL,
            "warnings": quality_warnings,
            "warnings_count": len(quality_warnings),
        },
        "report_accuracy": {
            "state": state_value,
            "warnings_count": len(quality_warnings),
            "is_partial": entity.state == RecordState.PARTIAL,
        },
        "sections": {
            "partial_data_warning": _build_partial_warning(entity.state, quality_warnings),
            "score_explanation": list(score.score_explanation),
        },
    }
    return report


def _render_json(validated_data: ValidatedEntityRecord, score_data: ScoreData) -> str:
    """Legacy placeholder retained for interface compatibility."""
    return str(build_report(validated_data, score_data))


def _render_markdown(validated_data: ValidatedEntityRecord, score_data: ScoreData) -> str:
    """Legacy placeholder retained for interface compatibility."""
    report = build_report(validated_data, score_data)
    lines = [
        f"# EICH 2 Report: {report['entity']['entity_name']}",
        "",
        f"- Pipeline Run: {report['pipeline_run_id']}",
        f"- State: {report['quality']['state']}",
        f"- Final Score: {report['score_summary']['final_score']}",
    ]
    return "\n".join(lines)


def _render_conflict_log(validated_data: ValidatedEntityRecord) -> str:
    """Legacy placeholder retained for interface compatibility."""
    return str({"entity_id": validated_data.entity_id, "conflicts": []})


def _resolve_kmp_records(entity: ValidatedEntityRecord) -> list[Any]:
    records = getattr(entity, "kmp_records", None)
    if records is not None:
        return list(records)
    return list(getattr(entity, "kmp_list", []))


def _resolve_compensation_records(entity: ValidatedEntityRecord, kmp_records: list[Any]) -> list[Any]:
    records = getattr(entity, "compensation_records", None)
    if records is not None:
        return list(records)
    collected: list[Any] = []
    for kmp in kmp_records:
        collected.extend(getattr(kmp, "compensation", []))
    return collected


def _resolve_metadata(entity: ValidatedEntityRecord) -> dict[str, Any]:
    metadata = getattr(entity, "metadata", None)
    if isinstance(metadata, dict):
        return dict(metadata)
    return {
        "entity_type": entity.entity_type,
        "jurisdiction": entity.jurisdiction,
        "associated_entities_count": len(getattr(entity, "associated_entities", [])),
        "relationship_map_count": len(getattr(entity, "relationship_map", [])),
        "institution_network_count": len(getattr(entity, "institution_network", [])),
    }


def _build_entity_section(entity: ValidatedEntityRecord, metadata: dict[str, Any]) -> dict[str, Any]:
    return {
        "entity_id": entity.entity_id,
        "entity_name": entity.entity_name,
        "metadata": _to_json_safe(metadata),
    }


def _build_kmp_summary_section(kmp_records: list[Any], compensation_records: list[Any]) -> dict[str, Any]:
    unique_roles = sorted(
        {
            str(getattr(kmp, "canonical_role", "")).strip()
            for kmp in kmp_records
            if str(getattr(kmp, "canonical_role", "")).strip()
        }
    )
    return {
        "kmp_count": len(kmp_records),
        "roles": unique_roles,
        "compensation_record_count": len(compensation_records),
        "kmp_records": [_kmp_to_dict(kmp) for kmp in kmp_records],
        "compensation_records": [_comp_to_dict(comp) for comp in compensation_records],
    }


def _build_score_section(score: ScoreData) -> dict[str, Any]:
    return {
        "final_score": score.final_score,
        "contributing_fields": dict(sorted(score.contributing_fields.items())),
        "score_explanation": list(score.score_explanation),
        "rating": score.rating,
    }


def _build_provenance_section(entity: ValidatedEntityRecord, kmp_records: list[Any], compensation_records: list[Any]) -> dict[str, Any]:
    return {
        "entity_fields": sorted(getattr(entity, "field_sources", {}).keys()),
        "kmp_fields": sorted(
            {
                key
                for kmp in kmp_records
                for key in getattr(kmp, "field_sources", {}).keys()
            }
        ),
        "compensation_fields": sorted(
            {
                key
                for comp in compensation_records
                for key in getattr(comp, "field_sources", {}).keys()
            }
        ),
    }


def _build_partial_warning(state: RecordState, warnings: list[str]) -> dict[str, Any] | None:
    if state != RecordState.PARTIAL:
        return None
    return {
        "title": "Partial Data Notice",
        "message": "Report generated from PARTIAL validated data; review warnings before consumption.",
        "warnings": list(warnings),
    }


def _kmp_to_dict(kmp: Any) -> dict[str, Any]:
    return {
        "kmp_id": getattr(kmp, "kmp_id", ""),
        "full_name": getattr(kmp, "full_name", ""),
        "canonical_role": getattr(kmp, "canonical_role", ""),
        "state": _state_value(getattr(kmp, "state", RecordState.VALIDATED)),
        "staleness_flag": bool(getattr(kmp, "staleness_flag", False)),
        "last_observed_date": _iso_or_none(getattr(kmp, "last_observed_date", None)),
    }


def _comp_to_dict(comp: Any) -> dict[str, Any]:
    return {
        "kmp_id": getattr(comp, "kmp_id", ""),
        "year": getattr(comp, "year", None),
        "compensation_value": getattr(comp, "compensation_value", None),
        "currency": getattr(comp, "currency", ""),
        "evidence_sentence": getattr(comp, "evidence_sentence", None),
    }


def _state_value(value: Any) -> str:
    if isinstance(value, RecordState):
        return value.value
    if isinstance(value, Enum):
        return str(value.value)
    return str(value)


def _iso_or_none(value: Any) -> str | None:
    if value is None:
        return None
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return str(value)


def _to_json_safe(value: Any) -> Any:
    if value is None or isinstance(value, (bool, int, float, str)):
        return value
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    if isinstance(value, Enum):
        return value.value
    if isinstance(value, dict):
        return {str(k): _to_json_safe(v) for k, v in value.items()}
    if isinstance(value, list):
        return [_to_json_safe(v) for v in value]
    if is_dataclass(value):
        return _to_json_safe(asdict(value))
    return str(value)
