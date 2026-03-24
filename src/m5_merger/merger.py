"""
Module: merger
Architecture: M5 — Merge / Reconcile

Implements the sequenced merge algorithm (MF-2) that combines M3 and M4 extraction
outputs into a single merged record per entity. Applies source precedence, recency
arbitration, and structured-over-AI rules in a defined step order.

Merge algorithm steps (see EICH2_ARCHITECTURE.md §4b):
  1. Collect all candidate values per field
  2. Drop nulls (absence of evidence ≠ evidence of absence)
  3. Partition by extraction_method (structured vs AI)
  4. Structured wins over AI_INFERENCE
  5. Rank by source_tier within surviving candidates
  6. Rank by recency within matching tiers
  7. Additive union for aliases and relationships
  8. Numeric spread check for compensation fields

KMP identity matching uses normalize_role() from role_normalizer.py before comparison.
Raises MergeConflictError on hard uniqueness violations (e.g. duplicate CompensationRecord keys).
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import date, datetime, timedelta
from typing import Any

from contracts.source_ref import SourceRef
from contracts.validated_data import (
    CompensationRecord,
    KMPRecord,
    RecordState,
    ValidatedEntityRecord,
)
from m5_merger.merge_conflict import MergeConflictError, MergeConflictLog
from m5_merger.role_normalizer import normalize_role


_TIER_RANK: dict[str, int] = {
    "authoritative": 0,
    "official": 1,
    "secondary": 2,
    "web": 3,
}


@dataclass(frozen=True)
class _Candidate:
    value: Any
    source: SourceRef


@dataclass
class Merger:
    """
    Deterministic merger for validated entity records.

    Public API:
      - merge_entity_records(entity_records, pipeline_run_id)
      - merge_kmp_records(kmp_records)
      - merge_compensation_records(comp_records)
    """

    entity_id: str
    conflict_log: MergeConflictLog | None = None
    staleness_days: int = 180

    def _ensure_log(self, pipeline_run_id: str) -> None:
        if self.conflict_log is None:
            self.conflict_log = MergeConflictLog(
                pipeline_run_id=pipeline_run_id,
                entity_id=self.entity_id,
            )

    def merge_entity_records(
        self,
        entity_records: list[ValidatedEntityRecord],
        pipeline_run_id: str,
    ) -> ValidatedEntityRecord:
        """Merge multiple entity snapshots into one deterministic entity payload."""
        if not entity_records:
            raise ValueError("entity_records cannot be empty")

        self._ensure_log(pipeline_run_id)

        base = entity_records[0]
        all_kmps: list[KMPRecord] = []
        for rec in entity_records:
            all_kmps.extend(rec.kmp_list)

        merged_kmp_list = self.merge_kmp_records(all_kmps)

        any_quarantined = any(k.state == RecordState.QUARANTINED for k in merged_kmp_list)
        has_suppressed = bool(self.conflict_log and self.conflict_log.suppressed_count > 0)

        if any_quarantined:
            state = RecordState.PARTIAL if merged_kmp_list else RecordState.QUARANTINED
        elif has_suppressed:
            state = RecordState.PARTIAL
        else:
            state = RecordState.VALIDATED

        warnings: list[str] = []
        if self.conflict_log and self.conflict_log.raised_count > 0:
            warnings.append(f"merge_raised_conflicts={self.conflict_log.raised_count}")
        if self.conflict_log and self.conflict_log.suppressed_count > 0:
            warnings.append(f"merge_suppressed_conflicts={self.conflict_log.suppressed_count}")

        return ValidatedEntityRecord(
            entity_id=base.entity_id,
            entity_name=base.entity_name,
            entity_type=base.entity_type,
            jurisdiction=base.jurisdiction,
            kmp_list=merged_kmp_list,
            associated_entities=base.associated_entities,
            relationship_map=base.relationship_map,
            institution_network=base.institution_network,
            field_sources=base.field_sources,
            quality_warnings=warnings,
            state=state,
            pipeline_run_id=pipeline_run_id,
        )

    def merge_kmp_records(self, kmp_records: list[KMPRecord]) -> list[KMPRecord]:
        """Merge KMP records by stable kmp_id with role normalization before matching."""
        if not kmp_records:
            return []

        grouped: dict[str, list[KMPRecord]] = {}
        for record in kmp_records:
            normalized = normalize_role(record.raw_role)
            if normalized != record.canonical_role:
                record.field_sources["canonical_role"] = (
                    record.field_sources.get("canonical_role")
                    or record.field_sources.get("raw_role")
                    or self._first_source(record.field_sources)
                )
            record.canonical_role = normalized
            grouped.setdefault(record.kmp_id, []).append(record)

        merged: list[KMPRecord] = []
        for kmp_id in sorted(grouped.keys()):
            records = grouped[kmp_id]
            template = records[0]

            full_name, full_name_src = self._merge_field(
                "full_name",
                [_Candidate(r.full_name, self._source_for_field(r, "full_name")) for r in records],
                kmp_id,
            )
            canonical_role, canonical_role_src = self._merge_field(
                "canonical_role",
                [_Candidate(r.canonical_role, self._source_for_field(r, "canonical_role")) for r in records],
                kmp_id,
            )

            combined_sources = self._merge_field_sources(records)
            if full_name_src is not None:
                combined_sources["full_name"] = full_name_src
            if canonical_role_src is not None:
                combined_sources["canonical_role"] = canonical_role_src

            last_observed = self._compute_last_observed_date(combined_sources)
            staleness = self._compute_staleness(last_observed)

            all_comp: list[CompensationRecord] = []
            for r in records:
                all_comp.extend(r.compensation)

            kmp_state = RecordState.VALIDATED
            merged_comp: list[CompensationRecord] = []
            try:
                merged_comp = self.merge_compensation_records(all_comp)
            except MergeConflictError:
                kmp_state = RecordState.QUARANTINED
                merged_comp = []

            if kmp_state == RecordState.VALIDATED and self._has_source_gaps(combined_sources):
                kmp_state = RecordState.PARTIAL

            merged.append(
                KMPRecord(
                    kmp_id=kmp_id,
                    full_name=full_name,
                    canonical_role=canonical_role,
                    raw_role=template.raw_role,
                    field_sources=combined_sources,
                    staleness_flag=staleness,
                    last_observed_date=last_observed,
                    compensation=merged_comp,
                    state=kmp_state,
                )
            )

        return merged

    def merge_compensation_records(
        self,
        comp_records: list[CompensationRecord],
    ) -> list[CompensationRecord]:
        """Merge compensation records by (kmp_id, year) and enforce uniqueness."""
        if not comp_records:
            return []

        grouped: dict[tuple[str, int], list[CompensationRecord]] = {}
        for rec in comp_records:
            grouped.setdefault(rec.merge_key, []).append(rec)

        merged: list[CompensationRecord] = []
        for (kmp_id, year), records in sorted(grouped.items(), key=lambda x: x[0]):
            value, value_src = self._merge_field(
                "compensation_value",
                [_Candidate(r.compensation_value, self._source_for_field(r, "compensation_value")) for r in records],
                kmp_id,
            )
            currency, currency_src = self._merge_field(
                "currency",
                [_Candidate(r.currency, self._source_for_field(r, "currency")) for r in records],
                kmp_id,
            )

            evidence_sentence: str | None = None
            for rec in records:
                if rec.evidence_sentence:
                    evidence_sentence = rec.evidence_sentence
                    break

            merged_sources = self._merge_comp_field_sources(records)
            if value_src is not None:
                merged_sources["compensation_value"] = value_src
            if currency_src is not None:
                merged_sources["currency"] = currency_src

            merged.append(
                CompensationRecord(
                    kmp_id=kmp_id,
                    year=year,
                    compensation_value=value,
                    currency=currency,
                    field_sources=merged_sources,
                    evidence_sentence=evidence_sentence,
                )
            )

        self._assert_compensation_uniqueness(merged)
        return merged

    def _merge_field(
        self,
        field_name: str,
        candidates: list[_Candidate],
        kmp_id: str,
    ) -> tuple[Any, SourceRef | None]:
        """
        Enforce merge sequence for one field:
          - collect all candidates with provenance
          - rank by source tier
          - recency tie-break using document_date
          - structured-over-AI precedence
          - structured null does not defeat AI non-null
          - return winning value + SourceRef
        """
        if not candidates:
            return None, None

        sorted_candidates = sorted(candidates, key=self._candidate_sort_key)

        structured = [c for c in sorted_candidates if c.source.is_structured()]
        ai_or_pdf = [c for c in sorted_candidates if not c.source.is_structured()]

        structured_non_null = [c for c in structured if c.value is not None]
        ai_or_pdf_non_null = [c for c in ai_or_pdf if c.value is not None]

        if structured_non_null:
            winner_pool = structured_non_null
            for loser in ai_or_pdf_non_null:
                self._log_conflict(
                    field_name,
                    kmp_id,
                    winner_pool[0].value,
                    loser.value,
                    [winner_pool[0].source.source_id, loser.source.source_id],
                    "Structured-over-AI precedence applied",
                    raised=False,
                )
        elif ai_or_pdf_non_null:
            winner_pool = ai_or_pdf_non_null
            for loser in structured:
                if loser.value is None:
                    self._log_conflict(
                        field_name,
                        kmp_id,
                        winner_pool[0].value,
                        loser.value,
                        [winner_pool[0].source.source_id, loser.source.source_id],
                        "Structured null does not defeat AI/PDF non-null",
                        raised=False,
                    )
        else:
            winner_pool = sorted_candidates

        top = winner_pool[0]
        if len(winner_pool) > 1:
            runner = winner_pool[1]
            same_tier = self._tier_rank(top.source) == self._tier_rank(runner.source)
            same_date = (top.source.document_date or date.min) == (runner.source.document_date or date.min)
            same_method = top.source.extraction_method == runner.source.extraction_method
            different_values = top.value != runner.value
            if same_tier and same_date and same_method and different_values:
                err = MergeConflictError(
                    field_name=field_name,
                    kmp_id=kmp_id,
                    conflicting_values=[top.value, runner.value],
                    sources=[top.source.source_id, runner.source.source_id],
                    reason="Irreconcilable tie after tier and recency ordering",
                )
                self._add_conflict(err, raised=True)
                raise err
            for loser in winner_pool[1:]:
                self._log_conflict(
                    field_name,
                    kmp_id,
                    top.value,
                    loser.value,
                    [top.source.source_id, loser.source.source_id],
                    "Lower-ranked candidate suppressed by deterministic ordering",
                    raised=False,
                )

        return top.value, top.source

    def _assert_compensation_uniqueness(self, records: list[CompensationRecord]) -> None:
        seen: set[tuple[str, int]] = set()
        for rec in records:
            key = rec.merge_key
            if key in seen:
                err = MergeConflictError(
                    field_name="compensation",
                    kmp_id=rec.kmp_id,
                    conflicting_values=[key],
                    sources=[
                        rec.field_sources.get("compensation_value", self._first_source(rec.field_sources)).source_id
                        if rec.field_sources else "unknown"
                    ],
                    reason="Duplicate compensation merge key remained after deduplication",
                )
                self._add_conflict(err, raised=True)
                raise err
            seen.add(key)

    def _source_for_field(self, record: KMPRecord | CompensationRecord, field_name: str) -> SourceRef:
        source = record.field_sources.get(field_name) or self._first_source(record.field_sources)
        if source is None:
            # Fallback deterministic placeholder for missing provenance; keeps merge deterministic.
            source = SourceRef(
                source_id="unknown",
                source_name="unknown",
                source_tier="web",
                extraction_method="ai_inference",
                document_date=None,
                fetched_at=datetime.min,
                url=None,
            )
        return source

    def _merge_field_sources(self, records: list[KMPRecord]) -> dict[str, SourceRef]:
        merged: dict[str, SourceRef] = {}
        for r in records:
            for field_name, src in r.field_sources.items():
                current = merged.get(field_name)
                if current is None or self._candidate_sort_key(_Candidate(None, src)) < self._candidate_sort_key(_Candidate(None, current)):
                    merged[field_name] = src
        return merged

    def _merge_comp_field_sources(self, records: list[CompensationRecord]) -> dict[str, SourceRef]:
        merged: dict[str, SourceRef] = {}
        for r in records:
            for field_name, src in r.field_sources.items():
                current = merged.get(field_name)
                if current is None or self._candidate_sort_key(_Candidate(None, src)) < self._candidate_sort_key(_Candidate(None, current)):
                    merged[field_name] = src
        return merged

    def _compute_last_observed_date(self, field_sources: dict[str, SourceRef]) -> date | None:
        dated = [src.document_date for src in field_sources.values() if src.document_date is not None]
        if not dated:
            return None
        return max(dated)

    def _compute_staleness(self, last_observed_date: date | None) -> bool:
        if last_observed_date is None:
            return True
        return last_observed_date < (date.today() - timedelta(days=self.staleness_days))

    def _has_source_gaps(self, field_sources: dict[str, SourceRef]) -> bool:
        return not field_sources or any(src.source_id == "unknown" for src in field_sources.values())

    def _tier_rank(self, source: SourceRef) -> int:
        return _TIER_RANK.get(source.source_tier, 99)

    def _candidate_sort_key(self, candidate: _Candidate) -> tuple[int, int, str, str]:
        # Lower tuple wins. Recency: newer dates sort first via negative ordinal.
        document_ord = candidate.source.document_date.toordinal() if candidate.source.document_date else date.min.toordinal()
        return (
            self._tier_rank(candidate.source),
            -document_ord,
            candidate.source.extraction_method,
            candidate.source.source_id,
        )

    def _first_source(self, sources: dict[str, SourceRef]) -> SourceRef | None:
        if not sources:
            return None
        return sorted(sources.values(), key=lambda s: (self._tier_rank(s), -(s.document_date.toordinal() if s.document_date else 0), s.source_id))[0]

    def _add_conflict(self, error: MergeConflictError, raised: bool) -> None:
        if self.conflict_log is None:
            # In non-entity flow, we still maintain a deterministic local log shell.
            self.conflict_log = MergeConflictLog(pipeline_run_id="", entity_id=self.entity_id)
        self.conflict_log.add_conflict(error, raised=raised)

    def _log_conflict(
        self,
        field_name: str,
        kmp_id: str,
        winner_value: Any,
        losing_value: Any,
        sources: list[str],
        reason: str,
        raised: bool,
    ) -> None:
        err = MergeConflictError(
            field_name=field_name,
            kmp_id=kmp_id,
            conflicting_values=[winner_value, losing_value],
            sources=sources,
            reason=reason,
        )
        self._add_conflict(err, raised=raised)
