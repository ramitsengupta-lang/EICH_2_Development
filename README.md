# EICH 2

A separate rebuild of EICH 1. EICH 1 is untouched and fully operational.

## Pipeline

```
M1 Identifier → M2 Source Acquirer → M3 Structured Extractor →
M4 AI Extractor → M5 Merger → M6 Validator → M7 Scorer → M8 Report Builder
```

Downstream contract is unchanged: `validated_data + score_data → report`.

## Key design principles

- AI extracts **only** from fetched evidence, never from open-ended world knowledge.
- Structured sources have precedence over AI extraction for the same field.
- Every field in `validated_data` carries per-field provenance via `field_sources`.
- `RecordState` (`VALIDATED | PARTIAL | QUARANTINED`) governs which modules may consume a record.
- Compensation `currency` and `year` are never inferred; absence quarantines the record.

## Architecture reference

See `EICH2_ARCHITECTURE.md` for full module specs, field ownership matrix, merge algorithm,
data contracts, and implementation plan.

## Project structure

```
src/
  contracts/          canonical data contracts (validated_data, score_data, source_ref)
  pipeline/           orchestration (pipeline_runner)
  m1_identifier/      entity identity resolution
  m2_source_acquirer/ evidence fetch and store
  m3_structured_extractor/  XBRL, JSON API, CSV parsing
  m4_ai_extractor/    bounded AI extraction from evidence
  m5_merger/          sequenced merge algorithm + role normalisation
  m6_validator/       validation gate (VALIDATED | PARTIAL | QUARANTINED)
  m7_scorer/          dimension scoring; reads validated_data only
  m8_report_builder/  report assembly; reads validated_data + score_data only
config/               settings and source tier registry
tests/                test suite
data/
  evidence_store/     fetched raw documents with SHA-256 hashes
  raw_inputs/         manually dropped source files (Phase 1)
  output/             validated_data, score_data, quarantine, reports
logs/
```

## Setup

```bash
pip install -r requirements.txt
cp .env.example .env   # configure paths and thresholds
```

## Running

```python
from src.pipeline.pipeline_runner import run_pipeline, PipelineConfig
import uuid

config = PipelineConfig(entity_id="ENTITY_001", run_id=str(uuid.uuid4()))
result = run_pipeline(config)
print(result)
```
