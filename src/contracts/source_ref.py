"""
Module: source_ref
Architecture: Cross-cutting contract used by M2, M3, M4, M5, M6, and M7.

Defines SourceRef, the per-field provenance object attached to validated fields.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import date, datetime


_VALID_SOURCE_TIERS: set[str] = {"authoritative", "official", "secondary", "web"}
_VALID_EXTRACTION_METHODS: set[str] = {"structured", "pdf_parse", "ai_inference"}


@dataclass
class SourceRef:
  """Per-field provenance metadata for one extracted value."""

  source_id: str
  source_name: str
  source_tier: str
  extraction_method: str
  document_date: date | None = None
  fetched_at: datetime = datetime.min
  url: str | None = None

  def __post_init__(self) -> None:
    if self.source_tier not in _VALID_SOURCE_TIERS:
      raise ValueError(
        f"Invalid source_tier '{self.source_tier}'. "
        f"Expected one of {sorted(_VALID_SOURCE_TIERS)}"
      )
    if self.extraction_method not in _VALID_EXTRACTION_METHODS:
      raise ValueError(
        f"Invalid extraction_method '{self.extraction_method}'. "
        f"Expected one of {sorted(_VALID_EXTRACTION_METHODS)}"
      )

  def is_structured(self) -> bool:
    """Return True when extraction method is structured."""
    return self.extraction_method == "structured"

  def penalty_factor(self) -> float:
    """
    Return additive penalty on a 0.0–0.4 linear scale.

    Minimum case:
      authoritative + structured -> 0.0
    Maximum case:
      web + ai_inference -> 0.4
    """
    tier_rank = {
      "authoritative": 0,
      "official": 1,
      "secondary": 2,
      "web": 3,
    }[self.source_tier]
    method_rank = {
      "structured": 0,
      "pdf_parse": 1,
      "ai_inference": 2,
    }[self.extraction_method]

    normalized = ((tier_rank / 3.0) + (method_rank / 2.0)) / 2.0
    return round(0.4 * normalized, 6)
