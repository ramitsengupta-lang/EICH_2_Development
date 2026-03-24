"""
Module: structured_extractor
Architecture: M3 — Structured Extractor

Deterministically parses structured payloads into ValidatedEntityRecord outputs.
No network calls and no AI inference are used in this module.
"""
from __future__ import annotations

from copy import copy
from datetime import date, datetime
from typing import Any

from contracts.source_ref import SourceRef
from contracts.validated_data import CompensationRecord, KMPRecord, RecordState, ValidatedEntityRecord


_REQUIRED_ENTITY_FIELDS: tuple[str, ...] = ("entity_name", "entity_type", "jurisdiction")


def extract(raw_input: dict[str, Any], source_ref: SourceRef | None = None) -> list[ValidatedEntityRecord]:
    """
    Parse structured input and return one ValidatedEntityRecord per identifiable entity.

    Accepts either:
      1) extract(raw_input: dict, source_ref: SourceRef)
      2) extract(raw_input: dict)  # source_ref will be synthesized deterministically
    """
    entities_payload = _extract_entities(raw_input)
    base_source_ref = _ensure_structured_source_ref(source_ref, raw_input)

    records: list[ValidatedEntityRecord] = []
    for index, entity_payload in enumerate(entities_payload):
        if not _is_identifiable(entity_payload):
            continue
        records.append(_build_entity_record(entity_payload, base_source_ref, index))
    return records


def extract_xbrl(raw_input: dict[str, Any], source_ref: SourceRef | None = None) -> list[ValidatedEntityRecord]:
    """Deterministic XBRL adapter; delegates to extract()."""
    return extract(raw_input, source_ref)


def extract_json_api(raw_input: dict[str, Any], source_ref: SourceRef | None = None) -> list[ValidatedEntityRecord]:
    """Deterministic JSON API adapter; delegates to extract()."""
    return extract(raw_input, source_ref)


def extract_csv(raw_input: dict[str, Any], source_ref: SourceRef | None = None) -> list[ValidatedEntityRecord]:
    """Deterministic CSV adapter; delegates to extract()."""
    return extract(raw_input, source_ref)


def _extract_entities(raw_input: dict[str, Any]) -> list[dict[str, Any]]:
    if "entities" in raw_input and isinstance(raw_input["entities"], list):
        return [item for item in raw_input["entities"] if isinstance(item, dict)]
    if isinstance(raw_input, dict):
        return [raw_input]
    return []


def _ensure_structured_source_ref(source_ref: SourceRef | None, raw_input: dict[str, Any]) -> SourceRef:
    if source_ref is None:
        source_ref = SourceRef(
            source_id=str(raw_input.get("source_id", "structured_input")),
            source_name=str(raw_input.get("source_name", "structured_input")),
            source_tier=str(raw_input.get("source_tier", "official")),
            extraction_method="structured",
            document_date=None,
            fetched_at=datetime.min,
            url=raw_input.get("source_url"),
        )
    elif source_ref.extraction_method != "structured":
        copied = copy(source_ref)
        copied.extraction_method = "structured"
        source_ref = copied
    return source_ref


def _is_identifiable(entity_payload: dict[str, Any]) -> bool:
    entity_id = str(entity_payload.get("entity_id", "")).strip()
    entity_name = str(entity_payload.get("entity_name", "")).strip()
    return bool(entity_id or entity_name)


def _build_entity_record(entity_payload: dict[str, Any], source_ref: SourceRef, index: int) -> ValidatedEntityRecord:
    entity_name = str(entity_payload.get("entity_name", "")).strip()
    entity_id = str(entity_payload.get("entity_id", "")).strip() or _derive_entity_id(entity_name, index)
    entity_type = str(entity_payload.get("entity_type", "")).strip()
    jurisdiction = str(entity_payload.get("jurisdiction", "")).strip()

    state = RecordState.VALIDATED
    warnings: list[str] = []
    for field_name in _REQUIRED_ENTITY_FIELDS:
        if not str(entity_payload.get(field_name, "")).strip():
            state = RecordState.PARTIAL
            warnings.append(f"M3_REQUIRED_FIELD_MISSING|{field_name}|missing required field")

    kmp_records = _build_kmp_records(entity_payload, source_ref)
    return ValidatedEntityRecord(
        entity_id=entity_id,
        entity_name=entity_name,
        entity_type=entity_type,
        jurisdiction=jurisdiction,
        kmp_list=kmp_records,
        associated_entities=list(entity_payload.get("associated_entities", [])),
        relationship_map=list(entity_payload.get("relationship_map", [])),
        institution_network=list(entity_payload.get("institution_network", [])),
        field_sources={
            "entity_id": source_ref,
            "entity_name": source_ref,
            "entity_type": source_ref,
            "jurisdiction": source_ref,
        },
        quality_warnings=sorted(warnings),
        state=state,
        pipeline_run_id=str(entity_payload.get("pipeline_run_id", "")),
    )


