# EICH 2 — Architecture Design Document
**Version:** 1.0 | **Date:** 2026-03-24 | **Status:** MVP Blueprint

---

## 1. FINAL MODULE ARCHITECTURE

```
┌─────────────────────────────────────────────────────────────────────────┐
│                        EICH 2 PIPELINE                                  │
│                                                                         │
│  [M1: Identifier]                                                       │
│    └─ entity_id, aliases, jurisdiction, entity_type                     │
│         │                                                               │
│  [M2: Source Acquisition]                                               │
│    ├─ Structured feeds  (registries, filings, APIs)                     │
│    ├─ Document fetcher  (PDFs, HTML, annual reports)                    │
│    └─ Evidence store    (raw_evidence: url, hash, timestamp, mime)      │
│         │                                                               │
│  [M3: Structured Extractor]                                             │
│    └─ Field-level parser for machine-readable sources                   │
│       (XBRL, JSON APIs, CSV registries)                                 │
│         │                                                               │
│  [M4: AI Evidence Extractor]  ← ONLY reads raw_evidence from M2        │
│    ├─ PDF/prose → structured fields                                     │
│    ├─ Bounded prompt: evidence text in, structured JSON out             │
│    └─ Per-extraction: source_ref, confidence, extracted_at              │
│         │                                                               │
│  [M5: Merge / Reconcile]                                                │
│    ├─ Apply source precedence rules                                     │
│    ├─ Recency arbitration                                               │
│    ├─ Conflict flagging (not silent overwrite)                          │
│    └─ Output: merged_record + conflict_log                             │
│         │                                                               │
│  [M6: Validation]                                                       │
│    ├─ Schema validation (required fields, types, ranges)               │
│    ├─ Cross-field consistency checks                                    │
│    ├─ Provenance completeness check                                     │
│    └─ Output: validated_data (pass) | quarantine_log (fail)            │
│         │                                                               │
│  [M7: Scoring]                                                          │
│    ├─ Reads ONLY from validated_data                                    │
│    ├─ Dimension scorers (per scoring spec)                             │
│    └─ Output: score_data                                               │
│         │                                                               │
│  [M8: Report Builder]                                                   │
│    └─ Reads ONLY validated_data + score_data                           │
│       (no re-fetching, no AI reasoning at report stage)                │
└─────────────────────────────────────────────────────────────────────────┘
```

### Module Responsibilities (One-Line Each)

| Module | Class/File | Responsibility |
|--------|-----------|----------------|
| M1 | `identifier.py` | Resolve and normalize entity identity + alias registry |
| M2 | `source_acquirer.py` | Fetch and store raw evidence with full provenance |
| M3 | `structured_extractor.py` | Parse machine-readable sources into typed field records |
| M4 | `ai_extractor.py` | Extract fields from opaque evidence using bounded AI prompts |
| M5 | `merger.py` | Merge multi-source field records with precedence + conflict rules |
| M6 | `validator.py` | Validate merged record; gate to validated_data or quarantine |
| M7 | `scorer.py` | Compute dimension scores from validated_data only |
| M8 | `report_builder.py` | Assemble final report from validated_data + score_data only |

---

## 2. FIELD OWNERSHIP MATRIX

### Legend
- **S** = Structured Extractor (M3) — primary authority
- **A** = AI Extractor (M4) — used when S unavailable or underspecified
- **M** = Merge-derived (M5) — computed from S + A outputs
- **V** = Validation-derived (M6) — computed during validation pass
- **[locked]** = AI cannot override a structured value for this field

### Entity Identity

| Field | Owner | AI Permitted | Notes |
|-------|-------|-------------|-------|
| `entity_id` | S | No | Registry-assigned; immutable |
| `entity_name` | S | No [locked] | Official registered name |
| `aliases` | M | Yes (additive) | AI may add aliases, not remove |
| `jurisdiction` | S | No [locked] | From incorporation registry |
| `entity_type` | S | No [locked] | Company, Fund, Trust, etc. |
| `status` | S | No [locked] | Active/Dissolved from registry |

### Key Management Personnel (KMP)

| Field | Owner | AI Permitted | Notes |
|-------|-------|-------------|-------|
| `kmp_name` | S | No [locked] | From official filing |
| `kmp_role` | S | A (fallback) | AI only when no structured source |
| `role_start_date` | S | A (with low confidence) | AI confidence capped at 0.7 |
| `role_end_date` | S | A (with low confidence) | AI confidence capped at 0.7 |
| `kmp_status` | M | No | Derived from dates + current filing |
| `kmp_tenure_days` | V | No | Computed in validation pass |
| `staleness_flag` | M5 | No | True if no Tier 1–2 source observed in >180 days |
| `last_observed_date` | M5 | No | Latest effective_date from any source for this KMP |

### Compensation

| Field | Owner | AI Permitted | Notes |
|-------|-------|-------------|-------|
| `total_compensation` | S | A (with citation) | S = XBRL/filing table; A = PDF prose |
| `base_salary` | S | A (with citation) | AI must cite evidence sentence |
| `bonus` | S | A (with citation) | AI must cite evidence sentence |
| `equity_value` | S | A (low confidence) | High variance; flag for review |
| `compensation_year` | S | A (required) | Year must be explicit in evidence |
| `compensation_currency` | S | A (required) | Must be explicit; no inference |

### Relationships / Associated Entities

| Field | Owner | AI Permitted | Notes |
|-------|-------|-------------|-------|
| `direct_relationships` | S | A (additive only) | Board seats, ownership from registry |
| `inferred_relationships` | A | A (bounded) | AI-only; tagged `inferred`; never promoted to S |
| `relationship_evidence_ref` | V | No | Every relationship requires a source_ref |
| `relationship_valid_from` | S | A | Required for all direct relationships |
| `relationship_valid_to` | S | A | Null = currently active |
| `over_link_flag` | V | No | Set if entity degree > threshold (config) |

### Provenance (All Fields)

