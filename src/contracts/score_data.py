"""
Module: score_data
Architecture: M7 Scorer output contract consumed by M8 Report Builder.

Defines the final score payload generated for one entity and one pipeline run.
"""
from __future__ import annotations

from dataclasses import dataclass, field


@dataclass
class ScoreData:
  """Final scoring output for one entity in a pipeline run."""

  pipeline_run_id: str
  entity_id: str
  final_score: float = 0.0
  financial_strength_score: float = 0.0
  outcome_strength_score: float = 0.0
  financial_model_used: str = ""
  outcome_source: str = ""
  accreditation_multiplier: float = 1.0
  vintage_multiplier: float = 1.0
  city_multiplier: float = 1.0
  score_explanation: list[str] = field(default_factory=list)
  contributing_fields: dict[str, str] = field(default_factory=dict)
  rating: str = ""
  remarks: str = ""
  gatekeeper_status: str = ""
