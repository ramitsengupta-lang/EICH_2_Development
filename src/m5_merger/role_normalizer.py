"""
Module: role_normalizer
Architecture: M5 — Merge / Reconcile (KMP role normalisation)

Provides the canonical role title normalisation map and normalize_role() function.
Must be applied to both role values before any KMP exact-match comparison in M5.

Normalisation pipeline:
  1. Strip whitespace
  2. Lowercase
  3. Exact alias lookup (case-insensitive)
  4. Return canonical form if found
  5. If not found, return raw role unchanged
"""
from __future__ import annotations

def _k(value: str) -> str:
    """Canonical alias key: trim + lowercase (case-insensitive exact match)."""
    return value.strip().lower()


# Required canonical titles and alias coverage.
# Keys are aliases (case-insensitive after trim/lower); values are canonical titles.
ROLE_NORMALIZATION_MAP: dict[str, str] = {
    # CEO
    _k("Chief Executive Officer"): "Chief Executive Officer",
    _k("CEO"): "Chief Executive Officer",
    # MD
    _k("Managing Director"): "Managing Director",
    _k("MD"): "Managing Director",
    # CFO
    _k("Chief Financial Officer"): "Chief Financial Officer",
    _k("CFO"): "Chief Financial Officer",
    # COO
    _k("Chief Operating Officer"): "Chief Operating Officer",
    _k("COO"): "Chief Operating Officer",
    # CTO
    _k("Chief Technology Officer"): "Chief Technology Officer",
    _k("CTO"): "Chief Technology Officer",
    # CIO
    _k("Chief Information Officer"): "Chief Information Officer",
    _k("CIO"): "Chief Information Officer",
    # CMO
    _k("Chief Marketing Officer"): "Chief Marketing Officer",
    _k("CMO"): "Chief Marketing Officer",
    # CHRO
    _k("Chief Human Resources Officer"): "Chief Human Resources Officer",
    _k("CHRO"): "Chief Human Resources Officer",
    # Chairman
    _k("Chairman"): "Chairman",
    # Vice Chairman
    _k("Vice Chairman"): "Vice Chairman",
    # President
    _k("President"): "President",
    # Vice President
    _k("Vice President"): "Vice President",
    _k("VP"): "Vice President",
    # Director
    _k("Director"): "Director",
    # Executive Director
    _k("Executive Director"): "Executive Director",
    _k("ED"): "Executive Director",
    # Principal
    _k("Principal"): "Principal",
    # Secretary
    _k("Secretary"): "Secretary",
    # Treasurer
    _k("Treasurer"): "Treasurer",
    # Registrar
    _k("Registrar"): "Registrar",
    # Dean
    _k("Dean"): "Dean",
    # Associate Dean
    _k("Associate Dean"): "Associate Dean",
    # Head of Department
    _k("Head of Department"): "Head of Department",
    _k("HOD"): "Head of Department",
    # Trustee
    _k("Trustee"): "Trustee",
    # Founder
    _k("Founder"): "Founder",
    # Co-Founder
    _k("Co-Founder"): "Co-Founder",
    _k("Co Founder"): "Co-Founder",
    # Patron
    _k("Patron"): "Patron",
    # Member
    _k("Member"): "Member",
    # Elected Member
    _k("Elected Member"): "Elected Member",
    # Nominated Member
    _k("Nominated Member"): "Nominated Member",
    # Additional required abbreviations
    _k("jt. secretary"): "Joint Secretary",
    _k("jt secretary"): "Joint Secretary",
    _k("jt. director"): "Joint Director",
    _k("jt director"): "Joint Director",
}


def normalize_role(raw_role: str) -> str:
    """
    Return canonical role title if a known alias match exists; otherwise raw input.

    Rules:
      - matching is case-insensitive
      - leading/trailing whitespace is ignored
      - if no alias match is found, raw_role is returned unchanged
    """
    key = _k(raw_role)
    return ROLE_NORMALIZATION_MAP.get(key, raw_role)


def get_all_canonical_roles() -> list[str]:
    """Return all canonical role titles in deterministic sorted order."""
    return sorted(set(ROLE_NORMALIZATION_MAP.values()))