| Field | Owner | AI Permitted | Notes |
|-------|-------|-------------|-------|
| `source_id` | M2 | No | UUID of raw_evidence record |
| `source_url` | M2 | No | Stored at acquisition time |
| `source_hash` | M2 | No | SHA-256 of fetched content |
| `extracted_at` | M3/M4 | No | ISO timestamp |
| `confidence` | M3/M4 | No | Float 0.0–1.0; structured = 1.0 |
| `source_tier` | M2 | No | `SourceTier` enum: AUTHORITATIVE \| OFFICIAL \| SECONDARY \| WEB |
| `extraction_method` | M3/M4 | No | `ExtractionMethod` enum: STRUCTURED \| PDF_PARSE \| AI_INFERENCE |
| `field_sources` | M5 | No | Per-field `SourceRef` map; populated by merger from M3/M4 outputs |

---

## 3. CONTRACT DEFINITIONS

### 3a. `validated_data` Contract

```python
@dataclass
class ValidatedEntityRecord:
    # Identity
    entity_id: str                          # required, non-empty
    entity_name: str                        # required, non-empty
    jurisdiction: str                       # required, ISO 3166
    entity_type: EntityType                 # enum: COMPANY | FUND | TRUST | OTHER
    status: EntityStatus                    # enum: ACTIVE | DISSOLVED | UNKNOWN

    # KMP list
    kmp: list[KMPRecord]                    # required, may be empty list

    # Compensation list
    compensation: list[CompensationRecord]  # required, may be empty list

    # Relationships
    direct_relationships: list[RelationshipRecord]
    inferred_relationships: list[InferredRelationshipRecord]

    # Audit
    pipeline_run_id: str                    # UUID, ties to full run log
    validated_at: datetime
    validation_version: str                 # semver of validator
    conflict_log: list[ConflictRecord]      # zero or more unresolved conflicts preserved
    record_state: RecordState               # see enum below; governs downstream module access
    quarantine_detail: str | None           # populated only when record_state = QUARANTINED or PARTIAL


class RecordState(str, Enum):
    """
    VALIDATED  — All required fields present, all provenance complete, no unresolved conflicts.
                 May be consumed by: M7 Scorer, M8 Report Builder.

    PARTIAL    — Required fields present but one or more non-critical fields are missing provenance,
                 have unresolved conflicts, or carry confidence < 0.5.
                 May be consumed by: M8 Report Builder (with partial-data warning rendered).
                 Must NOT be consumed by: M7 Scorer (partial records excluded from scoring).

    QUARANTINED — One or more critical fields (entity_id, jurisdiction, kmp_id, compensation year,
                  compensation currency) are absent, unprovable, or in hard conflict.
                  Must NOT be consumed by: M7 Scorer, M8 Report Builder.
                  Written to: store/quarantine/ only.
                  quarantine_detail must be non-null and describe the blocking reason.
    """
    VALIDATED   = "VALIDATED"
    PARTIAL     = "PARTIAL"
    QUARANTINED = "QUARANTINED"


@dataclass
class SourceRef:
    source_id: str                          # UUID of raw_evidence record (from M2)
    confidence: float                       # 0.0–1.0
    source_tier: SourceTier                 # independent axis 1: origin authority of the document
    extraction_method: ExtractionMethod     # independent axis 2: how the value was obtained
    extracted_at: datetime
    # Both axes contribute to score penalties independently (see §3b score penalty rules).


class SourceTier(str, Enum):
    """
    Describes the authority of the source document. Assigned at M2 acquisition. Cannot be AI-assigned.
    authoritative — Official registry APIs, XBRL filings, stock exchange disclosures.
    official       — Audited annual reports, company investor relations pages.
    secondary      — Regulatory news feeds, verified press releases.
    web            — Unverified third-party documents, analyst reports, scraped pages.
    """
    AUTHORITATIVE = "authoritative"
    OFFICIAL      = "official"
    SECONDARY     = "secondary"
    WEB           = "web"


class ExtractionMethod(str, Enum):
    """
    Describes how the value was obtained from the source document. Assigned at M3/M4. Cannot be AI-assigned.
    structured  — Parsed directly from machine-readable format (XBRL, JSON API, CSV registry).
    pdf_parse   — Extracted from a structured table or form field within a PDF (deterministic parser).
    ai_inference — Extracted by AI prompt from unstructured prose or ambiguous PDF content.
    """
    STRUCTURED   = "structured"
    PDF_PARSE    = "pdf_parse"
    AI_INFERENCE = "ai_inference"


@dataclass
class KMPRecord:
    kmp_id: str                             # UUID, stable across runs
    name: str
    name_raw: str                           # original pre-normalization text; preserved for audit
    role: str                               # normalized via role synonym table (see §4b.1)
    role_start_date: date | None
    role_end_date: date | None              # None = currently active
    kmp_status: Literal["active", "former", "unknown"]
    tenure_days: int | None
    staleness_flag: bool                    # True if no AUTHORITATIVE or OFFICIAL source in >180 days
    last_observed_date: date | None         # latest effective_date seen across any source for this KMP
    source_ref: str                         # primary source_id (highest-confidence field source)
    confidence: float                       # min(field_sources[f].confidence for f in field_sources)
    extraction_method: ExtractionMethod             # dominant extraction method across field_sources
    field_sources: dict[str, SourceRef]     # per-field provenance: field_name → SourceRef


@dataclass
class CompensationRecord:
    compensation_id: str                    # UUID
    kmp_id: str                             # FK to KMPRecord
    year: int                               # required; no inference
    currency: str                           # ISO 4217; required
    total_compensation: Decimal | None
    base_salary: Decimal | None
    bonus: Decimal | None
    equity_value: Decimal | None
    evidence_sentence: str | None           # required when extraction_method = ai_bounded
    source_ref: str                         # primary source_id (highest-confidence field source)
    confidence: float                       # min(field_sources[f].confidence for f in field_sources)
    extraction_method: ExtractionMethod             # dominant extraction method across field_sources
    field_sources: dict[str, SourceRef]     # per-field provenance: field_name → SourceRef
    # MERGE KEY: (kmp_id, year, currency) — must be unique within a merged entity record.
    # Enforcement: after field-level merge, M5 asserts uniqueness across all CompensationRecords
    # for the entity. If two records share the same (kmp_id, year, currency) after deduplication,
    # M5 raises MergeConflictError(field="compensation", key=(kmp_id, year, currency))
    # and halts the merge for that entity. The entity is written to store/quarantine/ with
    # quarantine_detail describing the duplicate key. It is NOT passed to M6 Validation.


@dataclass
class RelationshipRecord:
    rel_id: str
    from_entity_id: str
    to_entity_id: str
    relationship_type: str                  # enum from controlled vocab
    valid_from: date | None
    valid_to: date | None
    source_ref: str
    confidence: float
    over_link_flag: bool


@dataclass
class InferredRelationshipRecord(RelationshipRecord):
    inference_basis: str                    # evidence text that triggered inference
    # Never promoted to direct_relationships; always tagged inferred
```

