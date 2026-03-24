"""
Module: identifier
Architecture: M1 — Entity Identifier

Resolves and normalises entity identity from raw input.
Assigns a stable entity_id, normalises the entity name, resolves jurisdiction,
and builds the initial alias registry.

Invariants:
  - entity_id is assigned once and never changes across runs for the same entity.
  - jurisdiction must resolve to a valid ISO 3166 code.
  - AI is not permitted to assign or override entity_id, entity_name, or jurisdiction.
"""
from __future__ import annotations

from dataclasses import dataclass
import hashlib
import re


_NORMALIZED_ENTITY_TYPES: dict[str, str] = {
    "institution": "Institution",
    "college": "Institution",
    "university": "Institution",
    "school": "Institution",
    "trust": "Trust",
    "society": "Society",
    "company": "Company",
    "private limited": "Company",
    "pvt ltd": "Company",
    "limited": "Company",
    "ltd": "Company",
}


@dataclass
class EntityIdentity:
    """Resolved and normalised identity for an entity."""
    entity_id: str
    entity_name: str
    jurisdiction: str      # ISO 3166
    entity_type: str       # from EntityType enum values
    aliases: list[str]


def identify(raw_input: dict) -> dict:
    """
    Normalize and enrich entity identity fields from raw input.

    Returns a dictionary containing normalized values plus _identified=True.
    """
    entity_name = normalize_entity_name(str(raw_input.get("entity_name", "")))
    jurisdiction = str(raw_input.get("jurisdiction", "")).strip().upper()
    entity_type = _normalize_entity_type(str(raw_input.get("entity_type", "")))

    entity_id = str(raw_input.get("entity_id", "")).strip()
    if not entity_id:
        seed = f"{entity_name}{jurisdiction}".encode("utf-8")
        entity_id = hashlib.sha256(seed).hexdigest()[:16]

    enriched = dict(raw_input)
    enriched.update(
        {
            "entity_id": entity_id,
            "entity_name": entity_name,
            "entity_type": entity_type,
            "jurisdiction": jurisdiction,
            "_identified": True,
        }
    )
    return enriched


def resolve_entity(raw_input: dict) -> EntityIdentity:
    """
    Backward-compatible wrapper returning EntityIdentity for existing callers.
    """
    identified = identify(raw_input)
    aliases = normalize_aliases(list(raw_input.get("aliases", [])))
    return EntityIdentity(
        entity_id=identified["entity_id"],
        entity_name=identified["entity_name"],
        jurisdiction=identified["jurisdiction"],
        entity_type=identified["entity_type"],
        aliases=aliases,
    )


def normalize_entity_name(raw_name: str) -> str:
    """
    Return canonical entity name: stripped, collapsed whitespace, and title-cased.
    """
    cleaned = " ".join(raw_name.strip().split())
    return cleaned.title()


def normalize_aliases(aliases: list[str]) -> list[str]:
    """
    Deduplicate aliases after normalization and return them sorted.
    """
    normalized = {
        normalize_entity_name(alias)
        for alias in aliases
        if isinstance(alias, str) and alias.strip()
    }
    return sorted(normalized)


def _normalize_entity_type(raw_type: str) -> str:
    key = re.sub(r"\s+", " ", raw_type.strip().lower())
    if not key:
        return "Unknown"
    return _NORMALIZED_ENTITY_TYPES.get(key, "Unknown")
