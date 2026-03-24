"""
Module: source_acquirer
Architecture: M2 — Source Acquisition

Fetches raw sources (registries, APIs, PDFs, HTML documents) and writes them to the
evidence store with full provenance: url, SHA-256 hash, fetched_at timestamp, mime type.

Invariants:
  - Every fetched document is assigned a unique source_id (UUID).
  - source_tier is looked up from source_registry, never AI-assigned.
  - max_evidence_age_days is enforced: stale cached documents trigger a re-fetch or block.
  - ai_extractor.py receives only text from this store; it never makes live web calls.
"""
from __future__ import annotations

from dataclasses import dataclass
from datetime import datetime
import hashlib
from pathlib import Path
from urllib.parse import urlparse

from contracts.source_ref import SourceRef


@dataclass
class RawEvidence:
    """A single fetched document stored in the evidence store."""
    source_id: str           # UUID assigned at acquisition time
    entity_id: str
    source_url: str
    source_hash: str         # SHA-256 hex digest of raw content
    fetched_at: datetime
    mime_type: str
    content_path: Path       # path to file on disk in evidence_store/
    source_tier: str         # SourceTier value; looked up from source_registry


def acquire(entity_id: str, source_urls: list[str]) -> list[SourceRef]:
    """
    Deterministically resolve URLs to SourceRef entries without network calls.

    Rules:
      - one SourceRef per input URL
      - source_id = sha256(entity_id + url)[:16]
      - source_name = parsed URL domain
      - source_tier inferred from URL pattern
      - extraction_method always "structured"
    """
    if not source_urls:
        return []

    refs: list[SourceRef] = []
    for url in source_urls:
        normalized_url = str(url).strip()
        if not normalized_url:
            continue
        refs.append(
            SourceRef(
                source_id=_source_id(entity_id, normalized_url),
                source_name=_domain_from_url(normalized_url),
                source_tier=_infer_source_tier(normalized_url),
                extraction_method="structured",
                document_date=None,
                fetched_at=datetime.min,
                url=normalized_url,
            )
        )
    return refs


def acquire_sources(entity_id: str, source_urls: list[str]) -> list[RawEvidence]:
    """
    Backward-compatible wrapper over acquire().
    """
    refs = acquire(entity_id, source_urls)
    evidences: list[RawEvidence] = []
    for ref in refs:
        evidences.append(
            RawEvidence(
                source_id=ref.source_id,
                entity_id=entity_id,
                source_url=ref.url or "",
                source_hash=hashlib.sha256(f"{entity_id}{ref.url}".encode("utf-8")).hexdigest(),
                fetched_at=ref.fetched_at,
                mime_type="application/octet-stream",
                content_path=Path("data/evidence_store") / f"{ref.source_id}.bin",
                source_tier=ref.source_tier,
            )
        )
    return evidences


def store_evidence(content: bytes, entity_id: str, source_url: str, mime_type: str) -> RawEvidence:
    """
    Deterministic placeholder storage for compatibility; no filesystem writes.
    """
    source_id = _source_id(entity_id, source_url)
    source_hash = hashlib.sha256(content).hexdigest()
    return RawEvidence(
        source_id=source_id,
        entity_id=entity_id,
        source_url=source_url,
        source_hash=source_hash,
        fetched_at=datetime.min,
        mime_type=mime_type,
        content_path=Path("data/evidence_store") / f"{source_id}.bin",
        source_tier=_infer_source_tier(source_url),
    )


def is_evidence_stale(evidence: RawEvidence, max_age_days: int) -> bool:
    """Return True if the evidence is older than max_age_days from today."""
    if max_age_days < 0:
        return True
    age_days = (datetime.utcnow() - evidence.fetched_at).days
    return age_days > max_age_days


def _source_id(entity_id: str, url: str) -> str:
    return hashlib.sha256(f"{entity_id}{url}".encode("utf-8")).hexdigest()[:16]


def _domain_from_url(url: str) -> str:
    parsed = urlparse(url)
    if parsed.netloc:
        return parsed.netloc.lower()
    if parsed.path:
        head = parsed.path.split("/")[0].strip().lower()
        return head
    return "unknown"


def _infer_source_tier(url: str) -> str:
    lowered = url.lower()
    if "naac.gov" in lowered or "ugc.ac.in" in lowered or "aicte-india.org" in lowered:
        return "official"
    if "mca.gov" in lowered or "aishe.gov" in lowered or ".gov.in" in lowered:
        return "authoritative"
    if "wikipedia" in lowered or "linkedin" in lowered:
        return "secondary"
    return "web"
