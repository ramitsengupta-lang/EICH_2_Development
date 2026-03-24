"""
Module: scorer
Architecture: M7 — Scorer

Computes dimension scores and a composite score from a ValidatedEntityRecord.
Reads exclusively from validated_data; has zero imports from M2, M3, or M4.

Score penalty rules (both axes applied independently and additively, capped at 0.40):
  source_tier penalties:      AUTHORITATIVE=0.00, OFFICIAL=0.05, SECONDARY=0.15, WEB=0.30
  extraction_method penalties: STRUCTURED=0.00, PDF_PARSE=0.05, AI_INFERENCE=0.20

Hard rules:
  - Only consumes records with record_state = VALIDATED.
  - Any field with confidence < 0.5 contributes 0 to data_completeness.
  - ScoreData is immutable once produced for a pipeline_run_id.
  - Score changes across runs are logged in score_delta_log (Phase 2).
"""
from __future__ import annotations

from dataclasses import dataclass

from contracts.validated_data import RecordState, ValidatedEntityRecord
from m6_validator.validator import ValidationResult, build_scoring_payload
from contracts.score_data import ScoreData

# Source tier penalty multipliers
TIER_PENALTIES: dict[str, float] = {
    "authoritative": 0.00,
    "official":      0.05,
    "secondary":     0.15,
    "web":           0.30,
}

# Extraction method penalty multipliers
METHOD_PENALTIES: dict[str, float] = {
    "structured":   0.00,
    "pdf_parse":    0.05,
    "ai_inference": 0.20,
}

MAX_FIELD_PENALTY: float = 0.40

PARTIAL_ENTITY_PENALTY: float = 0.35
PARTIAL_KMP_PENALTY: float = 0.30


@dataclass
class _DimensionResult:
    score: float
    explanation: str
    contributing_field: str


def score(validated_data: ValidatedEntityRecord) -> ScoreData:
    """
    Compute ScoreData from validated payload only.

    Gating:
      - QUARANTINED entity is excluded from scoring.
      - VALIDATED and PARTIAL entities are scored.
      - QUARANTINED KMP records are fully excluded from score inputs.
    """
    if validated_data.state == RecordState.QUARANTINED:
        raise ValueError("QUARANTINED entity cannot be scored")

    payload = build_scoring_payload(validated_data)

    financial = _score_financial_strength(payload)
    outcome = _score_outcome_strength(payload)

    final_score = round((financial.score + outcome.score) / 2.0, 4)
    rating = _rating_from_score(final_score)

    explanations = sorted([
        f"FINANCIAL|{financial.explanation}",
        f"OUTCOME|{outcome.explanation}",
        f"FINAL|composite=average(financial,outcome)={final_score:.4f}",
    ])

    remarks = "state=PARTIAL" if payload.state == RecordState.PARTIAL else "state=VALIDATED"

    return ScoreData(
        pipeline_run_id=payload.pipeline_run_id,
        entity_id=payload.entity_id,
        final_score=final_score,
        financial_strength_score=financial.score,
        outcome_strength_score=outcome.score,
        financial_model_used="deterministic_compensation_v1",
        outcome_source="kmp_role_and_state",
        accreditation_multiplier=1.0,
        vintage_multiplier=1.0,
        city_multiplier=1.0,
        score_explanation=explanations,
        contributing_fields={
            "financial_strength_score": financial.contributing_field,
            "outcome_strength_score": outcome.contributing_field,
            "final_score": "financial_strength_score,outcome_strength_score",
        },
        rating=rating,
        remarks=remarks,
    )


def score_from_validation_result(result: ValidationResult) -> ScoreData:
    """Deterministic integration step: validator output -> scorer input."""
    return score(result.validated_payload)


def _compute_field_penalty(source_tier: str, extraction_method: str) -> float:
    """
    Compute the additive penalty for a single field based on its two provenance axes.
    Result is capped at MAX_FIELD_PENALTY.
    """
    tier_penalty = TIER_PENALTIES.get(source_tier, TIER_PENALTIES["web"])
    method_penalty = METHOD_PENALTIES.get(extraction_method, METHOD_PENALTIES["ai_inference"])
    return min(MAX_FIELD_PENALTY, tier_penalty + method_penalty)


