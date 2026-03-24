"""
Module: preflight
Architecture: Orchestration layer — operational safeguards

Lightweight pre-run checks executed before pipeline stages are loaded.
All failures are collected and returned as a deterministic PreflightResult;
nothing is raised — callers decide how to surface failures.

Checks performed:
  1. Input path exists (when provided)
  2. Output directory is writable
  3. Required pipeline modules are importable
"""
from __future__ import annotations

import importlib
from dataclasses import dataclass, field
from pathlib import Path

# Modules that must be importable for the pipeline to run.
# Lazy-import check: we only test importability, not execution.
_REQUIRED_MODULES: list[str] = [
    "contracts.source_ref",
    "contracts.validated_data",
    "contracts.score_data",
    "m5_merger.merger",
    "m6_validator.validator",
    "m7_scorer.scorer",
    "pipeline.pipeline_runner",
]


@dataclass
class PreflightResult:
    """Result of all preflight checks."""

    passed: bool
    failures: list[str] = field(default_factory=list)

    def as_error_dict(self) -> dict:
        return {
            "type": "PreflightFailure",
            "stage": "preflight",
            "reason": "One or more preflight checks failed",
            "failures": self.failures,
        }


def run_preflight(
    input_path: Path | None,
    output_dir: Path,
    *,
    required_modules: list[str] | None = None,
) -> PreflightResult:
    """
    Run all preflight checks and return a PreflightResult.

    Args:
        input_path:  Path to the input file, or None (skips existence check).
        output_dir:  Directory where artifacts will be written.
        required_modules: Override the default module list (used by tests).
    """
    failures: list[str] = []
    modules_to_check = required_modules if required_modules is not None else _REQUIRED_MODULES

    # 1. Input path exists
    if input_path is not None and not input_path.exists():
        failures.append(f"Input path does not exist: {input_path}")

    # 2. Output directory is writable
    try:
        output_dir.mkdir(parents=True, exist_ok=True)
        probe = output_dir / ".eich2_preflight_probe"
        probe.write_text("ok", encoding="utf-8")
        probe.unlink()
    except (OSError, PermissionError) as exc:
        failures.append(f"Output directory not writable ({output_dir}): {exc}")

    # 3. Required modules are importable
    for module_name in modules_to_check:
        try:
            importlib.import_module(module_name)
        except ImportError as exc:
            failures.append(f"Required module not importable [{module_name}]: {exc}")

    return PreflightResult(passed=len(failures) == 0, failures=failures)