### 3b. `score_data` Contract

```python
@dataclass
class ScoreData:
    entity_id: str                          # FK to validated_data
    pipeline_run_id: str                    # same run UUID
    scored_at: datetime
    scorer_version: str                     # semver

    dimensions: dict[str, DimensionScore]  # keyed by dimension name

    composite_score: float                  # 0.0–100.0
    composite_method: str                   # e.g. "weighted_average_v2"
    score_confidence: float                 # min(confidence) across inputs

    # Traceability: which validated_data fields fed each score
    field_contributions: dict[str, list[str]]  # dim_name -> [field_paths used]


@dataclass
class DimensionScore:
    dimension: str
    raw_value: float
    normalized_score: float                 # 0.0–100.0
    weight: float
    contributing_fields: list[str]
    data_completeness: float               # 0.0–1.0; penalizes missing fields
    confidence: float
```

**Hard rules for score_data:**
- `scorer.py` imports ONLY from `validated_data`; no raw source access
- Any field with `confidence < 0.5` contributes 0 to data_completeness
- `score_data` is immutable once produced for a `pipeline_run_id`
- Score changes across runs are logged in `score_delta_log`

---

## 4. MERGE / RECONCILE POLICY

### 4a. Source Axes

Sources are described on **two independent axes**, both assigned at M2 acquisition.

**Axis 1 — `source_tier` (document authority):**
```
AUTHORITATIVE:  Official registry APIs, XBRL filings, stock exchange disclosures
OFFICIAL:       Audited annual reports, company investor relations pages
SECONDARY:      Regulatory news feeds, verified press releases
WEB:            Unverified third-party documents, analyst reports, scraped pages
```
`source_tier` is assigned per `source_id` at M2 registration. Cannot be AI-assigned.

**Axis 2 — `extraction_method` (how the value was obtained):**
```
STRUCTURED:     Parsed from machine-readable format (XBRL, JSON API, CSV)
PDF_PARSE:      Extracted from a structured table/form field in a PDF (deterministic parser)
AI_INFERENCE:   Extracted by AI prompt from unstructured prose or ambiguous PDF content
```
`extraction_method` is assigned per extracted value by M3 (STRUCTURED, PDF_PARSE) or M4 (AI_INFERENCE).

**Score penalty rules (both axes applied independently by M7 Scorer):**

| source_tier | penalty multiplier |
|-------------|-------------------|
| AUTHORITATIVE | 0.00 (no penalty) |
| OFFICIAL | 0.05 |
| SECONDARY | 0.15 |
| WEB | 0.30 |

| extraction_method | penalty multiplier |
|-------------------|-------------------|
| STRUCTURED | 0.00 (no penalty) |
| PDF_PARSE | 0.05 |
| AI_INFERENCE | 0.20 |

Final field penalty = `source_tier_penalty + extraction_method_penalty` (additive, capped at 0.40).
Applied to `DimensionScore.data_completeness` for each contributing field.

### 4b. Field-Level Merge Algorithm

The merge rules are evaluated as a **single sequenced algorithm** per field F, executed in order. Steps are not interchangeable. Each step either resolves F or falls through to the next step.

```
MERGE ALGORITHM — Applied per field F across all candidate values:

  STEP 1 — Collect:
    Gather all (value, source_tier: SourceTier, extraction_method: ExtractionMethod,
                effective_date, source_ref)
    tuples for field F from M3 and M4 outputs.
    If only one candidate exists, assign it. Algorithm ends.

  STEP 2 — Drop nulls:
    Remove any candidate where value IS NULL.
    A null from any tier is not a competing value.
    (Absence of evidence ≠ evidence of absence.)
    If one non-null candidate remains after dropping, assign it. Algorithm ends.

  STEP 3 — Partition by extraction_method:
    Split remaining candidates into:
      structured_candidates  (extraction_method in {STRUCTURED, PDF_PARSE})
      ai_candidates          (extraction_method = AI_INFERENCE)

  STEP 4 — Structured wins:
    If structured_candidates is non-empty, discard ai_candidates entirely.
    Log each discarded AI_INFERENCE candidate to conflict_log
    with resolution_rule = RULE_3_SUPPRESSED.
    Proceed with structured_candidates only.

  STEP 5 — Rank by source_tier (within surviving candidates):
    Order: AUTHORITATIVE > OFFICIAL > SECONDARY > WEB. Higher tier wins.
    Discard lower-tier candidates.
    Log each discarded candidate to conflict_log with resolution_rule = RULE_TIER.
    If a tie on tier, continue to Step 6.

  STEP 6 — Rank by recency (within same tier):
    Use candidate with latest effective_date or publication_date.
    Log discarded candidate to conflict_log with resolution_rule = RULE_RECENCY.
    If dates are equal or both unknown, do NOT resolve:
      → Write all tied candidates to conflict_log with resolution_rule = CONFLICT_UNRESOLVED.
      → Set review_flag = True on the ConflictRecord.
      → Assign the first-seen candidate as a provisional value.

  STEP 7 — Additive fields (aliases, relationships only):
    For fields declared additive in the Field Ownership Matrix,
    override Steps 4–6: take the union of all non-null values after dedup.
    Each entry in the union retains its own source_ref via field_sources.

  STEP 8 — Numeric spread check (compensation fields only):
    After assignment, compare the winning value against all Tier 1–2 candidates.
    If spread > 20% of the winning value, set review_flag = True on the ConflictRecord.
    Do not change the assigned value.

  POST-MERGE — KMP identity match:
    Match KMP entries on (name_normalized + role_normalized + entity_id).
    Normalization must run before comparison (see §4b.1).
    No fuzzy match in MVP; exact normalized match only.
    Unmatched entries are appended with source_ref; not silently merged.
    Near-matches (name similarity > 80%) are written to conflict_log
    with resolution_rule = POTENTIAL_DUPLICATE; both entries preserved.
```

