"""
Module: cli
Architecture: Orchestration layer — CLI entrypoint

Runs a single EICH 2 pipeline execution from command line.

Usage:
    python -m pipeline.cli <input_path> [options]

    input_path   Path to a JSON or plain-text input file.
                 JSON: must contain at least one of "entity_id" or "entity_name".
                 Plain text: treated as entity_name.

    --source-urls URL [URL ...]   Zero or more source URLs passed to M2.
    --run-id RUN_ID               Explicit pipeline run ID (auto-generated if omitted).
    --output-dir DIR              Base output directory (default: logs).
                                  Override with EICH2_OUTPUT_ROOT env var.
    --debug                       Print additional debug info to stderr.

Exit codes:
    0  — success, partial, or quarantined (data produced; inspect status)
    1  — fatal execution failure or preflight failure

Artifacts written under <output_dir>/<run_id>/:
    execution_trace.json    stage timings, overall status
    pipeline_result.json    run id, status, warnings, error
    validation_summary.json validator counters (when available)
    score_data.json         scoring output (when scoring ran)
    report.json             report (when built)
    errors.json             error detail (on fatal failure only)
"""
from __future__ import annotations

import argparse
import hashlib
import json
import os
import sys
import time
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Callable


# ---------------------------------------------------------------------------
# Internal helpers
# ---------------------------------------------------------------------------

def _deterministic_run_id(entity_id: str, timestamp: str) -> str:
    """SHA-256 digest of 'entity_id:timestamp', first 12 hex chars."""
    raw = f"{entity_id}:{timestamp}".encode("utf-8")
    return "run-" + hashlib.sha256(raw).hexdigest()[:12]


def _load_input(input_path: Path) -> dict[str, Any]:
    """Load and parse the input file; plain text is treated as entity_name."""
    text = input_path.read_text(encoding="utf-8")
    try:
        payload = json.loads(text)
        if not isinstance(payload, dict):
            raise ValueError("Top-level JSON must be an object")
        return payload
    except (json.JSONDecodeError, ValueError):
        return {"entity_name": text.strip()}


def _output_root(cli_arg: str) -> str:
    """Resolve output root: env var wins, then CLI arg, then 'logs'."""
    return os.getenv("EICH2_OUTPUT_ROOT") or cli_arg or "logs"


def _print_summary(
    result: Any,
    output_dir: Path,
    written_paths: dict[str, Path],
) -> None:
    print(f"Run ID   : {result.pipeline_run_id}")
    print(f"Status   : {result.status}")
    print(f"Warnings : {len(result.warnings)}")
    print(f"Output   : {output_dir}")
    for name, path in sorted(written_paths.items()):
        print(f"  {name:<20} {path}")


def _write_preflight_errors(target: Path, payload: dict[str, Any]) -> None:
    try:
        target.parent.mkdir(parents=True, exist_ok=True)
        with open(target, "w", encoding="utf-8") as fh:
            json.dump(payload, fh, indent=2, sort_keys=True)
    except OSError:
        pass  # best-effort; already reporting to stderr


# ---------------------------------------------------------------------------
# Public entrypoint
# ---------------------------------------------------------------------------

def main(
    argv: list[str] | None = None,
    _runner_factory: Callable[[], Any] | None = None,
) -> int:
    """
    CLI entry point.  Returns an integer exit code (0 or 1).

    The optional _runner_factory parameter is intended for testing only:
    pass a zero-argument callable that returns a PipelineRunner-compatible
    object to inject fake stages without spawning real module imports.
    """
    parser = argparse.ArgumentParser(
        prog="eich2",
        description="EICH 2 Entity Intelligence Pipeline",
        formatter_class=argparse.RawDescriptionHelpFormatter,
    )
    parser.add_argument("input", help="Path to JSON or plain-text input file")
    parser.add_argument(
        "--source-urls",
        nargs="*",
        default=[],
        metavar="URL",
        help="Source URLs passed to the source acquirer (M2)",
    )
    parser.add_argument(
        "--run-id",
        default=None,
        help="Explicit pipeline run ID (auto-generated deterministically if omitted)",
    )
    parser.add_argument(
        "--output-dir",
        default="logs",
        help="Base output directory (default: logs; override via EICH2_OUTPUT_ROOT)",
    )
    parser.add_argument(
        "--debug",
        action="store_true",
        help="Print debug information to stderr",
    )

    args = parser.parse_args(argv)
    input_path = Path(args.input)
    timestamp = datetime.now(timezone.utc).strftime("%Y%m%dT%H%M%SZ")

    # Resolve base output root before preflight so we can write errors.json
    base_output_root = Path(_output_root(args.output_dir))

    # -----------------------------------------------------------------------
    # Preflight
    # -----------------------------------------------------------------------
    from pipeline.preflight import run_preflight

    preflight = run_preflight(input_path, base_output_root)
    if not preflight.passed:
        print("[EICH2] PREFLIGHT FAILED", file=sys.stderr)
        for failure in preflight.failures:
            print(f"  - {failure}", file=sys.stderr)
        _write_preflight_errors(
            base_output_root / "errors.json",
            preflight.as_error_dict(),
        )
        return 1

    # -----------------------------------------------------------------------
    # Load input and resolve run ID
    # -----------------------------------------------------------------------
    raw_input = _load_input(input_path)
    entity_id: str = (
        raw_input.get("entity_id")
        or raw_input.get("entity_name")
        or "unknown"
    )

    run_id: str = args.run_id if args.run_id else _deterministic_run_id(entity_id, timestamp)
    output_dir = base_output_root / run_id
    output_dir.mkdir(parents=True, exist_ok=True)

    if args.debug:
        print(f"[DEBUG] input_path  : {input_path}", file=sys.stderr)
        print(f"[DEBUG] entity_id   : {entity_id}", file=sys.stderr)
        print(f"[DEBUG] run_id      : {run_id}", file=sys.stderr)
        print(f"[DEBUG] output_dir  : {output_dir}", file=sys.stderr)

    # -----------------------------------------------------------------------
    # Pipeline execution
    # -----------------------------------------------------------------------
    from pipeline.pipeline_runner import PipelineRunner
    from pipeline.trace_writer import write_trace_artifacts

    if _runner_factory is not None:
        runner = _runner_factory()
    else:
        runner = PipelineRunner()

    run_started_at = datetime.now(timezone.utc).isoformat()
    t0 = time.monotonic()

    result = runner.run(
        raw_input=raw_input,
        source_urls=args.source_urls or [],
        pipeline_run_id=run_id,
        ai_fields=[],
    )

    run_finished_at = datetime.now(timezone.utc).isoformat()
    run_duration_seconds = round(time.monotonic() - t0, 4)

    # -----------------------------------------------------------------------
    # Write trace artifacts
    # -----------------------------------------------------------------------
    written_paths = write_trace_artifacts(
        result=result,
        output_dir=output_dir,
        run_started_at=run_started_at,
        run_finished_at=run_finished_at,
        run_duration_seconds=run_duration_seconds,
    )

    # -----------------------------------------------------------------------
    # Print summary and return exit code
    # -----------------------------------------------------------------------
    _print_summary(result, output_dir, written_paths)

    if args.debug and result.error:
        print(f"[DEBUG] error       : {result.error}", file=sys.stderr)

    return 0 if result.status != "failed" else 1


if __name__ == "__main__":
    sys.exit(main())
