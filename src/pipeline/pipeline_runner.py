"""
Module: pipeline_runner
Architecture: Orchestration layer

Orchestrates the full EICH 2 pipeline by invoking M1 through M8 in sequence.
Passes outputs between modules according to the defined contracts.
Handles per-entity run lifecycle: start, checkpoint, completion, error routing.

Pipeline sequence:
  M1 Identifier → M2 Source Acquirer → M3 Structured Extractor →
  M4 AI Extractor → M5 Merger → M6 Validator → M7 Scorer → M8 Report Builder
"""
from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime
from typing import Any, Callable

from contracts.validated_data import RecordState, ValidatedEntityRecord


@dataclass
class PipelineConfig:
    """Runtime configuration passed to each module."""
    entity_id: str
    run_id: str                     # UUID assigned before pipeline starts
    max_evidence_age_days: int = 90
    enable_ai_extraction: bool = True
    enable_inferred_relationships: bool = False  # off in Phase 1


@dataclass
class PipelineResult:
    """Structured result returned by PipelineRunner.run()."""

    pipeline_run_id: str
    validated_data: ValidatedEntityRecord | None
    score_data: Any | None
    report: Any | None
    validation_summary: Any | None
    warnings: list[str] = field(default_factory=list)
    status: str = "failed"  # success | partial | quarantined | failed
    error: dict[str, Any] | None = None
    stage_sequence: list[str] = field(default_factory=list)
    stage_timings: dict[str, float] = field(default_factory=dict)


class PipelineStageError(Exception):
    """Raised when an individual pipeline stage fails."""

    def __init__(self, stage: str, reason: str, details: dict[str, Any] | None = None) -> None:
        self.stage = stage
        self.reason = reason
        self.details = details or {}
        super().__init__(f"{stage} failed: {reason}")


class PipelineExecutionError(Exception):
    """Raised when orchestration cannot continue due to fatal stage failure."""

    def __init__(self, stage: str, reason: str, details: dict[str, Any] | None = None) -> None:
        self.stage = stage
        self.reason = reason
        self.details = details or {}
        super().__init__(f"Pipeline failed at {stage}: {reason}")