### 4b.1. KMP Role Normalization Map

This normalization map **must be applied to both `role` values before any KMP exact-match comparison** in STEP POST-MERGE. Normalization: lowercase → strip punctuation → apply synonym map → collapse whitespace.

```python
# Canonical role synonym map (extend as needed; keys are lowercase post-strip)
ROLE_NORMALIZATION_MAP: dict[str, str] = {
    # C-Suite
    "ceo":                              "chief executive officer",
    "cfo":                              "chief financial officer",
    "coo":                              "chief operating officer",
    "cto":                              "chief technology officer",
    "cio":                              "chief information officer",
    "cmo":                              "chief marketing officer",
    "cro":                              "chief risk officer",
    "cco":                              "chief compliance officer",
    "chro":                             "chief human resources officer",
    "cso":                              "chief strategy officer",
    # Managing / Executive Director
    "md":                               "managing director",
    "ed":                               "executive director",
    "exec director":                    "executive director",
    # Board roles
    "chairman":                         "chair of the board",
    "chairperson":                      "chair of the board",
    "chair":                            "chair of the board",
    "ned":                              "non-executive director",
    "non executive director":           "non-executive director",
    "independent director":             "non-executive director",
    "independent non-executive director": "non-executive director",
    # General director
    "director":                         "director",
    "board member":                     "director",
    # Finance
    "group cfo":                        "chief financial officer",
    "finance director":                 "chief financial officer",
    "fd":                               "chief financial officer",
    # Company Secretary
    "company secretary":                "company secretary",
    "co sec":                           "company secretary",
    "cosec":                            "company secretary",
    # President / VP
    "president":                        "president",
    "svp":                              "senior vice president",
    "evp":                              "executive vice president",
    "vp":                               "vice president",
}

def normalize_role(raw_role: str) -> str:
    """Lowercase, strip punctuation, apply synonym map, collapse whitespace."""
    import re, string
    cleaned = raw_role.lower().translate(str.maketrans("", "", string.punctuation)).strip()
    cleaned = re.sub(r"\s+", " ", cleaned)
    return ROLE_NORMALIZATION_MAP.get(cleaned, cleaned)
```

**Rules:**
- `normalize_role()` runs in M5 (Merger) before KMP match, not in M3/M4.
- The raw value is preserved as `name_raw` / the raw role string for audit.
- An unknown role not in the map passes through as-is (normalized lowercase); it is NOT rejected.
- The map is versioned in `config/role_normalization.yaml`; changes require a merger version bump.

---

### 4c. Conflict Record Schema

```python
@dataclass
class ConflictRecord:
    field_path: str                 # e.g. "compensation[2026].base_salary"
    winning_value: Any
    winning_source_ref: str
    losing_value: Any
    losing_source_ref: str
    resolution_rule: str            # RULE_TIER | RULE_RECENCY | RULE_3_SUPPRESSED |
                                    # POTENTIAL_DUPLICATE | CONFLICT_UNRESOLVED
    review_flag: bool
```

### 4d. KMP Drift Prevention

- Each KMP has a stable `kmp_id` (UUID assigned on first observation)
- Role changes produce new `KMPRecord` entries (not updates) linked by `kmp_id`
- `role_end_date` is only set when explicitly evidenced — never inferred from absence
- Staleness detection: if a KMP has no update from Tier 1–2 source in >180 days, set `staleness_flag = True`

### 4e. Associated Entity Over-Linking Guard

```
Config: MAX_DIRECT_DEGREE = 10 (adjustable)
Config: MAX_INFERRED_DEGREE = 5 (adjustable)

At merge time:
  If entity degree (direct) > MAX_DIRECT_DEGREE → set over_link_flag, pause addition
  If entity degree (inferred) > MAX_INFERRED_DEGREE → set over_link_flag, drop addition
  All dropped inferences are logged in conflict_log with reason OVER_LINK_GUARD
```

---

## 5. IMPLEMENTATION PLANS

### Phase 1 — Minimal MVP

**Goal:** End-to-end pipeline producing a valid report for 1 entity type (Company) with manual source inputs.

**Timeline target:** 8–10 sprints

| Sprint | Deliverable |
|--------|------------|
| 1–2 | M1 Identifier + M2 Source Acquirer (manual file drop + hash/provenance) |
| 3–4 | M3 Structured Extractor (registry JSON + XBRL parser for KMP + compensation) |
| 5–6 | M4 AI Extractor (PDF → JSON; 3 field types: role, compensation, relationship) |
| 7 | M5 Merger (Rules 1–6 only; no drift detection yet) |
| 8 | M6 Validator (schema + provenance completeness) |
| 9 | M7 Scorer (2 dimensions; manual weight config) |
| 10 | M8 Report Builder (JSON + Markdown output; no UI) |

**MVP Scope Limits:**
- Single entity type: Company
- Sources: 2 structured (registry API + XBRL), 1 AI (annual report PDF)
- KMP: roles, dates, tenure only
- Compensation: total + base only
- Relationships: direct board seats only; no inferred
- Report: JSON + Markdown; no PDF renderer

### Phase 2 — Scaled Production

