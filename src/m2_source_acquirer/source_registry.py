"""
Module: source_registry
Architecture: M2 — Source Acquisition (source tier definitions)

Maintains the registry of known sources and their assigned SourceTier.
Tier assignment is human-configured at registration time; it cannot be AI-assigned.

SourceTier values (see contracts/source_ref.py for full definitions):
  AUTHORITATIVE : official registry APIs, XBRL filings, exchange disclosures
  OFFICIAL      : audited annual reports, investor relations pages
  SECONDARY     : regulatory news feeds, verified press releases
  WEB           : unverified third-party documents, analyst reports, scraped pages

Runtime source registration is persisted to config/source_registry.yaml.
"""
from __future__ import annotations

from contracts.source_ref import SourceTier


# ---------------------------------------------------------------------------
# In-memory registry (seeded from config/source_registry.yaml at startup)
# ---------------------------------------------------------------------------

# Maps source_url_prefix → SourceTier
# Populated by load_registry(); do not reference directly in business logic.
_REGISTRY: dict[str, SourceTier] = {}


def load_registry(config_path: str) -> None:
    """
    Load source tier mappings from config/source_registry.yaml into _REGISTRY.
    Must be called once before any get_source_tier() calls.
    """
    raise NotImplementedError


def get_source_tier(source_url: str) -> SourceTier:
    """
    Return the SourceTier for a given source URL by longest-prefix match.
    Raises UnregisteredSourceError if no matching prefix is found.
    AI must not be used to determine or override the returned tier.
    """
    raise NotImplementedError


def register_source(url_prefix: str, tier: SourceTier) -> None:
    """
    Register a new source URL prefix with its tier.
    Persists the entry to config/source_registry.yaml.
    Raises ValueError if url_prefix is already registered with a different tier.
    """
    raise NotImplementedError
