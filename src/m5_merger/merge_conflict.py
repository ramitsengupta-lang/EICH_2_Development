"""
Module: merge_conflict
Architecture: M5 — Merge / Reconcile (error definitions)

Defines MergeConflictError and MergeConflictLog used by the merger to record
and surface unreconciled conflicts.
"""
from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any


class MergeConflictError(Exception):
    """Raised when values cannot be reconciled by merge policy."""

    def __init__(
        self,
        field_name: str,
        kmp_id: str,
        conflicting_values: list[Any],
        sources: list[str],
        reason: str,
    ) -> None:
        self.field_name = field_name
        self.kmp_id = kmp_id
        self.conflicting_values = list(conflicting_values)
        self.sources = list(sources)
        self.reason = reason
        super().__init__(self.__str__())

    def to_dict(self) -> dict[str, Any]:
        """Return a serialized representation for logs and reports."""
        return {
            "field_name": self.field_name,
            "kmp_id": self.kmp_id,
            "conflicting_values": self.conflicting_values,
            "sources": self.sources,
            "reason": self.reason,
        }

    def __str__(self) -> str:
        return (
            f"MergeConflictError(field_name={self.field_name!r}, "
            f"kmp_id={self.kmp_id!r}, sources={self.sources!r}, reason={self.reason!r})"
        )


@dataclass
class MergeConflictLog:
    """Run-scoped accumulator for merge conflict records."""

    pipeline_run_id: str
    entity_id: str
    conflicts: list[dict] = field(default_factory=list)
    raised_count: int = 0
    suppressed_count: int = 0

    def add_conflict(self, error: MergeConflictError, raised: bool) -> None:
        """Append a serialized conflict and update raised/suppressed counters."""
        entry = {
            "pipeline_run_id": self.pipeline_run_id,
            "entity_id": self.entity_id,
            "raised": raised,
            **error.to_dict(),
        }
        self.conflicts.append(entry)
        if raised:
            self.raised_count += 1
        else:
            self.suppressed_count += 1
