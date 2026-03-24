"""
Module: settings
Architecture: Config

Central configuration for the EICH 2 pipeline.
All tunable thresholds referenced by the architecture live here.
Environment-specific overrides are loaded from a .env file at startup.
"""
from __future__ import annotations

import os

# ---------------------------------------------------------------------------
# Evidence freshness
# ---------------------------------------------------------------------------

# Re-fetch evidence older than this many days
MAX_EVIDENCE_AGE_DAYS: int = int(os.getenv("MAX_EVIDENCE_AGE_DAYS", "90"))

# ---------------------------------------------------------------------------
# KMP staleness
# ---------------------------------------------------------------------------

# KMP with no AUTHORITATIVE or OFFICIAL source update beyond this threshold
# will have staleness_flag = True
KMP_STALENESS_THRESHOLD_DAYS: int = int(os.getenv("KMP_STALENESS_THRESHOLD_DAYS", "180"))

# ---------------------------------------------------------------------------
# Relationship over-link guard
# ---------------------------------------------------------------------------

MAX_DIRECT_DEGREE: int   = int(os.getenv("MAX_DIRECT_DEGREE", "10"))
MAX_INFERRED_DEGREE: int = int(os.getenv("MAX_INFERRED_DEGREE", "5"))

# ---------------------------------------------------------------------------
# Confidence thresholds
# ---------------------------------------------------------------------------

# Fields below this confidence contribute 0 to data_completeness in scoring
MIN_SCORING_CONFIDENCE: float = float(os.getenv("MIN_SCORING_CONFIDENCE", "0.5"))

# AI extractions above this threshold are accepted without mandatory review
AI_AUTO_ACCEPT_CONFIDENCE: float = float(os.getenv("AI_AUTO_ACCEPT_CONFIDENCE", "0.7"))

# AI compensation extractions below this threshold go to human review queue
COMPENSATION_REVIEW_CONFIDENCE: float = float(os.getenv("COMPENSATION_REVIEW_CONFIDENCE", "0.6"))

# ---------------------------------------------------------------------------
# Merge policy
# ---------------------------------------------------------------------------

# If compensation spread across Tier 1–2 sources exceeds this fraction of the
# winning value, review_flag is set on the ConflictRecord
COMPENSATION_SPREAD_THRESHOLD: float = float(os.getenv("COMPENSATION_SPREAD_THRESHOLD", "0.20"))

# ---------------------------------------------------------------------------
# Phase 1 feature flags
# ---------------------------------------------------------------------------

ENABLE_AI_EXTRACTION: bool           = os.getenv("ENABLE_AI_EXTRACTION", "true").lower() == "true"
ENABLE_INFERRED_RELATIONSHIPS: bool  = os.getenv("ENABLE_INFERRED_RELATIONSHIPS", "false").lower() == "true"

# ---------------------------------------------------------------------------
# Storage paths
# ---------------------------------------------------------------------------

EVIDENCE_STORE_PATH: str    = os.getenv("EVIDENCE_STORE_PATH", "data/evidence_store")
RAW_INPUTS_PATH: str        = os.getenv("RAW_INPUTS_PATH", "data/raw_inputs")
OUTPUT_PATH: str            = os.getenv("OUTPUT_PATH", "data/output")
VALIDATED_DATA_PATH: str    = os.getenv("VALIDATED_DATA_PATH", "data/output/validated_data")
SCORE_DATA_PATH: str        = os.getenv("SCORE_DATA_PATH", "data/output/score_data")
QUARANTINE_PATH: str        = os.getenv("QUARANTINE_PATH", "data/output/quarantine")
REPORTS_PATH: str           = os.getenv("REPORTS_PATH", "data/output/reports")

# ---------------------------------------------------------------------------
# CLI / trace artifact output
# ---------------------------------------------------------------------------

# Root directory for CLI-generated trace artifacts and run logs.
# Each pipeline run creates a sub-directory named after its run ID.
# Override with EICH2_OUTPUT_ROOT environment variable.
EICH2_OUTPUT_ROOT: str = os.getenv("EICH2_OUTPUT_ROOT", "logs")