**Prerequisites:** MVP stable, 10+ entities validated manually

| Capability | Detail |
|-----------|--------|
| Multi-entity types | Fund, Trust, SPV with entity-type-specific field schemas |
| Source expansion | 5+ structured feeds per jurisdiction; press release parsers |
| AI extraction v2 | Multi-pass extraction with self-consistency check |
| KMP drift detection | 180-day staleness flag; role-change audit trail |
| Over-link guard | Live degree calculation + configurable thresholds |
| Compensation v2 | Bonus, equity, LTI; PDF table extraction |
| Inferred relationships | Bounded AI inference; tagged; never promoted |
| Score v2 | 5+ dimensions; weight tuning UI; score delta log |
| Automation | Scheduled pipeline runs; source freshness monitoring |
| Audit UI | Provenance viewer; conflict log browser; quarantine queue |
| Multi-jurisdiction | Jurisdiction-aware field schemas and source precedence |

---

## 6. TOP 10 IMPLEMENTATION RISKS AND MITIGATIONS

| # | Risk | Severity | Mitigation |
|---|------|----------|-----------|
| 1 | **Compensation buried in PDF prose/tables** — AI misreads layout or extracts wrong year | HIGH | Require `evidence_sentence` citation; validate year is explicit; cap AI confidence at 0.7; human review queue for compensation fields when confidence < 0.6 |
| 2 | **KMP identity collision** — Two people with similar names merged into one KMP record | HIGH | Exact-match only in MVP; add `kmp_id` stability tests; log all near-matches to manual review queue; no fuzzy match until Phase 2 with explicit dedup rules |
| 3 | **KMP role drift undetected** — Outdated role carried forward silently | HIGH | Staleness flag at 180 days; never infer `role_end_date` from absence; make stale KMP visible in report with warning |
| 4 | **AI extractor drifts to open-ended reasoning** — Model uses training knowledge instead of evidence text | HIGH | Strictly bounded prompts: evidence text injected, no web access, `extract only what appears in this text` instruction; output validation rejects fields not cited in evidence |
| 5 | **Source precedence misconfiguration** — Tier assigned incorrectly, wrong data wins | MEDIUM | Tier assignment is human-configured per source_id at M2 registration; automated tests assert expected winner for known conflict fixtures |
| 6 | **Associated entity over-linking** — Relationship graph grows unbounded via AI inference | MEDIUM | Over-link guard with hard degree limits; inferred relationships never promoted; all additions logged; Phase 1 disables inferred relationships entirely |
| 7 | **Conflict silently dropped** — Merge rule resolves conflict without surfacing it | MEDIUM | Every conflict goes to `conflict_log` regardless of resolution rule; report builder surfaces unresolved conflicts; `review_flag` exposed in output |
| 8 | **Schema version mismatch** — validated_data schema changes break scorer or report builder | MEDIUM | Version field on validated_data and score_data; scorer and report_builder declare supported schema versions; CI test matrix across schema versions |
| 9 | **Stale source cache used** — Old fetched document used for new run | LOW–MEDIUM | M2 stores `fetched_at` + `source_hash`; pipeline config has `max_evidence_age_days`; staleness detected before extraction; fresh fetch triggered or run blocked |
| 10 | **Currency/year inference in compensation** — AI infers currency or year when not explicit | MEDIUM | Both `currency` and `year` are required fields; if absent from evidence, record is quarantined (not inserted with guessed values); quarantine reason reported |

---

## APPENDIX A: Directory Structure (Phase 1)

```
eich2/
├── pipeline/
│   ├── identifier.py
│   ├── source_acquirer.py
│   ├── structured_extractor.py
│   ├── ai_extractor.py
│   ├── merger.py
│   ├── validator.py
│   ├── scorer.py
│   └── report_builder.py
├── models/
│   ├── validated_data.py       ← dataclasses from Section 3a
│   ├── score_data.py           ← dataclasses from Section 3b
│   ├── raw_evidence.py
│   └── enums.py
├── config/
│   ├── source_registry.yaml    ← source_id → tier mapping
│   ├── merge_rules.yaml
│   └── score_weights.yaml
├── tests/
│   ├── fixtures/               ← known-good entity records for regression
│   ├── test_merger.py
│   ├── test_validator.py
│   └── test_scorer.py
├── store/
│   ├── raw_evidence/           ← fetched documents + hashes
│   ├── validated_data/         ← per-run JSON outputs
│   └── score_data/             ← per-run score outputs
└── reports/
    └── {entity_id}_{run_id}/
        ├── report.md
        ├── report.json
        └── conflict_log.json
```

---

## APPENDIX B: Key Design Invariants (Non-Negotiable)

1. `report_builder.py` has zero imports from M2, M3, or M4
2. `scorer.py` has zero imports from M2, M3, or M4
3. Every field in `validated_data` has a non-null `source_ref`
4. `ai_extractor.py` receives only text from `raw_evidence` store — no live web calls
5. Compensation `currency` and `year` are never defaulted or inferred
6. `role_end_date = None` means active; it is never set by absence of evidence
7. Inferred relationships are never present in `direct_relationships` list
8. Every `score_data` record is immutable and tied to exactly one `pipeline_run_id`

---
---

# EICH 2 — PRODUCTION ARCHITECTURE REVIEW

**Reviewer role:** Production readiness reviewer  
**Reviewed document:** EICH2_ARCHITECTURE.md v1.0  
**Date:** 2026-03-24  
**Verdict:** The hybrid direction is sound, the downstream contract is preserved, and the AI-bounding principle is correct. However, the design has **7 must-fix gaps** that will cause data corruption, audit failures, or silent merge errors in production. These are structural, not cosmetic — they need resolution before any module is built. 12 additional findings are deferrable to Phase 2.

---

## EXECUTIVE VERDICT

The architecture correctly separates structured from AI extraction, enforces evidence-only AI, and gates scoring/reporting on validated data only. The module boundary is clean, the invariants in Appendix B are the right ones, and the downstream contract (`validated_data` + `score_data` → report) is preserved.