def _score_financial_strength(validated_data: ValidatedEntityRecord) -> _DimensionResult:
    """Score from compensation values using provenance-derived penalties."""
    values: list[float] = []
    penalties: list[float] = []
    partial_hits = 0

    for kmp in validated_data.kmp_list:
        if kmp.state == RecordState.QUARANTINED:
            continue
        if kmp.state == RecordState.PARTIAL:
            partial_hits += 1
        for comp in kmp.compensation:
            if comp.compensation_value is None:
                continue
            src = comp.field_sources.get("compensation_value")
            if src is None:
                # No provenance should have been downgraded by validator; apply worst-case if present.
                penalties.append(MAX_FIELD_PENALTY)
            else:
                penalties.append(_compute_field_penalty(src.source_tier, src.extraction_method))
            values.append(float(comp.compensation_value))

    if not values:
        return _DimensionResult(
            score=0.0,
            explanation="no eligible compensation values",
            contributing_field="kmp_list[].compensation[].compensation_value",
        )

    avg_value = sum(values) / len(values)
    avg_penalty = sum(penalties) / len(penalties) if penalties else 0.0

    base = min(100.0, (avg_value / 1000.0))
    entity_partial_penalty = PARTIAL_ENTITY_PENALTY if validated_data.state == RecordState.PARTIAL else 0.0
    kmp_partial_penalty = min(0.30, partial_hits * PARTIAL_KMP_PENALTY / max(1, len(validated_data.kmp_list)))
    adjusted = base * (1.0 - avg_penalty) * (1.0 - entity_partial_penalty) * (1.0 - kmp_partial_penalty)

    explanation = (
        f"avg_value={avg_value:.4f};base={base:.4f};avg_source_penalty={avg_penalty:.4f};"
        f"entity_partial_penalty={entity_partial_penalty:.4f};kmp_partial_penalty={kmp_partial_penalty:.4f};"
        f"adjusted={adjusted:.4f}"
    )
    return _DimensionResult(
        score=round(max(0.0, min(100.0, adjusted)), 4),
        explanation=explanation,
        contributing_field="kmp_list[].compensation[].compensation_value",
    )


def _score_outcome_strength(validated_data: ValidatedEntityRecord) -> _DimensionResult:
    """Score from eligible KMP coverage and role provenance quality."""
    eligible = [k for k in validated_data.kmp_list if k.state != RecordState.QUARANTINED]
    if not eligible:
        return _DimensionResult(
            score=0.0,
            explanation="no eligible kmp records",
            contributing_field="kmp_list[].canonical_role",
        )

    role_penalties: list[float] = []
    partial_hits = 0
    for kmp in eligible:
        if kmp.state == RecordState.PARTIAL:
            partial_hits += 1
        src = kmp.field_sources.get("canonical_role")
        if src is None:
            role_penalties.append(MAX_FIELD_PENALTY)
        else:
            role_penalties.append(_compute_field_penalty(src.source_tier, src.extraction_method))

    base = min(100.0, float(len(eligible) * 20))
    avg_role_penalty = sum(role_penalties) / len(role_penalties)
    entity_partial_penalty = PARTIAL_ENTITY_PENALTY if validated_data.state == RecordState.PARTIAL else 0.0
    kmp_partial_penalty = min(0.30, partial_hits * PARTIAL_KMP_PENALTY / len(eligible))
    adjusted = base * (1.0 - avg_role_penalty) * (1.0 - entity_partial_penalty) * (1.0 - kmp_partial_penalty)

    explanation = (
        f"eligible_kmp={len(eligible)};base={base:.4f};avg_role_penalty={avg_role_penalty:.4f};"
        f"entity_partial_penalty={entity_partial_penalty:.4f};kmp_partial_penalty={kmp_partial_penalty:.4f};"
        f"adjusted={adjusted:.4f}"
    )
    return _DimensionResult(
        score=round(max(0.0, min(100.0, adjusted)), 4),
        explanation=explanation,
        contributing_field="kmp_list[].canonical_role",
    )


def _compute_composite(dimension_scores: dict[str, float], method: str) -> float:
    """Combine dimension scores into a composite 0.0–100.0 score using the given method."""
    if not dimension_scores:
        return 0.0
    if method != "average_v1":
        raise ValueError(f"Unsupported composite method: {method}")
    return round(sum(dimension_scores.values()) / len(dimension_scores), 4)


def _rating_from_score(score_value: float) -> str:
    if score_value >= 85:
        return "A"
    if score_value >= 70:
        return "B"
    if score_value >= 55:
        return "C"
    if score_value >= 40:
        return "D"
    return "E"
