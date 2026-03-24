"""
Module: ai_extractor
Architecture: M4 — AI Evidence Extractor

Extracts structured fields from opaque evidence (PDF prose, unstructured HTML)
using bounded AI prompts. AI operates exclusively on text from the evidence store;
it never makes live web calls or uses open-ended world knowledge.

Invariants:
  - Input is always text read from RawEvidence in the evidence store.
  - All prompts are bounded: evidence text is injected; no web access permitted.
  - Every AI-extracted field must include an evidence_sentence citation.
  - extraction_method is always AI_INFERENCE; never STRUCTURED or PDF_PARSE.
  - compensation currency and year must be explicit in evidence; never inferred.
  - Fields not present in the evidence text must be returned as None.
  - AI output is validated before returning: extracted values must appear in evidence_sentence.
"""
from __future__ import annotations

from dataclasses import replace

from contracts.source_ref import SourceRef


# Fields that AI is permitted to extract (closed list; cannot be extended at runtime)
PERMITTED_AI_FIELDS: frozenset[str] = frozenset({
    "kmp_role",
    "role_start_date",
    "role_end_date",
    "total_compensation",
    "base_salary",
    "bonus",
    "equity_value",
    "compensation_year",
    "compensation_currency",
    "direct_relationships",
})


def extract(raw_text: str, source_ref: SourceRef, ai_fields: list[str]) -> dict:
    """
    Deterministic AI extraction stub.

    Rules implemented:
      - No model calls.
      - If ai_fields is empty, return only extraction metadata keys.
      - Otherwise return one key per requested field mapped to None.
      - Return enriched copy of source_ref with extraction_method=ai_inference.
      - Do not mutate the input source_ref.
    """
    del raw_text  # kept for interface completeness; unused in deterministic stub

    result: dict = {
        "_ai_extraction_attempted": True,
        "_ai_extraction_method": "stub",
    }

    if not ai_fields:
        return result

    enriched_source_ref = replace(source_ref, extraction_method="ai_inference")
    for field_name in ai_fields:
        result[str(field_name)] = None
    result["_source_ref"] = enriched_source_ref
    return result


def build_bounded_prompt(evidence_text: str, fields: list[str]) -> str:
    """
    Deterministic placeholder prompt builder retained for compatibility.
    """
    field_list = ", ".join(fields)
    return (
        "AI extraction is disabled in this runtime. "
        f"Requested fields: [{field_list}]. "
        f"Evidence length: {len(evidence_text)}"
    )


def validate_ai_output(extracted: dict, evidence_text: str) -> list[str]:
    """
    Deterministic placeholder validator retained for compatibility.
    """
    del extracted
    del evidence_text
    return []