But the design breaks down at three seams:

1. **Provenance is per-record, not per-field.** After merge, you cannot trace which source provided which field within a KMPRecord or CompensationRecord. This directly undermines the stated auditability goal.
2. **The merge rules mix two independent axes (source tier vs. extraction method) without a defined precedence between them.** Rule 3 and Rule 6 interact ambiguously.
3. **The KMP and compensation contracts lack merge keys and normalization specs**, meaning exact-match merge will produce duplicates on day one.

Each of these will generate incorrect reports or audit gaps if not fixed before the first module is coded.

---

## MUST-FIX FINDINGS (Before Build)

### MF-1: Per-Field Provenance Is Missing — Records Carry Only One `source_ref`

**Where it breaks:**  
`KMPRecord` has a single `source_ref` and single `confidence`. After M5 merges a KMP entry from two sources (e.g., name from registry, role_start_date from AI), the record has one `source_ref`. Which source does it point to? The merger must pick one, and the other is silently lost.

Same problem on `CompensationRecord` — if `total_compensation` came from XBRL and `base_salary` from PDF AI extraction, one `source_ref` cannot represent both.

**Why it matters:**  
Invariant 3 says "every field in validated_data has a non-null source_ref." But the dataclass enforces this at the record level, not the field level. An auditor asking "where did base_salary come from?" gets the wrong answer.

**Fix:**  
Replace single `source_ref` / `confidence` / `extraction_method` on KMPRecord and CompensationRecord with a per-field provenance map:

```python
# On KMPRecord and CompensationRecord:
field_provenance: dict[str, FieldProvenance]  # keyed by field name

@dataclass
class FieldProvenance:
    source_ref: str
    confidence: float
    extraction_method: Literal["structured", "ai_bounded"]
    extracted_at: datetime
```

Keep the top-level `confidence` as `min(field_provenance[f].confidence for f in contributing_fields)` for backward compatibility with the scorer. But the per-field map is the audit trail.

---

### MF-2: Merge Rules Mix Tier and Extraction Method Without a Defined Interaction Model

**Where it breaks:**  
- **Rule 1** says tier wins.  
- **Rule 3** says AI never overwrites structured.  
- **Rule 6** says NULL from higher tier doesn't overwrite.

Scenario: A Tier 2 PDF (annual report) is processed by M4 (AI extraction), producing `base_salary = 250,000`. A Tier 1 XBRL filing is processed by M3 (structured), producing `base_salary = NULL` (field absent in XBRL).

- Rule 3 says: structured exists → AI does not overwrite. But the structured value is NULL.  
- Rule 3 exception says: AI may fill NULL structured fields. So AI wins? Base_salary = 250,000?  
- Rule 6 says: NULL from higher tier does NOT overwrite non-NULL from lower tier. But here Tier 1 has NULL and Tier 2 has a value via AI. Rule 6 seems to agree with Rule 3's exception.  
- Rule 1 says: higher tier wins. Tier 1 NULL wins? That contradicts Rule 6.

There's a 3-way ambiguity. The merger implementor will guess, and different people will guess differently.

**Fix:**  
Define an explicit evaluation order for the rules:

```
RESOLUTION ORDER:
  Step 1: Collect all values for field F across sources.
  Step 2: Remove NULLs (Rule 6 — null is not a competing value).
  Step 3: Among remaining non-null values, partition by extraction_method.
  Step 4: If any structured value exists, it wins (Rule 3).
           Among multiple structured values, apply Rule 1 (tier), then Rule 2 (recency).
  Step 5: If no structured value exists, apply Rule 1 (tier) among AI values,
           then Rule 2 (recency).
  Step 6: Log all non-winning values to conflict_log.
```

Write this as a merge algorithm spec, not as independent rules that may contradict.

---

### MF-3: KMP Match Key Is Underspecified — "name_normalized" Has No Normalization Spec

**Where it breaks:**  
Rule 7 says match on `(name_normalized + role_normalized + entity_id)`. But:

- What is name normalization? Lowercase? Remove middle initials? Remove suffixes (Jr., III)? Remove diacritics? The architecture doesn't say.
- "CEO" vs. "Chief Executive Officer" vs. "Chief Exec. Officer" — these are the same role. `role_normalized` has no mapping defined.
- Real data: "John Smith" appears as "J. Smith" in one filing and "John Andrew Smith" in another. Exact match fails. Two KMP records are created. The conflict is never detected because they never match.

**Why it matters:**  
KMP duplication is listed as Risk #2 in the document's own risk table, but the mitigation says "exact-match only in MVP." That's not a mitigation — it's an acceptance of guaranteed duplicates. Given KMP feeds into compensation linkage (`kmp_id` FK on CompensationRecord), duplicate KMPs create orphaned or mislinked compensation records.

**Fix (must-have for MVP):**
1. Define a canonical normalization function: `lowercase → strip punctuation → collapse whitespace → remove common suffixes (Jr, Sr, III, etc.)`.
2. Define a role synonym table (even if small): `{"CEO": "chief executive officer", "CFO": "chief financial officer", "MD": "managing director", ...}`.
3. Add a `match_candidates` output from the merger: when a new KMP entry does NOT match exactly but has >80% name similarity to an existing entry, log it as `POTENTIAL_DUPLICATE` in conflict_log with both entries. Do not merge them — just flag them.
4. Store `name_raw` alongside `name` on KMPRecord to preserve the original for auditing.

---

### MF-4: `validated_data` Contract Contradiction — Quarantined Records Inside Validated Output

**STATUS: FIXED** — Replaced `quarantine_reasons: list[str]` with `record_state: RecordState` enum (`VALIDATED | PARTIAL | QUARANTINED`) and `quarantine_detail: str | None`. Downstream module consumption is now gated by `record_state`:
- **M7 Scorer:** consumes `VALIDATED` only.
- **M8 Report Builder:** consumes `VALIDATED` and `PARTIAL` (partial renders with warning); never `QUARANTINED`.
- **Quarantined records** are written to `store/quarantine/` only and never reach M6, M7, or M8.