def _build_kmp_records(entity_payload: dict[str, Any], source_ref: SourceRef) -> list[KMPRecord]:
    payload = entity_payload.get("kmp_records", entity_payload.get("kmp_list", []))
    if not isinstance(payload, list):
        return []

    compensation_payload = entity_payload.get("compensation_records", [])
    compensation_by_kmp = _group_compensation_by_kmp(compensation_payload)

    records: list[KMPRecord] = []
    for index, item in enumerate(payload):
        if not isinstance(item, dict):
            continue
        kmp_id = str(item.get("kmp_id", "")).strip() or f"KMP-{index + 1}"
        full_name = str(item.get("full_name", "")).strip()
        canonical_role = str(item.get("canonical_role", item.get("role", ""))).strip()
        raw_role = str(item.get("raw_role", canonical_role)).strip()
        last_observed = _parse_date(item.get("last_observed_date"))

        records.append(
            KMPRecord(
                kmp_id=kmp_id,
                full_name=full_name,
                canonical_role=canonical_role,
                raw_role=raw_role,
                field_sources={
                    "full_name": source_ref,
                    "canonical_role": source_ref,
                    "raw_role": source_ref,
                },
                staleness_flag=bool(item.get("staleness_flag", False)),
                last_observed_date=last_observed,
                compensation=compensation_by_kmp.get(kmp_id, []),
                state=RecordState.PARTIAL if (not full_name or not canonical_role) else RecordState.VALIDATED,
            )
        )
    return records


def _group_compensation_by_kmp(payload: Any) -> dict[str, list[CompensationRecord]]:
    if not isinstance(payload, list):
        return {}

    grouped: dict[str, list[CompensationRecord]] = {}
    for item in payload:
        if not isinstance(item, dict):
            continue
        kmp_id = str(item.get("kmp_id", "")).strip()
        if not kmp_id:
            continue
        year = _safe_int(item.get("year"))
        if year is None:
            continue
        comp_record = CompensationRecord(
            kmp_id=kmp_id,
            year=year,
            compensation_value=_safe_float(item.get("compensation_value")),
            currency=str(item.get("currency", "")).strip(),
            field_sources={
                "compensation_value": _ensure_comp_source_ref(item),
                "currency": _ensure_comp_source_ref(item),
            },
            evidence_sentence=item.get("evidence_sentence"),
        )
        grouped.setdefault(kmp_id, []).append(comp_record)

    for kmp_id in grouped:
        grouped[kmp_id].sort(key=lambda rec: rec.year)
    return grouped


def _ensure_comp_source_ref(item: dict[str, Any]) -> SourceRef:
    return SourceRef(
        source_id=str(item.get("source_id", "structured_input")),
        source_name=str(item.get("source_name", "structured_input")),
        source_tier=str(item.get("source_tier", "official")),
        extraction_method="structured",
        document_date=None,
        fetched_at=datetime.min,
        url=item.get("source_url"),
    )


def _derive_entity_id(entity_name: str, index: int) -> str:
    if not entity_name:
        return f"ENT-{index + 1}"
    normalized = "".join(char for char in entity_name.upper() if char.isalnum())
    return normalized[:20] or f"ENT-{index + 1}"


def _safe_int(value: Any) -> int | None:
    try:
        return int(value)
    except (TypeError, ValueError):
        return None


def _safe_float(value: Any) -> float | None:
    try:
        return float(value)
    except (TypeError, ValueError):
        return None


def _parse_date(value: Any) -> date | None:
    if isinstance(value, date):
        return value
    if isinstance(value, str) and value.strip():
        try:
            return date.fromisoformat(value.strip())
        except ValueError:
            return None
    return None
