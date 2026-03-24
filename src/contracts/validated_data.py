"""
Module: validated_data
Architecture: M6 Validator contract used downstream by M7 and M8.

Defines the validated entity data model with KMP and compensation structures.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date
from enum import Enum

from .source_ref import SourceRef


class RecordState(str, Enum):
    """Validation state assigned by M6 Validator."""

    VALIDATED = "VALIDATED"
    PARTIAL = "PARTIAL"
    QUARANTINED = "QUARANTINED"


@dataclass
class CompensationRecord:
    """Compensation record for one KMP in one year."""

    kmp_id: str
    year: int
    compensation_value: float | None = None
    currency: str = ""
    field_sources: dict[str, SourceRef] = field(default_factory=dict)
    evidence_sentence: str | None = None

    @property
    def merge_key(self) -> tuple[str, int]:
        """Composite merge key as required by MF-5."""
        return (self.kmp_id, self.year)


@dataclass
class KMPRecord:
    """Validated KMP record including source provenance and compensation history."""

    kmp_id: str
    full_name: str
    canonical_role: str
    raw_role: str
    field_sources: dict[str, SourceRef] = field(default_factory=dict)
    staleness_flag: bool = False
    last_observed_date: date | None = None
    compensation: list[CompensationRecord] = field(default_factory=list)
    state: RecordState = RecordState.VALIDATED


@dataclass
class ValidatedEntityRecord:
    """Top-level validated entity payload consumed by downstream modules."""

    entity_id: str
    entity_name: str
    entity_type: str
    jurisdiction: str
    kmp_list: list[KMPRecord] = field(default_factory=list)
    associated_entities: list[dict] = field(default_factory=list)
    relationship_map: list[dict] = field(default_factory=list)
    institution_network: list[dict] = field(default_factory=list)
    field_sources: dict[str, SourceRef] = field(default_factory=dict)
    quality_warnings: list[str] = field(default_factory=list)
    state: RecordState = RecordState.VALIDATED
    pipeline_run_id: str = ""
