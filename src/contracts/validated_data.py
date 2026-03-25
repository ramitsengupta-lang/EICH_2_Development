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
    email: str = ""
    experience: str | None = None


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
    # Location & accreditation
    city: str = ""
    year_of_establishment: int | None = None
    regulatory_body: str = ""
    naac_grade: str = ""
    sanctioned_intake: int | None = None
    main_programs: list[str] = field(default_factory=list)
    # Governing body
    registered_address: str = ""
    governing_body_name: str = ""
    governing_body_type: str = ""
    governing_body_year_established: int | None = None
    governed_institutions: list[str] = field(default_factory=list)
    governing_body_trustees: list[dict] = field(default_factory=list)
    # Outcome
    placement_rate: float | None = None
    median_salary_lpa: float | None = None
    higher_studies: str | None = None
    top_recruiters: list[str] = field(default_factory=list)
    # Banking
    banking_opportunities: list[dict] = field(default_factory=list)
    # Report accuracy
    report_accuracy_overall: float | None = None
    report_accuracy_sections: dict[str, float] = field(default_factory=dict)
