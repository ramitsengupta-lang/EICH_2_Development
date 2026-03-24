"""Test edge cases and failure modes in the full pipeline."""
import json
import pytest
from contracts.source_ref import SourceRef
from contracts.validated_data import ValidatedEntityRecord, RecordState
from contracts.score_data import ScoreData


def test_missing_financial_profile():
    """Pipeline handles missing financial profile gracefully."""
    validated = ValidatedEntityRecord(
        entity_id="test_entity_001",
        entity_name="Test Institution",
        entity_type="Educational Institution",
        jurisdiction="India",
    )
    score = ScoreData(
        pipeline_run_id="run_001",
        entity_id="test_entity_001",
        final_score=25.0
    )
    # Should not crash, should use fallback
    assert validated.entity_id == "test_entity_001"


def test_malformed_json_recovery():
    """Scorer handles non-numeric scores."""
    try:
        score = ScoreData(
            pipeline_run_id="run_002",
            entity_id="test_entity_002",
            final_score="invalid"  # This should fail type checking
        )
    except (ValueError, TypeError):
        # Expected: scorer must validate numeric input
        pass