---

### MF-5: CompensationRecord Has No Defined Merge Key — Duplicates Guaranteed

**Where it breaks:**  
`CompensationRecord` is a flat list on `ValidatedEntityRecord`. There's no uniqueness constraint. What prevents two CompensationRecords for the same `(kmp_id, year)` with different values ending up in validated_data?

The merge rules (Rule 5) say "pick winning value by Tier+Recency." But that's for a single field. What about the record itself? If M3 produces a CompensationRecord from XBRL and M4 produces another from PDF for the same KMP+year, does the merger:
- Merge them field-by-field into one record?  
- Pick one record wholesale?  
- Keep both?

The architecture doesn't say. "Both" is the likely implementation default, meaning validated_data has two conflicting compensation records for the same KMP+year, and the scorer has no rule for which to use.

**Fix:**  
Define a merge key: `(kmp_id, year, currency)`. Merge is field-level within matching records. If the merger sees two CompensationRecords with the same key, it merges field-by-field using Rules 1–3 (per MF-2 resolution order). The output is exactly one CompensationRecord per merge key. Conflicts go to conflict_log.

---

### MF-6: `staleness_flag` Referenced in Policy But Missing From All Dataclasses

**Where it breaks:**  
Section 4d says "set `staleness_flag = True`" for KMP with no Tier 1–2 update in 180 days. But `KMPRecord` has no `staleness_flag` field. Neither does `ValidatedEntityRecord`.

**Fix:**  
Add to `KMPRecord`:
```python
staleness_flag: bool                   # True if no Tier 1–2 source in >180 days
last_tier1_2_update: date | None       # latest source date from Tier 1–2
```

---

### MF-7: Tier 4 Definition Conflates Source Origin With Extraction Method

**Where it breaks:**  
Tier definitions:
- Tier 2: "audited annual reports (PDF)"  
- Tier 4: "AI extraction from Tier 1–3 evidence documents"

So an annual report PDF is Tier 2. But when M4 AI-extracts from that Tier 2 PDF, is the result Tier 2 or Tier 4? The tier is assigned at M2 (on the source_id), so the source is Tier 2. But Tier 4's definition says AI extraction from a Tier 2 doc is Tier 4.

This means the same source_id would need two tiers depending on the extraction method, which contradicts "Tier is assigned to each source_id at acquisition (M2)."

**Fix:**  
Tier is strictly about the **source document**, not the extraction. Drop the Tier 4/5 definitions. Instead, the extraction_method (`structured` vs `ai_bounded`) is a separate axis that Rule 3 already handles. Redefine:

```
Tier 1 (authoritative):  Official registries, XBRL filings, exchange disclosures
Tier 2 (primary):        Audited annual reports, investor relations pages
Tier 3 (secondary):      Regulatory news, verified press releases
Tier 4 (tertiary):       Unverified third-party documents, analyst reports
```

And let the merge rules handle the structured-vs-AI axis via Rule 3, which already exists. This eliminates the double-counting.

---

## PHASE-2 FINDINGS (Deferrable)

### P2-1: Pipeline Has No Retry, Checkpoint, or Idempotency Model

If M4 fails mid-extraction (timeout, bad JSON from LLM), the entire pipeline must re-run from scratch. No module stores intermediate output in a way that allows resumption. Acceptable for MVP with manual runs; unacceptable for automation in Phase 2.

**Defer fix:** Add per-module output checkpoints keyed by `(entity_id, pipeline_run_id, module)`. Allow re-entry from any module.

### P2-2: Over-Link Guard Is Single-Entity Scoped — No Cross-Entity Degree Check

If entity A has 9 relationships and entity B also links to A, A's degree becomes 10+ but the guard only evaluated at A's merge time. Phase 2 needs a global entity-degree index checked at write time.

### P2-3: `score_confidence = min(confidence)` Is Too Aggressive

One low-confidence field (e.g., 0.51) drags the entire score_confidence to 0.51 even if 15 other fields are 1.0. This distorts the signal.

**Defer fix:** Use weighted harmonic mean or a penalized average. Document the formula in the scorer spec.

### P2-4: Alias Deduplication Rules Undefined

Rule 4 says "after deduplication" but no normalization is defined. "Apple Inc." / "APPLE INC." / "Apple, Inc." will all coexist.

**Defer fix:** Define alias normalization (lowercase, strip punctuation, collapse whitespace). Low risk for MVP with manual inputs.

### P2-5: `relationship_type` Controlled Vocabulary Not Defined

`RelationshipRecord.relationship_type` says "enum from controlled vocab" but no vocab exists. AI can generate arbitrary types ("board_member", "director", "board member (non-executive)") with no normalization.

**Defer fix:** Define a closed vocabulary of ≤20 relationship types. Map AI-generated types to this vocab in M5.

### P2-6: No Cross-Entity Pipeline — Discovered Entities Are Not Processed

When processing entity A, a relationship to entity B is discovered. Does B get enqueued for processing? The architecture is single-entity-at-a-time with no queue or entity discovery protocol.

**Defer fix:** Add an entity discovery queue in Phase 2. For MVP, only process explicitly input entities.

### P2-7: No Raw Evidence Versioning — Re-Fetch Creates Ambiguity

If the same URL is re-fetched and content has changed, does it get a new `source_id` or update the old one? The architecture stores `source_hash` + `fetched_at` but doesn't define the versioning model.

**Defer fix:** Each fetch = new `source_id`. Source_ids are linked by `source_url` for lineage. Merge uses the latest `source_id` per URL within the tier's recency rules.

### P2-8: Structured Extraction Has No Error/Fallback Model

What happens when XBRL is malformed, a registry API returns 500, or a CSV has unexpected columns? No module-level error handling or quarantine is defined for M3 failures.

**Defer fix:** M3 produces `ExtractionResult = Success(records) | Failure(reason, partial_records)`. Failures go to quarantine. Acceptable to skip in MVP with manual source validation.

