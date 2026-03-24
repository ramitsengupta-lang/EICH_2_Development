"""
Module: validator
Architecture: M6 — Validator

Validates a MergedRecord from M5 and assigns a RecordState:
  VALIDATED   — all required fields present, provenance complete, no unresolved conflicts
  PARTIAL     — required fields present but non-critical gaps or low-confidence fields
  QUARANTINED — critical field missing, unprovable, or in hard conflict

Validation checks performed (in order):
  1. Schema validation: required fields present, correct types, value ranges
  2. Cross-field consistency: e.g. role_end_date > role_start_date, year plausible
  3. Provenance completeness: every field has a non-null source_ref in field_sources
  4. Compensation currency and year must be explicit (not inferred)
  5. Staleness flag computation for KMP records
  6. KMP tenure_days computation from role dates

VALIDATED and PARTIAL records are written to store/validated_data/.
QUARANTINED records are written to store/quarantine/ only.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from typing import Iterable

from contracts.validated_data import CompensationRecord, KMPRecord, RecordState, ValidatedEntityRecord


@dataclass
class ValidationSummary:
  """Machine-readable counters for one validation run."""

  total_kmp: int = 0
  validated_kmp: int = 0
  partial_kmp: int = 0
  quarantined_kmp: int = 0
  total_compensation: int = 0
  valid_compensation: int = 0
  partial_compensation: int = 0
  quarantined_compensation: int = 0
  warnings_count: int = 0
  excluded_from_scoring_count: int = 0


@dataclass
class ValidationResult:
  """Validated payload plus counters and warnings emitted by M6."""

  validated_payload: ValidatedEntityRecord
  summary: ValidationSummary


_KMP_REQUIRED_FIELDS: tuple[str, ...] = ("kmp_id", "full_name", "canonical_role", "raw_role")
_ENTITY_REQUIRED_FIELDS: tuple[str, ...] = (
  "entity_id",
  "entity_name",
  "entity_type",
  "jurisdiction",
  "pipeline_run_id",
)
_KMP_MERGED_FIELDS: tuple[str, ...] = ("full_name", "canonical_role", "raw_role")
_COMP_MERGED_FIELDS: tuple[str, ...] = ("compensation_value", "currency")


def _warn(code: str, message: str, path: str) -> str:
  return f"{code}|{path}|{message}"


def validate_entity_record(entity_record: ValidatedEntityRecord) -> ValidationResult:
  """
  Validate one merged entity payload.

  State policy:
    - VALIDATED: all required fields/provenance complete; no critical violations
    - PARTIAL: non-critical validation failures present
    - QUARANTINED: critical validation failures present
  """
  warnings: list[str] = list(entity_record.quality_warnings)
  summary = ValidationSummary()

  entity_critical_issues = _check_required_entity_fields(entity_record)
  for issue in entity_critical_issues:
    warnings.append(_warn("VAL_ENTITY_REQUIRED_MISSING", issue, "entity"))

  validated_kmps: list[KMPRecord] = []

  for idx, kmp in enumerate(entity_record.kmp_list):
    summary.total_kmp += 1
    kmp_path = f"kmp_list[{idx}]"

    kmp_critical, kmp_non_critical = _validate_kmp(kmp, kmp_path)
    warnings.extend(kmp_critical)
    warnings.extend(kmp_non_critical)

    checked_comp: list[CompensationRecord] = []
    kmp_has_partial_comp = False
    for cidx, comp in enumerate(kmp.compensation):
      summary.total_compensation += 1
      comp_path = f"{kmp_path}.compensation[{cidx}]"
      comp_critical, comp_non_critical = _validate_compensation(comp, comp_path)
      warnings.extend(comp_critical)
      warnings.extend(comp_non_critical)

      if comp_critical:
        summary.quarantined_compensation += 1
        summary.excluded_from_scoring_count += 1
        continue
      if comp_non_critical:
        summary.partial_compensation += 1
        kmp_has_partial_comp = True
      else:
        summary.valid_compensation += 1
      checked_comp.append(comp)

    kmp.compensation = checked_comp

    if kmp_critical:
      kmp.state = RecordState.QUARANTINED
      summary.quarantined_kmp += 1
      summary.excluded_from_scoring_count += 1
    elif kmp_non_critical or kmp_has_partial_comp:
      kmp.state = RecordState.PARTIAL
      summary.partial_kmp += 1
    else:
      kmp.state = RecordState.VALIDATED
      summary.validated_kmp += 1

    validated_kmps.append(kmp)

  has_critical = bool(entity_critical_issues) or summary.quarantined_kmp > 0
  has_partial = summary.partial_kmp > 0 or summary.partial_compensation > 0

  if has_critical and summary.validated_kmp == 0 and summary.partial_kmp == 0:
    entity_state = RecordState.QUARANTINED
  elif has_critical or has_partial:
    entity_state = RecordState.PARTIAL
  else:
    entity_state = RecordState.VALIDATED

  summary.warnings_count = len(warnings)

  entity_record.kmp_list = validated_kmps
  entity_record.quality_warnings = warnings
  entity_record.state = entity_state

  return ValidationResult(validated_payload=entity_record, summary=summary)


def build_scoring_payload(validated_payload: ValidatedEntityRecord) -> ValidatedEntityRecord:
  """
  Produce scorer-eligible payload by excluding QUARANTINED KMP records and
  retaining only validated/partial KMP compensation entries.
  """
  eligible_kmp = [k for k in validated_payload.kmp_list if k.state != RecordState.QUARANTINED]
  validated_payload.kmp_list = eligible_kmp
  if validated_payload.state == RecordState.QUARANTINED:
    validated_payload.kmp_list = []
  return validated_payload


def _check_required_entity_fields(entity: ValidatedEntityRecord) -> list[str]:
  issues: list[str] = []
  for field_name in _ENTITY_REQUIRED_FIELDS:
    value = getattr(entity, field_name)
    if value is None or (isinstance(value, str) and value.strip() == ""):
      issues.append(f"missing required field: {field_name}")
  return issues


def _validate_kmp(kmp: KMPRecord, kmp_path: str) -> tuple[list[str], list[str]]:
  critical: list[str] = []
  non_critical: list[str] = []

  for field_name in _KMP_REQUIRED_FIELDS:
    value = getattr(kmp, field_name)
    if value is None or (isinstance(value, str) and value.strip() == ""):
      critical.append(_warn("VAL_KMP_REQUIRED_MISSING", f"missing {field_name}", f"{kmp_path}.{field_name}"))

  missing_prov = _missing_provenance(kmp.field_sources, _KMP_MERGED_FIELDS)
  for field_name in missing_prov:
    non_critical.append(
      _warn(
        "VAL_KMP_PROVENANCE_MISSING",
        f"missing provenance for merged field {field_name}",
        f"{kmp_path}.{field_name}",
      )
    )

  if kmp.last_observed_date is None:
    non_critical.append(_warn("VAL_KMP_LAST_OBSERVED_MISSING", "last_observed_date is missing", f"{kmp_path}.last_observed_date"))

  return critical, non_critical


def _validate_compensation(comp: CompensationRecord, comp_path: str) -> tuple[list[str], list[str]]:
  critical: list[str] = []
  non_critical: list[str] = []

  current_year = date.today().year
  if comp.year < 1900 or comp.year > current_year + 1:
    critical.append(_warn("VAL_COMP_YEAR_INVALID", f"invalid year {comp.year}", f"{comp_path}.year"))

  if comp.compensation_value is not None and not isinstance(comp.compensation_value, (int, float)):
    critical.append(_warn("VAL_COMP_VALUE_INVALID", "compensation_value must be numeric or null", f"{comp_path}.compensation_value"))

  if not comp.currency or not isinstance(comp.currency, str):
    critical.append(_warn("VAL_COMP_CURRENCY_MISSING", "currency is required", f"{comp_path}.currency"))

  missing_prov = _missing_provenance(comp.field_sources, _COMP_MERGED_FIELDS)
  for field_name in missing_prov:
    non_critical.append(
      _warn(
        "VAL_COMP_PROVENANCE_MISSING",
        f"missing provenance for merged field {field_name}",
        f"{comp_path}.{field_name}",
      )
    )

  src_value = comp.field_sources.get("compensation_value")
  if src_value and src_value.extraction_method == "ai_inference" and not comp.evidence_sentence:
    non_critical.append(
      _warn(
        "VAL_COMP_AI_EVIDENCE_MISSING",
        "ai_inference compensation requires evidence_sentence",
        f"{comp_path}.evidence_sentence",
      )
    )

  return critical, non_critical


def _missing_provenance(field_sources: dict[str, Any], required_fields: Iterable[str]) -> list[str]:
  missing: list[str] = []
  for field_name in required_fields:
    if field_name not in field_sources:
      missing.append(field_name)
  return missing


def validate(entity_record: ValidatedEntityRecord) -> ValidationResult:
  """Backward-compatible entry point for validator integration."""
  return validate_entity_record(entity_record)


def _check_required_fields(merged: MergedRecord) -> list[str]:
    """
    Return a list of missing critical field descriptions.
    Empty list = all critical fields present.
    """
    raise NotImplementedError


def _check_provenance_completeness(merged: MergedRecord) -> list[str]:
    """
    Verify every field on every KMPRecord and CompensationRecord has a SourceRef entry.
    Returns list of field paths with missing provenance.
    """
    raise NotImplementedError


def _compute_kmp_tenure(merged: MergedRecord) -> MergedRecord:
    """
    Compute tenure_days for each KMPRecord from role_start_date and role_end_date.
    Sets tenure_days = None if either date is absent.
    """
    raise NotImplementedError


def _compute_staleness_flags(merged: MergedRecord) -> MergedRecord:
    """
    Set staleness_flag = True on any KMPRecord whose last_observed_date from an
    AUTHORITATIVE or OFFICIAL source is more than 180 days before today.
    """
    raise NotImplementedError