@dataclass
class PipelineRunner:
    """
    Deterministic M1→M8 orchestrator with explicit dependency injection.

    Stage dependencies can be passed as module-like objects or custom test doubles.
    """

    identifier_stage: Any = None
    source_acquirer_stage: Any = None
    structured_extractor_stage: Any = None
    ai_extractor_stage: Any = None
    merger_stage_factory: Callable[[str], Any] | None = None
    validator_stage: Any = None
    scorer_stage: Any = None
    report_builder_stage: Any = None
    clock: Callable[[], datetime] = datetime.utcnow

    def __post_init__(self) -> None:
        self._resolve_default_stages()

    def _resolve_default_stages(self) -> None:
        # Lazy defaults avoid import-time coupling; DI remains first-class.
        if self.identifier_stage is None:
            from m1_identifier import identifier as m1_identifier
            self.identifier_stage = m1_identifier
        if self.source_acquirer_stage is None:
            from m2_source_acquirer import source_acquirer as m2_source_acquirer
            self.source_acquirer_stage = m2_source_acquirer
        if self.structured_extractor_stage is None:
            from m3_structured_extractor import structured_extractor as m3_structured_extractor
            self.structured_extractor_stage = m3_structured_extractor
        if self.ai_extractor_stage is None:
            from m4_ai_extractor import ai_extractor as m4_ai_extractor
            self.ai_extractor_stage = m4_ai_extractor
        if self.merger_stage_factory is None:
            from m5_merger.merger import Merger
            self.merger_stage_factory = lambda entity_id: Merger(entity_id=entity_id)
        if self.validator_stage is None:
            from m6_validator import validator as m6_validator
            self.validator_stage = m6_validator
        if self.scorer_stage is None:
            from m7_scorer import scorer as m7_scorer
            self.scorer_stage = m7_scorer
        if self.report_builder_stage is None:
            from m8_report_builder import report_builder as m8_report_builder
            self.report_builder_stage = m8_report_builder

    def run(
        self,
        raw_input: dict[str, Any],
        source_urls: list[str],
        pipeline_run_id: str,
        ai_fields: list[str] | None = None,
    ) -> PipelineResult:
        """
        Execute stages in strict order:
        M1 Identifier -> M2 Source Acquisition -> M3 Structured Extractor ->
        M4 AI Extractor -> M5 Merger -> M6 Validator -> M7 Scorer -> M8 Report Builder.
        """
        stage_sequence: list[str] = []
        stage_timings: dict[str, float] = {}

        try:
            # M1
            stage_sequence.append("M1")
            _t = self.clock()
            identity = self._call(
                self.identifier_stage,
                ["resolve_entity", "identify"],
                raw_input,
            )
            entity_id = getattr(identity, "entity_id", raw_input.get("entity_id", ""))
            if not entity_id:
                raise PipelineStageError("M1", "entity_id could not be resolved", {"raw_input": raw_input})
            stage_timings["M1"] = (self.clock() - _t).total_seconds()

            # M2
            stage_sequence.append("M2")
            _t = self.clock()
            evidence_list = self._call(
                self.source_acquirer_stage,
                ["acquire_sources", "acquire"],
                entity_id,
                source_urls,
            )
            stage_timings["M2"] = (self.clock() - _t).total_seconds()

            # M3
            stage_sequence.append("M3")
            _t = self.clock()
            structured_records: list[Any] = []
            for evidence in evidence_list:
                structured_records.extend(
                    self._call(
                        self.structured_extractor_stage,
                        ["extract"],
                        evidence,
                    )
                )
            stage_timings["M3"] = (self.clock() - _t).total_seconds()

            # M4
            stage_sequence.append("M4")
            _t = self.clock()
            ai_records: list[Any] = []
            if ai_fields is None:
                ai_fields = []
            if ai_fields:
                for evidence in evidence_list:
                    ai_records.extend(
                        self._call(
                            self.ai_extractor_stage,
                            ["extract"],
                            evidence,
                            ai_fields,
                        )
                    )
            stage_timings["M4"] = (self.clock() - _t).total_seconds()

            # M5
            stage_sequence.append("M5")
            _t = self.clock()
            merger = self.merger_stage_factory(entity_id)
            merged_entity = self._call(
                merger,
                ["merge_entity_records", "merge"],
                structured_records + ai_records,
                pipeline_run_id,
            )
            stage_timings["M5"] = (self.clock() - _t).total_seconds()

            # M6
            stage_sequence.append("M6")
            _t = self.clock()
            validation_result = self._call(
                self.validator_stage,
                ["validate_entity_record", "validate"],
                merged_entity,
            )
            validated_data, validation_summary = self._extract_validation_payload(validation_result)
            warnings = list(getattr(validated_data, "quality_warnings", []))
            stage_timings["M6"] = (self.clock() - _t).total_seconds()

            if validated_data.state == RecordState.QUARANTINED:
                return PipelineResult(
                    pipeline_run_id=pipeline_run_id,
                    validated_data=validated_data,
                    score_data=None,
                    report=None,
                    validation_summary=validation_summary,
                    warnings=warnings,
                    status="quarantined",
                    error=None,
                    stage_sequence=stage_sequence,
                    stage_timings=stage_timings,
                )

            # M7
            stage_sequence.append("M7")
            _t = self.clock()
            score_data = self._score_from_validation(validation_result, validated_data)
            stage_timings["M7"] = (self.clock() - _t).total_seconds()

            # M8
            stage_sequence.append("M8")
            _t = self.clock()
            report = self._call(
                self.report_builder_stage,
                ["build_report", "build"],
                self._adapt_for_report(validated_data),
                self._adapt_for_report(score_data),
            )
            stage_timings["M8"] = (self.clock() - _t).total_seconds()

            status = "partial" if validated_data.state == RecordState.PARTIAL else "success"
            return PipelineResult(
                pipeline_run_id=pipeline_run_id,
                validated_data=validated_data,
                score_data=score_data,
                report=report,
                validation_summary=validation_summary,
                warnings=warnings,
                status=status,
                error=None,
                stage_sequence=stage_sequence,
                stage_timings=stage_timings,
            )

        except PipelineStageError as exc:
            return PipelineResult(
                pipeline_run_id=pipeline_run_id,
                validated_data=None,
                score_data=None,
                report=None,
                validation_summary=None,
                warnings=[],
                status="failed",
                error={
                    "type": "PipelineStageError",
                    "stage": exc.stage,
                    "reason": exc.reason,
                    "details": exc.details,
                },
                stage_sequence=stage_sequence,
                stage_timings=stage_timings,
            )
        except Exception as exc:
            failure_stage = stage_sequence[-1] if stage_sequence else "M1"
            return PipelineResult(
                pipeline_run_id=pipeline_run_id,
                validated_data=None,
                score_data=None,
                report=None,
                validation_summary=None,
                warnings=[],
                status="failed",
                error={
                    "type": exc.__class__.__name__,
                    "stage": failure_stage,
                    "reason": str(exc),
                    "details": {},
                },
                stage_sequence=stage_sequence,
                stage_timings=stage_timings,
            )

    def _call(self, stage_obj: Any, candidate_names: list[str], *args: Any) -> Any:
        for name in candidate_names:
            if hasattr(stage_obj, name):
                fn = getattr(stage_obj, name)
                return fn(*args)
        raise PipelineStageError(
            stage="unknown",
            reason=f"None of methods {candidate_names} found on stage {stage_obj}",
        )

    def _extract_validation_payload(self, result: Any) -> tuple[ValidatedEntityRecord, Any | None]:
        if hasattr(result, "validated_payload"):
            return result.validated_payload, getattr(result, "summary", None)
        if isinstance(result, ValidatedEntityRecord):
            return result, None
        raise PipelineStageError("M6", "Validator returned unsupported payload type", {"type": type(result).__name__})

    def _score_from_validation(self, validation_result: Any, validated_data: ValidatedEntityRecord) -> Any:
        if hasattr(self.scorer_stage, "score_from_validation_result") and hasattr(validation_result, "validated_payload"):
            return self.scorer_stage.score_from_validation_result(validation_result)
        if hasattr(self.scorer_stage, "score"):
            return self.scorer_stage.score(validated_data)
        raise PipelineStageError("M7", "Scorer stage is missing score method")

    def _adapt_for_report(self, payload: Any) -> Any:
        # Minimal bridge: keep contract as two objects (validated_data + score_data).
        # If a stage emits wrapper dataclass with payload attr, unwrap deterministically.
        if hasattr(payload, "validated_payload"):
            return payload.validated_payload
        return payload


def run_pipeline(config: PipelineConfig) -> PipelineResult:
    """
    Execute M1 → M8 in sequence for a single entity.

    Backward-compatible convenience wrapper around PipelineRunner.
    Uses config.entity_id as seed raw input and config.run_id as pipeline_run_id.
    """
    runner = PipelineRunner()
    return runner.run(
        raw_input={"entity_id": config.entity_id},
        source_urls=[],
        pipeline_run_id=config.run_id,
        ai_fields=[],
    )