### P2-9: CompensationRecord Does Not Handle Multi-Currency Edge Case

A KMP may have base salary in GBP and bonus in USD (common in multinational entities). The contract has one `currency` per record. If the merge key is `(kmp_id, year, currency)`, then GBP and USD records are separate, which is correct but means the scorer must sum across currencies (requires FX rate), which is unaddressed.

**Defer fix:** Add optional `currency_normalized` + `fx_rate_used` fields in Phase 2. For MVP, assume single-currency per entity-year.

### P2-10: No Score Delta Log Contract Defined

The doc says "score changes across runs are logged in `score_delta_log`" but no schema or storage location is defined.

**Defer fix:** Define `ScoreDeltaRecord` with `(entity_id, previous_run_id, current_run_id, dimension, old_score, new_score, delta_cause)`.

### P2-11: Report Builder Has No Conflict Surfacing Spec

Section 6 Risk #7 says "report builder surfaces unresolved conflicts" but the report builder's responsibility is only "Reads ONLY validated_data + score_data." If conflicts are in validated_data's `conflict_log`, the report builder must render them — but no rendering spec exists.

**Defer fix:** Define which conflict types appear in the report, at what severity, and in what section.

### P2-12: AI Extractor Output Validation Is Unspecified

Risk #4 says "output validation rejects fields not cited in evidence." But no validation spec exists. How does M4 verify that an extracted value actually appears in the input text? String match? Semantic similarity? This is the core defense against hallucination and it's described only as a mitigation statement, not a design.

**Defer fix (but high priority for Phase 2):** Define an `EvidenceValidator` that checks: (a) `evidence_sentence` is a substring of the input evidence text, (b) extracted numeric values appear within the cited sentence. Reject extractions where (a) or (b) fail.

---

## MERGE / RECONCILE WEAKNESSES

| Weakness | Impact | Section |
|----------|--------|---------|
| Rules are listed as independent statements, not an ordered algorithm. Implementors will sequence them differently. | Different merge outcomes from same data depending on rule interpretation | MF-2 |
| No merge key for CompensationRecord — field-level vs record-level merge undefined | Duplicate compensation records in validated_data | MF-5 |
| Rule 7 KMP match relies on undefined normalization | Guaranteed KMP duplicates | MF-3 |
| Rule 5 "spread > 20%" check: 20% of what? Of the winning value? Of the smaller value? Of the average? | Inconsistent review_flag triggering | 4b Rule 5 |
| Rule 4 dedup for relationships undefined: is (from_entity, to_entity, type) the dedup key? Or does date range matter? | Duplicate relationships survive merge | 4b Rule 4 |
| Over-link guard fires at merge time but merged relationships may arrive across multiple pipeline runs — no cumulative guard | Degree limit circumvented by multiple runs | 4e |
| No conflict record for Rule 3 suppressions — AI value is "logged but does not overwrite" but ConflictRecord schema requires `resolution_rule`. What rule label gets used? | Missing conflict records from Rule 3 | 4b / 4c |

---

## DATA CONTRACT WEAKNESSES

| Weakness | Impact | Section |
|----------|--------|---------|
| Single `source_ref` per record loses per-field provenance after merge | Cannot audit individual field origins | MF-1 |
| ~~`quarantine_reasons` on validated record is contradictory~~ | **FIXED** — replaced with `record_state: RecordState` enum; module access governed by state | MF-4 |
| `staleness_flag` policy exists but no field in dataclass | Policy unenforceable | MF-6 |
| `KMPRecord.role` is a free string, not enum — "CEO", "Chief Executive Officer", "chief exec" are all valid | KMP roles unreconcilable without synonym table | MF-3 |
| `InferredRelationshipRecord` extends `RelationshipRecord` — polymorphism in a data contract makes serialization fragile | JSON serialization must handle union types correctly; easy to lose the `inference_basis` field | 3a |
| `ScoreData.field_contributions` maps dimension → field paths, but field paths are undefined (dot notation? index notation? both?) | Traceability breaks if paths don't match validated_data structure | 3b |
| `DimensionScore.confidence` aggregation method is undefined — is it min, mean, or weighted? | Scorer implementation will be inconsistent with merge-level confidence semantics | 3b |

---

## REVISED GUARDRAILS (Additions to Appendix B)

Add these to the non-negotiable invariant list:

```
 9. Every field in a merged KMPRecord or CompensationRecord carries
    per-field provenance (source_ref, confidence, extraction_method).
10. Merge rules are evaluated in a defined sequence (Step 1–6),
    not as independent unordered rules.
11. CompensationRecord is unique per (kmp_id, year, currency) after merge.
12. KMPRecord.name_raw preserves the original pre-normalization text.
13. Quarantined records never appear in validated_data. They go to a
    separate quarantine store.
14. KMP role values are normalized via a controlled synonym table
    before matching.
15. Rule 3 suppressions (AI blocked by structured) produce a
    ConflictRecord with resolution_rule = RULE_3_SUPPRESSED.
```

---

## FINAL RECOMMENDATION

**Do not start coding M5 (Merger) until MF-1 through MF-7 are resolved in this document.** The merger is the most complex module and it is the one most affected by these gaps. If you build it against the current spec, you will have to rewrite it.

Recommended resolution order:
1. Fix MF-7 (tier model) — it simplifies everything downstream.  
2. Fix MF-2 (merge algorithm) — this is the merger's spec.  
3. Fix MF-1 (per-field provenance) — changes every dataclass.  
4. Fix MF-4 (quarantine separation) — changes validation gate.  
5. Fix MF-5 (compensation merge key) — merger depends on this.  
6. Fix MF-3 (KMP normalization) — merger depends on this.  
7. Fix MF-6 (staleness field) — trivial addition.

Modules M1, M2, and M3 can be started in parallel with the above fixes since they are upstream of the merge and unaffected. M4 can start once the per-field provenance shape (MF-1) is settled so prompts return the right structure.

The architecture is 80% right. The remaining 20% is in the seams between modules — exactly where production systems fail.
