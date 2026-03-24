from __future__ import annotations

from datetime import date, datetime

from contracts.source_ref import SourceRef
from m4_ai_extractor.ai_extractor import extract


def _source_ref(method: str = "structured") -> SourceRef:
    return SourceRef(
        source_id="s1",
        source_name="example.org",
        source_tier="official",
        extraction_method=method,
        document_date=date(2026, 1, 1),
        fetched_at=datetime(2026, 1, 2),
        url="https://example.org/doc",
    )


def test_extract_with_empty_ai_fields_returns_metadata_only() -> None:
    src = _source_ref()

    result = extract("sample text", src, [])

    assert result == {
        "_ai_extraction_attempted": True,
        "_ai_extraction_method": "stub",
    }


def test_extract_returns_none_for_requested_fields_and_enriched_source_ref() -> None:
    src = _source_ref("pdf_parse")
    fields = ["kmp_role", "compensation_currency"]

    result = extract("sample text", src, fields)

    assert result["_ai_extraction_attempted"] is True
    assert result["_ai_extraction_method"] == "stub"
    assert result["kmp_role"] is None
    assert result["compensation_currency"] is None
    assert result["_source_ref"].extraction_method == "ai_inference"


def test_extract_does_not_mutate_input_source_ref() -> None:
    src = _source_ref("structured")

    result = extract("sample text", src, ["kmp_role"])

    assert src.extraction_method == "structured"
    assert result["_source_ref"].extraction_method == "ai_inference"
    assert result["_source_ref"] is not src
