# Master Brief (v2 - Stage 0 Complete)

**Change log vs v1:** Five Stage 0 decisions locked in. Stage 1 sequencing switched from Aware to Hesta. Canonical schema adds `value_band_raw`. Portfolio-posture derivative tables dropped from Stage 1. Host-Plus encoding handled by `errors='replace'` with logging. Sunsuper-schema duplicate views merged via metadata attachment, not dual ingest. Adapter inventory expanded from 5 to 8 named adapters (Hesta, Host-Plus, and AustralianSuper added; AustralianSuper now has real-file confirmation, a completed compatibility audit, and a thin fund-specific adapter with narrow `Member Direct` production support; Cbus remains deferred). Stage-roadmap re-ordered to reflect sequencing pivot.

**AustralianSuper correction:** Real AustralianSuper files are confirmed locally. The compatibility audit is complete. A thin fund-specific `AustralianSuperPhdAdapter` is implemented on the shared SunsuperSchema path. Approved production support is intentionally narrow (`Member Direct` only), while `Stable`, `Conservative Balanced`, and `Socially Aware` remain review-gated until their mappings are approved. `AR**` option codes are not a safe identity rule on their own. No generic shared-family adapter was introduced. Cbus remains deferred.

## 1. Product in one sentence

A premium intelligence product for Australian private markets that normalises APRA Portfolio Holdings Disclosure data into a queryable layer showing which super funds have direct disclosed exposure to named companies and assets, which only have manager-level aggregate exposure, and how those exposures change over time.

## 2. Target users and jobs-to-be-done

### Hedge fund / long-short PM

The PM is not browsing for ideas; they are pressure-testing a thesis, sizing the credibility of a private-market story, and looking for cross-holder signal before capital is committed. They want to type in a private company, toll-road operator, airport asset, or external manager and immediately see which super funds hold it directly, which only disclose a manager rollup, whether ownership percentages are disclosed, and whether the exposure is new, exiting, or recurring. The job is to reduce time spent stitching together fragmented super-fund PDFs and CSVs into a view that can change position sizing, diligence priority, or channel checks inside the same meeting.

### Investment banking / ECM / M&A analyst or associate

The banker is preparing a sell-side, capital raise, or strategic update and needs a defensible map of likely institutional buyers, strategic holders, and relationship adjacency. They want to start from a company, asset class, or manager and answer: which super funds already hold comparable assets, which funds have disclosed stakes in adjacent private businesses, which managers are running money for those funds, and which holdings changed in the last semi-annual period. The job is to shorten the path from fragmented public disclosure to a pitch-ready ownership and targeting view that supports mandate origination and buyer list construction.

### Private equity / infrastructure / pensions researcher

This user tracks sector ownership patterns rather than one-off trades. They care about which funds repeatedly back a manager, which funds co-own similar infrastructure or property assets, where direct ownership is concentrated, and which disclosures are only manager-level and therefore unsuitable for asset-level conclusions. The job is to turn APRA PHD disclosures into a longitudinal map of direct versus indirect exposure by asset class, manager, geography, and reporting period, without losing the nuance of disclosure completeness.

### Ambitious finance student

The student is using the product as a serious preparation tool for pensions, infrastructure, and investment interviews rather than as a learning toy. They want to understand how Australian super funds actually express private-market exposure, how direct stakes differ from manager mandates, and how ownership networks across funds, managers, and assets are structured. The job is to arrive at a SuperRatings, ClearView, super-fund, or infrastructure interview able to discuss real holdings, manager relationships, and portfolio construction patterns with specificity.

## 3. Core MVP definition

The narrowest credible launch is a searchable holdings intelligence layer for a small initial set of funds and reporting periods that does four things well:

1. Ingest and normalise PHD data from Hesta (Stage 1 anchor), then Aware, Australian Retirement Trust across both legacy schemas, UniSuper, and Host-Plus (Stage 2).
2. Preserve and clearly label disclosure completeness so direct named holdings are never blended with manager-level aggregate exposure.
3. Resolve a useful portion of companies, managers, and assets into stable entities with human review for ambiguous matches.
4. Present company, fund, and manager pages with period-over-period change views and precise provenance back to the original filing row.

What is out of MVP:

1. Any attempt to fully unwind nested fund-of-fund structures into underlying asset ownership.
2. A crawler network for every APRA fund website beyond a pragmatic file registration workflow.
3. Public-markets intelligence layers such as director trades, substantial holders, or scheme tracking.
4. News, commentary, macro pages, alerts, or a "terminal" experience.
5. Broad quant screens like factor exposures or portfolio analytics pretending the disclosure states are equivalent.
6. Portfolio-posture derivative tables (per-fund derivative exposure by kind, asset class, and currency). These are not holdings and are explicitly dropped from Stage 1; revisit in Stage 2 or 3 if user demand surfaces.

## 4. Explicit non-goals

1. Not a Bloomberg clone.
2. Not a macro dashboard.
3. Not a market-news or newsletter product.
4. Not a live marks or pricing system.
5. Not a universal Australian funds database in v1.
6. Not a private-company valuation engine.
7. Not a cap-table product.
8. Not a fully automated knowledge graph with zero manual review.

## 5. Adapter-per-fund ingestion architecture

### Architectural stance

The audit, verified against eight source files in Stage 0, removes any justification for a "generic PHD importer." The ingestion layer must be adapter-per-fund, with a deterministic canonical output contract and versioned mapping configs reviewed by a human before production use.

### Core pipeline

1. `file_registration`
   Every inbound file is registered before parsing with fund, option if known, file lineage, source URL, checksum, file date, reporting period, and schema version guess. This is where periods are attached for formats that do not carry row-level dates.
2. `adapter_selection`
   A deterministic router chooses the concrete adapter by fund and, where needed, lineage.
3. `source_parse`
   The adapter parses raw rows or sections into source-normalised records while preserving all raw columns and section context. CSV decoding uses UTF-8 with `errors='replace'`; the count of replaced bytes is logged as a data-quality metric and surfaced in the schema-drift review when above a threshold.
4. `mapping_application`
   An approved versioned source-to-canonical mapping config converts source fields and taxonomy labels into canonical fields.
5. `normalisation`
   Shared coercion functions normalise null sentinels, dates, currency-formatted values, percentages, units, identifiers, and addresses. Per-adapter overrides exist where formats differ (the Sunsuper schema stores ownership as a bare decimal; other adapters use formatted percent strings - see Section 8 normalisation table).
6. `metadata_attachment`
   Where a single adapter publishes the same holding in multiple views (the Sunsuper schema's "All Assets" vs "Externally Managed" filters), the adapter merges into a single precise row: the value-bearing row is kept; descriptive metadata from the duplicate view (classification, geo coordinates, address, value-band, location) is attached as enrichment. No dual ingest.
7. `validation`
   Contract validation checks required provenance fields, canonical enum validity, parse success rates, row counts, and row-hash uniqueness.
8. `schema_drift_check`
   Current file headers and structural signals are compared against the last approved version for that adapter. Material drift blocks automatic ingest and routes to review.
9. `load`
   Canonical rows are written idempotently into staging and then promoted into production tables.

### Base adapter interface

Inputs:

1. Registered file metadata: `source_file_id`, `fund_id`, `suspected_adapter_key`, `reporting_period`, `source_url`, `checksum`, `received_at`.
2. Raw file bytes or parsed CSV stream.
3. Approved mapping config version for that adapter.

Outputs:

1. A set of source-normalised holding records enriched with source provenance.
2. Structural metadata: discovered sections, inferred option boundaries, observed headers, adapter warnings, parse statistics, replacement-character counts.
3. A schema fingerprint used for drift detection.

Contract with canonical layer:

1. Adapters do not write to production tables directly.
2. Adapters must emit a stable intermediate shape: one record per source holding-like row, plus source context fields.
3. Canonical coercion and taxonomy mapping happen after adapter parse, not inside bespoke parser logic, except where section state is necessary to interpret a row.
4. Every emitted row must include raw source payload and row position for traceability.
5. Portfolio-posture summaries (derivative exposure by kind, asset class, or currency) are parsed only for completeness checksum purposes and are not emitted as holdings records in Stage 1. If emitted at all, they must carry an explicit non-holding flag.

### Concrete adapter set (verified against source files)

| Adapter key | Class | Verified sample | Stage | Notes |
|-------------|-------|------------------|-------|-------|
| `HestaPhdAdapter` | Flat row | `Hesta-High-Growth-super-assets*.csv` | **Stage 1** | Cleanest schema observed: 11 columns, single option per file, UK DD/MM/YYYY dates, clear `{class}` vs `{class} Total` subtotal pattern, weighting stored as decimal fraction (no conversion needed), UTF-8 clean. Chosen as Stage 1 anchor to minimise time to canonical-contract freeze. |
| `AwarePhdAdapter` | Mini-state-machine | `Aware.csv`, `AwareProperty.csv` | Stage 2 | 14 columns, one option per file, four concatenated Schedule 8D tables, 17 embedded SUB TOTAL rows in Table 1, state-dependent name-column selection across 13 `(asset_class, internal/external)` combinations. ISO reporting date embedded in table-header string. Contains the private-company gold seam (RUMIN8, FSSSP, HARRISON AI, WESBEAM). |
| `ArtQsuperPhdAdapter` | Flat row | `ART.csv` | Stage 2 | 16 columns, single option per file, textual date ("31 December 2025") in `AsAtDate` column, `n/a` as null sentinel. |
| `SunsuperSchemaPhdAdapter` | Flat row with structured `Name Type` column | `Aus-Super.csv`, `AusSuperPHD.csv`, `Balanced_PHD__3_.csv` | Stage 2 | Internal normalised 24-column contract currently exercised by the ART-Sunsuper narrow slice. Dates are derived from file registration (no row-level date column). Publishes same holdings in multiple filter views: metadata-attachment merging required. Carries geo-coordinates and `Classification` for property/infrastructure rows. ART-Sunsuper ownership in this slice is stored as a bare decimal already in canonical fraction form (`0.18` means 18%). Do not treat this internal contract as byte-compatible with real AustralianSuper CSVs. |
| `UniSuperPhdStateMachineAdapter` | Full state machine | `UniSuper.csv` | Stage 2 | 5 columns, 16 investment options in one 26,890-row file, column headers re-emit mid-file, US MM/DD/YYYY date trap (`12/31/2025`), nine variants of scope-modifier strings must normalise. |
| `HostPlusPhdStateMachineAdapter` | Full state machine (UniSuper-class, reused) | `Host-PlusHigh_Growth.csv` | Stage 2 (late) or Stage 3 | Single option per file but structurally UniSuper-class: section-header-driven, column-header re-emission, `Total` keyword for aggregates. Encoding corruption observed upstream (`non?associated`, `Table 2 �`). Reuse UniSuper state-machine class with per-fund config rather than duplicate. |
| `AustralianSuperPhdAdapter` | Thin fund-specific adapter on the shared SunsuperSchema path | `Stable PHD (1).csv`, `Conservative PHD (1).csv`, `Socially Aware PHD.csv`, `Member Direct PHD (1).csv` | Stage 2 narrow slice implemented | Real AustralianSuper files from the official site are now confirmed in the workspace, the compatibility audit is complete, and a thin fund-specific adapter is in place on the shared SunsuperSchema path. The approved loader/admin production slice is currently the official `Member Direct PHD (1).csv` family only; broader AustralianSuper shapes (`Stable`, `Conservative Balanced`, `Socially Aware`) can parse through the adapter but remain review-gated until their mappings are approved. Identity verification relies on source URL/domain/content signals rather than `AR**` option codes alone, and no generic shared-family adapter was introduced. |
| `CbusPhdAdapter` | Unverified | *none in workspace* | Deferred | Cbus remains the genuinely deferred case: no real sample is in the workspace yet. |

### Hesta as Stage 1 anchor: rationale and tradeoff

Chosen rationale:
1. Strictly flat 11-column CSV with a stable per-file schema; fastest path to canonical-contract freeze.
2. Clean UTF-8 encoding; no corruption handling needed at Stage 1.
3. Single option per file; no state machine required.
4. Subtotal pattern (`Cash Total`, `Unlisted Equity External Total`) is suffix-distinguishable and orthogonal to the rest of the row schema.
5. Contains real internally-managed unlisted equity disclosures (Assemble HoldCo at 40.40%, Industry Super Holdings at 16.90%, Frontier Advisors at 31.00%, Land Services WA at 10.00%, Generate Capital PBC at 1.38%) sufficient to exercise the `ownership_only` contract without the state-machine or multi-table complexity of Aware.

Acknowledged tradeoff:
The Aware file contains a strictly larger private-company gold seam (RUMIN8, FSSSP at 100%, HARRISON AI, WESBEAM, SONGTRADR, XPANSIV, VICSUPER IPE Trust plus ~240 internally-managed property holdings). Hesta's gold seam is narrower. Stage 1 therefore freezes the canonical contract using Hesta's more constrained dataset; the richer Aware data populates the product in Stage 2. Acceptable because contract stability matters more than demo-day dataset breadth at this point.

### UniSuper parser design

The UniSuper parser is a state machine over a CSV token stream, not a table import. It serves as the base class for `HostPlusPhdStateMachineAdapter`, with fund-specific configuration injected.

State tracked:

1. Current investment option.
2. Current section / asset class.
3. Current scope modifier ("Held directly or by associated entities or by PSTs", etc. - normalised via regex from nine observed variants).
4. Current management style (Internally / Externally Managed; case-insensitive match).
5. Active header definition.
6. Current interpretation of the name column.
7. Row index and boundary markers.

Transitions:

1. Option header encountered: switch option scope.
2. Section header encountered: switch asset-class context.
3. Scope modifier row encountered: update scope state.
4. Management-style row encountered: update management state.
5. Column-header row encountered: swap active column interpretation and capture header fingerprint.
6. Data row encountered: parse using current state; per-row `disclosure_completeness` determined from populated-column signature, not from section defaults.
7. `Total` or aggregate row encountered: emit as `aggregate_total` with `is_aggregate = true`.

### Schema-drift detection

Drift detection compares each new file against the last approved adapter version using:

1. Header set diff.
2. Header order diff.
3. Type-distribution changes by column.
4. New or missing section labels (including minor string variants of scope modifiers).
5. New null sentinel tokens.
6. Parse-rate anomalies.
7. Row-count anomalies by option or section.
8. Encoding replacement-character count anomalies (Host-Plus baseline includes known upstream corruption; a significant increase is drift).

Blocking rule:

Any new required column absence, unknown column that appears materially, changed section structure, or parse failure above a threshold routes the file to review and prevents silent ingest into production.

### Human-in-the-loop schema approval workflow

LLM usage is permitted only in the review workflow, never in runtime execution.

Workflow:

1. New fund or drift event lands in `schema_review_queue`.
2. System shows raw headers, sample rows, prior approved mapping if any, and drift diff.
3. LLM proposes a draft field mapping and taxonomy mapping with confidence scores and notes (see ADR-03 for model selection and prompt structure).
4. Human reviewer accepts, edits, or rejects the proposed mapping.
5. Approved mapping is stored as a versioned config tied to adapter key, file lineage, and effective reporting period range.
6. Runtime pipeline uses only the approved deterministic mapping.

Review UI wireframe:

1. Left panel: file metadata, source URL, checksum, reporting period, adapter guess, schema fingerprint, encoding-replacement count.
2. Center panel: raw header grid with sample values and detected types.
3. Right panel: proposed canonical mapping, canonical asset class mapping, value/date/null coercion preview, and warnings.
4. Bottom panel: row-level preview of 10 canonical output records before approval.
5. Action bar: approve as new version, edit mapping, reject, mark as non-holding file.

### Sunsuper-schema duplicate-view metadata-attachment rule

The Sunsuper schema publishes the same holding in multiple filter views within a single file. Example: IFM Investors appears in ARST Stable as both `Filter=Externally Managed` (with precise `$ Value`) and `Filter=All Assets` (with metadata including `Value Range`, classification, optional geo, location). The adapter must:

1. Group rows by `(option_code, asset_class, name_normalised)`.
2. Identify the precise row: the one with `$ Value` populated and a filter indicating a management-style bucket.
3. Identify the metadata row(s): those with the same entity name but a broader filter (`All Assets`, `Private Equity`) and typically empty `$ Value`.
4. Emit one canonical holdings row, carrying the precise row's value plus the metadata row's `classification`, `geo_lat`, `geo_lng`, `value_band_raw`, `location`, and `address` where present.
5. Preserve raw payloads for both rows in `raw_payload_json` as an array, with a provenance entry per source row number.

If the grouping is ambiguous (e.g. two `$ Value`-bearing rows for the same entity under different asset classes), the ambiguity is logged and the rows are emitted separately. Do not silently merge across asset classes.

### Fund identity for the shared 24-column family

Do **not** infer fund identity from `AR**` option codes. Real AustralianSuper files from the official site now use `ARST`, `ARYO`, `ARSB`, and `AR2O`, so `AR` is a shared-family marker at best, not an owning-fund rule.

Primary identity signals:

1. Registered `source_fund_id` from file registration.
2. Source URL / domain and branded path tokens (`australiansuper`, `australian-retirement-trust`, `sunsuper`, etc.).
3. Content signals from observed option names and file variants.
4. Review warnings when the declared fund and non-option-code signals disagree.

Rules:

1. `source_fund_id` is authoritative from file registration metadata, not inferred from option code at parse time.
2. `AR**` codes must never be used on their own to decide between ART-Sunsuper and AustralianSuper.
3. Identity mismatches should raise a review warning, not silently rewrite the fund assignment.
4. New option-code families should be appended only from observed files, not guessed in advance.

### Onboarding AustralianSuper and Cbus

Current position:

1. AustralianSuper real files are confirmed locally; the earlier `Aus-Super = ART` assumption is retired.
2. The compatibility audit is complete.
3. A thin fund-specific `AustralianSuperPhdAdapter` is implemented on the shared SunsuperSchema path.
4. Identity verification relies on registered fund, source URL / domain, and content signals rather than `AR**` option codes.
5. The approved loader/admin production claim is narrow: official `Member Direct PHD (1).csv` only.
6. `Stable`, `Conservative Balanced`, and `Socially Aware` can parse through the adapter, but they remain review-gated until their mappings are approved.
7. No generic shared-family adapter was introduced.
8. Cbus remains deferred pending a real sample file.

Next staged work:

1. Register additional official AustralianSuper slices one option family at a time.
2. Build and review raw-profile summaries for each new slice.
3. Generate LLM-assisted draft mappings.
4. Human approves or edits mappings.
5. Run dry-load into staging.
6. Review canonical preview and disclosure completeness distribution.
7. Promote each additional slice to active loader/admin ingest only after approval.

### LLM-assisted mapping workflow, concretely

Use a frontier model for review-time mapping proposals because the volume is low and the cost of a bad mapping is high. Recommendation: `gpt-5.4`, with no auto-approval path.

The review request should include:

1. Adapter key guess and schema fingerprint.
2. Raw headers in observed order.
3. Twenty representative sample rows, including blanks and edge cases.
4. Prior approved mapping version if one exists.
5. Canonical schema field definitions and canonical asset-class enum.
6. Per-adapter normalisation table reference (see Section 8).

The structured response must include:

1. Proposed column-to-canonical field mappings.
2. Proposed source-to-canonical asset-class mappings.
3. Proposed coercion rules for dates, values, percentages, and null sentinels.
4. Confidence score and rationale per mapped field.
5. Explicit unknowns and rows that should route to manual review.

The runtime pipeline must never execute a mapping that came straight from the model. It may only execute a stored approved config version.

### Stack and execution decisions

Chosen backend and data-plane stack:

1. Python 3.12.
2. FastAPI for internal APIs and admin workflows.
3. SQLAlchemy 2.0 for ORM and query composition.
4. Alembic for migrations.
5. Pydantic v2 for schema validation at service boundaries.
6. Pytest for unit, integration, and ingestion-contract tests.

Chosen frontend stack:

1. Next.js with React and TypeScript, beginning when user-facing pages start in Stage 3 and premium presentation in Stage 4.

Rejected for v1:

1. A pandas- or Polars-first ingestion architecture. The pipeline needs row-level provenance, explicit parser state, and deterministic transforms more than dataframe convenience.
2. GraphQL as the first API surface. The read model is still evolving and the product benefits more from explicit internal endpoints than a broad schema contract.
3. LLM-driven runtime transforms. They belong in review tooling only.

### Internal API posture

Stage 1 and Stage 2 expose an internal JSON API only. The contract covers six read and admin surfaces:

1. File registration and ingest-run inspection.
2. Schema and taxonomy review queue.
3. Search.
4. Company detail.
5. Fund detail.
6. Manager detail.

Public API design is explicitly out of MVP. The internal API stabilises the product's own read models first.

## 6. Canonical data model (v1)

### Design principles

1. Preserve provenance at row level.
2. Keep disclosure completeness explicit and queryable.
3. Separate entities from observations.
4. Record unresolved relationships rather than pretending to unwind them.
5. Support manual curation without mutating original source truth.
6. Metadata enrichment (classification, geo, value-band) lives on the precise holding row rather than as separate duplicate rows.

### Core entities

#### `funds`

Represents super funds or publishing institutions.

Key fields:

1. `id`
2. `name`
3. `apra_regulated_flag`
4. `status`
5. `source_system_notes`
6. `created_at`
7. `updated_at`

#### `investment_options`

Represents a fund's investment option or pool.

Key fields:

1. `id`
2. `fund_id`
3. `source_option_code`
4. `source_option_name`
5. `canonical_option_name`
6. `lineage_key`
7. `active_from_period`
8. `active_to_period`

#### `reporting_periods`

Represents a semi-annual observation period.

Key fields:

1. `id`
2. `period_end_date`
3. `disclosure_due_date`
4. `label`
5. `source_cycle`

#### `source_files`

Tracks registered input files.

Key fields:

1. `id`
2. `fund_id`
3. `investment_option_id` nullable
4. `adapter_key`
5. `source_url`
6. `checksum`
7. `reporting_period_id`
8. `schema_fingerprint`
9. `mapping_version_id`
10. `ingest_status`
11. `publication_date` nullable
12. `version_number`
13. `supersedes_source_file_id` nullable
14. `is_current_version`
15. `superseded_at` nullable
16. `supersession_reason` nullable
17. `encoding_replacement_count` (integer; bytes replaced during UTF-8 decode - baseline informative, spike flags drift)

#### `entities`

Represents companies, assets, managers, funds, vehicles, issuers, or properties as canonical resolved nodes.

Key fields:

1. `id`
2. `entity_type`
3. `canonical_name`
4. `abn` nullable
5. `country_code` nullable
6. `is_australian_entity`
7. `confidence_tier`
8. `notes`

Recommended `entity_type` enum:

1. `company`
2. `manager`
3. `asset`
4. `fund_vehicle`
5. `property_asset`
6. `infrastructure_asset`
7. `issuer`

#### `entity_aliases`

Stores observed raw names and approved aliases.

Key fields:

1. `id`
2. `entity_id`
3. `alias`
4. `alias_normalized`
5. `source_system`
6. `source_file_id` nullable
7. `is_preferred`
8. `match_confidence`

#### `managers`

A thin convenience table or view can exist, but operationally managers should be entities with `entity_type = manager`. Do not build a parallel truth store unless performance later requires it.

#### `canonical_asset_classes`

Taxonomy dimension table.

Key fields:

1. `id`
2. `code`
3. `label`
4. `parent_code` nullable
5. `description`

#### `holdings`

One row per disclosed holding-like observation in a given fund, option, and reporting period. After adapter-level metadata-attachment merging, one canonical row represents one economic position, even when the source adapter published the position across multiple raw rows.

Required fields:

1. `id`
2. `source_file_id`
3. `source_fund_id`
4. `source_option_id`
5. `reporting_period_id`
6. `entity_id` nullable
7. `raw_name`
8. `value_aud` nullable numeric
9. `ownership_pct` nullable numeric (stored as decimal fraction per ADR-09; `4%` -> `0.04`)
10. `units` nullable numeric
11. `is_aggregate` boolean
12. `disclosure_completeness` enum (five values - see ADR-07)
13. `canonical_asset_class_id`
14. `source_asset_class_raw`
15. `source_subclass_raw` nullable
16. `address` nullable
17. `geo_lat` nullable
18. `geo_lng` nullable
19. `security_identifier_value` nullable
20. `security_identifier_type` nullable
21. **`value_band_raw`** nullable string (e.g. `<$2m`, `$10m to $50m`, `$100m to $300m`, `>$1.5Bn`; currently populated only from Sunsuper-schema "All Assets" filter rows)
22. `source_row_hash`
23. `source_row_number`
24. `raw_payload_json` (may contain multiple source-row payloads after metadata-attachment merging)
25. `ingested_at`

Additional strongly recommended fields:

1. `manager_entity_id` nullable
2. `issuer_entity_id` nullable
3. `currency_raw` nullable
4. `classification_raw` nullable (e.g. `Airport`, `Toll Road`, `Office`, `Retail`, `Industrial`, `Telco & Data`, `Electricity`, `Seaport`, `Residential` - observed in the Sunsuper schema)
5. `location_raw` nullable (free-text location where supplied, e.g. `United States` in the Sunsuper schema)
6. `parse_warning_flags`
7. `metadata_attached_from_row_numbers` (array of integers - source rows whose metadata was merged onto this canonical row; empty for single-source rows)

### `value_band_raw` handling rule

1. A row with `value_band_raw` populated and `value_aud` NULL is classified as `name_only` for exposure semantics per ADR-07. The enum does not change.
2. Queries that compute exposure totals must exclude rows with `value_band_raw` populated and `value_aud` NULL; they contribute no precise dollar.
3. The product surface may display the band string on the holding detail row as metadata. A separate UI facet ("Disclosed in value band") may surface these rows; they never enter computed totals.
4. Stage 2 or Stage 3 may add `value_aud_low` and `value_aud_high` numeric bounds parsed from the band string. Out of scope for Stage 1.

### Portfolio-posture drop rule

Derivative exposure summaries - tables in Aware (Tables 2-4), UniSuper (TABLE 2-4 by option), Host-Plus (Tables 2-4), and ART-QSuper (`Derivatives By Kind`, `Derivatives By AssetClass`, `Derivatives By Currency` rows), and the Sunsuper schema (`Derivatives` Filter rows) - are not holdings. They are per-fund or per-option posture summaries of derivative exposure decomposed by kind, asset class, or currency.

Stage 1 rule: adapters must detect and skip these rows. They are not emitted as holdings records. If needed for completeness checksums (matching published totals), they may be computed into adapter-run metadata but not written to the `holdings` table.

Stage 2/3 revisit: if user demand surfaces for a separate `portfolio_posture` view, a dedicated table can be added without disturbing the holdings schema. The decision to defer is to keep the Stage 1 data contract narrow and unambiguous about what a holding is.

Asset-class weights, sector weights, and similar aggregations that users will want to see are computed at query time from the `holdings` table (filtered to non-aggregate rows). These do not require a separate posture table.

### Versioning, restatements, and idempotency

Re-filings and restatements are first-class events, not accidental duplicates.

Rules:

1. `source_files` is the versioned truth store for filings; `holdings` rows are immutable observations attached to a specific source file version.
2. There may be only one active source file per `fund + option + reporting_period + adapter lineage` slice.
3. A restated file supersedes an earlier file by linking `supersedes_source_file_id`; old rows remain queryable for audit but are excluded from current product views by default.
4. `source_row_hash` is idempotent only within a given `source_file_id`. It must not assume rows are globally stable across restatements.
5. Period-over-period diffs run only across active filing versions unless the user explicitly requests a restatement comparison.

### Indexing and query posture

The `holdings` table is the operational centre of gravity and is indexed intentionally from Stage 1.

Required indexes:

1. Unique index on `source_file_id + source_row_hash`.
2. B-tree index on `entity_id + reporting_period_id`.
3. B-tree index on `source_fund_id + source_option_id + reporting_period_id`.
4. B-tree index on `manager_entity_id + reporting_period_id`.
5. B-tree index on `canonical_asset_class_id + reporting_period_id`.
6. B-tree index on `security_identifier_type + security_identifier_value`.
7. Partial index on non-aggregate holdings by `reporting_period_id + disclosure_completeness`.
8. Trigram GIN index on normalised raw holding name for search and candidate generation.
9. Trigram GIN index on normalised address for property and infrastructure matching.

Supporting indexes:

1. Partial unique index on `entities.abn` where not null.
2. Trigram GIN index on `entity_aliases.alias_normalized`.

Do not add PostGIS in Stage 1. Store latitude and longitude as numeric fields now and introduce geospatial extensions only when the property map becomes a real shipped surface in Stage 5.

### Relationship tables

#### `entity_relationships`

Used for explicit graph edges.

Fields:

1. `id`
2. `from_entity_id`
3. `to_entity_id`
4. `relationship_type`
5. `effective_from_period_id` nullable
6. `effective_to_period_id` nullable
7. `confidence_score`
8. `source`
9. `notes`

Recommended `relationship_type` values:

1. `alias_of`
2. `parent_of`
3. `subsidiary_of`
4. `manages`
5. `invests_in`
6. `advises`
7. `administers`
8. `is_vehicle_for`
9. `co_investor_with`

#### `holding_relationships`

Bridges a holding row to related entities when the row describes a vehicle or a manager rather than an end asset.

Fields:

1. `id`
2. `holding_id`
3. `related_entity_id`
4. `relationship_role`
5. `confidence_score`
6. `source`

Recommended `relationship_role` values:

1. `underlying_manager`
2. `underlying_vehicle`
3. `issuer`
4. `property_asset_match`
5. `fund_counterparty`

### Unwinding stance

Do not unwind nested vehicles in v1. Record them explicitly as relationships and present them as such in the UI. A manager-level mandate, a named fund vehicle, and a direct asset holding are different truths and must stay different. False precision is worse than incompleteness.

## 7. Entity resolution strategy

### Position

Entity resolution is the hardest long-term system problem after ingestion and should be treated as an ongoing operations layer, not a batch cleanup task.

### Resolution timing

Entity resolution runs after ingest as a rerunnable batch over affected slices, not inline during parse and not lazily at read time.

Why:

1. Ingestion stays deterministic and auditable.
2. Alias overrides or ABN enrichments can trigger controlled re-resolution without re-parsing source files.
3. Review-queue volume is easier to manage when new candidates arrive in batches tied to approved loads.
4. User-facing page latency does not depend on live matching.

### Resolution hierarchy

1. Deterministic identifier match first. Use ABN when available through ASIC cross-reference or curated enrichment. This is the highest-trust key for Australian entities.
2. Deterministic security identifier match second. Use ASX ticker, ISIN, or CUSIP where present for listed or issued instruments.
3. Exact normalised-name match against scoped candidate sets.
4. Fuzzy match against entity-type-constrained candidate pools.
5. Human review for ambiguous results.

### Matching method recommendation

Use Jaro-Winkler as the primary fuzzy metric for entity-name matching, supplemented by token normalisation and token containment features.

Why Jaro-Winkler:

1. It performs well on finance-style near-matches, abbreviations, punctuation variation, and transpositions.
2. It is less easily fooled than token-sort alone when word order is part of meaning.
3. It works better for shorter manager and company names where token-sort ratio can overstate similarity.

Use token-sort ratio as a secondary feature, not the primary decider, because it is helpful when names reorder but too permissive for fund vehicles with repetitive words like `Fund`, `Partners`, `Holdings`, and vintage identifiers.

### Normalisation pipeline

Before fuzzy matching:

1. Uppercase and strip punctuation.
2. Remove legal suffixes where appropriate but preserve original text.
3. Standardise ampersands, hyphens, and apostrophes.
4. Tokenise and remove stop terms like `PTY`, `LIMITED`, `LTD`, `LP`, `TRUST`, `FUND` only for similarity features, not for display.
5. Preserve numeric and vintage tokens because they often distinguish vehicles.

### Confidence scoring

Every proposed match receives a 0 to 1 confidence score based on:

1. Identifier presence.
2. Fuzzy similarity.
3. Alias table hit.
4. Entity-type consistency.
5. Address overlap where relevant.
6. Manager-versus-company ambiguity penalty.
7. Cross-period recurrence bonus.

Suggested operating bands:

1. Deterministic identifier match or approved alias override: auto-accept.
2. `0.98 to 0.999` fuzzy score with secondary evidence: fast-review queue, not silent merge.
3. `0.85 to 0.979`: normal human review queue.
4. `< 0.85`: create unresolved entity candidate or leave unmatched.

No fuzzy-only match auto-merges in v1. The cost of a false merge between a manager, vehicle, and operating company is too high.

### Manual override table

#### `entity_match_overrides`

Fields:

1. `id`
2. `raw_name_normalized`
3. `entity_type_scope`
4. `source_fund_id` nullable
5. `source_asset_class_scope` nullable
6. `matched_entity_id`
7. `action`
8. `reason`
9. `created_by`
10. `created_at`
11. `expires_at` nullable

Recommended `action` values:

1. `force_match`
2. `force_no_match`
3. `force_new_entity`
4. `redirect_to_parent`

### Human review queue

The review queue is permanent product infrastructure.

Queue items include:

1. Raw disclosed name.
2. Source fund, option, period, and asset class.
3. Top candidate matches with scores.
4. Supporting evidence: address, identifier, past matches, related managers.
5. Reviewer decision and rationale.

### Handling same private company versus similar manager names

Rules:

1. A named Australian private company disclosed by two different funds is assumed distinct only until evidence supports merging; shared ABN or strong normalised match plus sector/address evidence can merge them.
2. Manager names and fund-vehicle names must live in different candidate pools first. Do not fuzzy-match a company row against manager entities by default.
3. Vintage-bearing private equity vehicles should bias toward `fund_vehicle`, not `manager`.
4. A manager and its flagship fund should be stored as separate entities linked by `is_vehicle_for` or `manages`, not merged.

### Known cross-fund entity case: IFM Investors Pty Ltd

IFM Investors is a canonical worked example and should drive review-queue test design. Across the verified Stage 0 file set, IFM Investors appears 18+ times across five funds in combinations including manager (most funds), issuer (Sunsuper-schema fixed income), and owned entity (UniSuper discloses 30.9% ownership). A single canonical `entity_id` must serve all observations; multiple `entity_relationships` edges express the distinct roles.

### Expected accuracy ceiling

Plan around 85 to 95 percent practical accuracy, not 100 percent. The residual ambiguity is structural and not something to "solve" away. The review queue is part of the product's operating model.

## 8. Taxonomy mapping layer

### Recommended canonical asset-class enum

Use a deliberately compact but expressive canonical enum:

1. `listed_equity`
2. `unlisted_equity`
3. `listed_property`
4. `unlisted_property`
5. `listed_infrastructure`
6. `unlisted_infrastructure`
7. `fixed_income`
8. `private_debt`
9. `cash`
10. `derivatives`
11. `alternatives`
12. `multi_asset_other`

Reasoning:

1. `private_debt` deserves its own canonical class because some funds distinguish it explicitly (Aware has `FIXED INCOME (PRIVATE DEBT)` as its own asset class; the Sunsuper schema has a `Fixed Income Private Debt` sub-filter).
2. Property and infrastructure each retain listed/unlisted splits because disclosure depth and use cases differ.
3. `alternatives` exists as a pressure valve for residual categories but should be used sparingly and surfaced as lower-quality classification.
4. `multi_asset_other` is preferable to forcing ambiguous section totals into a false precise class.
5. `derivatives` exists as a canonical class but in Stage 1 no holdings rows are mapped to it; it is reserved for future use.

### Per-adapter normalisation table

Verified parse rules for Stage 1 and Stage 2 adapters. Each adapter's normalisation config encodes its column:

| Adapter | Date format | Date location | Null sentinels | Value format | Percentage format |
|---------|-------------|---------------|----------------|--------------|-------------------|
| Hesta | UK `DD/MM/YYYY` | `Effective Date` column | empty string | raw float (scientific OK) | formatted `"16.90%"` -> strip % -> divide by 100 |
| Aware | ISO `YYYY-MM-DD` in table-header suffix | Regex extract from Table 1 header row | `-`, empty | formatted `"$9,144,447"` -> strip `$,` -> parse | formatted `"4%"` -> strip % -> divide by 100 |
| ART-QSuper | Textual `31 December 2025` | `AsAtDate` column | `n/a`, empty | formatted `"$339,726,831"` -> strip `$,` -> parse | formatted `"7%"` -> strip % -> divide by 100 |
| ART-Sunsuper narrow slice / internal shared-schema contract | - (from file registration) | n/a | `nan`, `n/a`, empty | raw float | **bare decimal `0.18` already in canonical fraction form** -> parse as-is |
| AustralianSuper real 24-column variant | - (from file registration) | n/a | `nan`, blank-space, empty | raw float | numeric percentage points such as `1.09` -> divide by 100 |
| UniSuper | US `MM/DD/YYYY` (trap) | `REPORTING DATE` row (structural) | empty | raw float | formatted `"29.00%"` -> strip % -> divide by 100 |
| Host-Plus | - (from file registration / filename) | n/a | empty | formatted `"28,837,447"` -> strip `,` -> parse | formatted `"13.17%"` -> strip % -> divide by 100 |

**The 24-column family is not one uniform percentage format.** The ART-Sunsuper narrow slice uses bare decimals already in canonical fraction form, while the confirmed AustralianSuper files use numeric percentage points that still need divide-by-100 normalisation. ADR-09 holds (canonical storage is decimal fraction, always), but adapter-level parsing differs and must live in each adapter's normalisation config.

### Mapping structure

#### `taxonomy_mappings`

Fields:

1. `id`
2. `adapter_key`
3. `mapping_version`
4. `source_asset_class_raw`
5. `source_filter_raw` nullable
6. `source_sub_filter_raw` nullable
7. `source_section_raw` nullable
8. `canonical_asset_class_code`
9. `is_aggregate_default`
10. `disclosure_completeness_default`
11. `notes`
12. `approved_by`
13. `approved_at`
14. `effective_from_period_id`
15. `effective_to_period_id` nullable

### Operating model

1. LLM proposes first-pass mappings for new source labels.
2. Human approves or edits them.
3. Runtime uses only approved mapping rows.
4. Unknown labels block load or route to staging-only, depending on severity.

## 9. Disclosure completeness model

### Enum (locked at five values per ADR-07)

1. `fully_disclosed` - A named end-asset row with enough row-level detail to treat it as direct exposure rather than a manager rollup; typically includes value and may also include ownership, units, or a security identifier.
2. `value_only` - Named manager, vehicle, or other non-look-through row with dollar exposure but no underlying end-asset detail; typical externally managed rollups.
3. `ownership_only` - Named row with ownership percentage but no value; relevant for some internally managed private holdings (Aware RUMIN8 at 4%, FSSSP at 100%; Hesta internal holdings; UniSuper internally managed unlisted equity with disclosed ownership).
4. `name_only` - Name present but neither value nor ownership populated; still a valid relationship observation (Sunsuper-schema private equity fund vehicles like `Delphi Ventures VIII, L.P.`; UniSuper PE vehicle rows like `APAX EUROPE VI LP`). **This category also covers rows with `value_band_raw` populated but no precise `$ Value`** - see Section 6 `value_band_raw` handling rule.
5. `aggregate_total` - Section, class, or subtotal row rather than a true holding.

### Operating rule

Do not introduce a sixth catch-all state. Auxiliary metadata - address, classification, coordinates, value band - is stored as metadata columns on the holding row. It does not create a new disclosure tier. A row's completeness is what the row says about *exposure*, not how many descriptive columns it happens to populate.

### Product rule

UI, search, and analytics must always surface disclosure state. Computed totals must not combine `fully_disclosed`, `value_only`, `ownership_only`, and `name_only` rows unless the query explicitly opts into mixed-completeness aggregation. Rows with `value_band_raw` populated are never included in dollar totals.

## 10. Key pages and signature features

### Key pages

#### Company page

Start with a canonical entity record and show:

1. Direct disclosed holders by fund and option.
2. Ownership percentages where present.
3. Period-over-period exposure history.
4. Related aliases and entity-confidence status.
5. Related managers or vehicles, clearly labelled as indirect or unresolved.
6. Where multiple funds disclose diverging ownership percentages for the same entity, show each per-fund disclosure alongside the canonical entity and never compute a cross-fund "total ownership" figure silently. Known case: Industry Super Holdings Pty Ltd is disclosed at 16.90% by Hesta, 13.17% by Host-Plus, 14.32% by ART Balanced, 0.18% by ART Stable, and as `name_only` by UniSuper across multiple options - these are different per-option slices or per-class interpretations, not a data-quality failure to reconcile.

#### Fund page

Show:

1. Investment options.
2. Asset-class mix by disclosure completeness.
3. Top direct private holdings.
4. Manager-level aggregate exposures.
5. Change since prior reporting period.

#### Manager page

Show:

1. Funds and options that disclose exposure to the manager.
2. Asset classes where the manager appears.
3. Whether exposure is direct end-asset, named vehicle, or manager rollup.
4. Related vehicles and co-occurring funds.
5. For managers that are also owned entities (IFM Investors being the canonical case), show both the manager relationship and the ownership relationship explicitly.

#### Search

Fast universal search across companies, funds, managers, assets, aliases, addresses, and identifiers.

#### Change-over-time views

These are not standalone analytics dashboards. They are entity-centric tables showing additions, exits, and changed exposures period over period.

### Homepage

The homepage is a serious index, not a news feed. It orients the user around the product's most differentiated surfaces:

1. Search as the primary action.
2. A compact "what changed this period" strip.
3. Curated entry points into direct private company ownership, manager exposure, and mapped property/infrastructure assets.
4. A short editorial-style note explaining disclosure completeness and why the data is powerful but uneven.

### Signature features to keep

Four signature features:

1. **Named private company ownership index.** The product's gold seam and should lead positioning.
2. **Manager roll-up exposure view.** Makes the limits of disclosure useful instead of frustrating.
3. **Cross-period change tracking.** Semi-annual cadence is slow, so every change event matters.
4. **Property and infrastructure asset map.** Staged to Stage 5 but worth keeping as a flagship. The Sunsuper schema publishes geo-coordinates and `Classification` (Airport, Toll Road, Office, Seaport, Telco & Data, Residential, Retail, Electricity) for ~80 property/infrastructure rows per option; Aware publishes addresses for 218 internally-managed property rows that can be geocoded. Realistic coverage ceiling is roughly 60-80% of directly-held property and infrastructure rows mapped; externally-managed rollups are structurally unmappable because they describe a manager relationship, not an asset location.

Cut for MVP:

1. Similar-portfolio detection as a signature feature.
2. Broad ownership graph exploration as a homepage hero.

Those are interesting, but second-order compared with getting direct versus aggregate exposure right.

## 11. Search and discovery

### Search

Text search is table stakes and must support:

1. Canonical names.
2. Aliases.
3. Tickers and other identifiers.
4. Addresses and partial addresses.
5. Manager and vehicle names.

### Discovery beyond text search

#### Ownership graph traversal

Constrained form:

1. From a company, walk up to directly exposed funds and options.
2. From a fund, walk sideways to co-holders or co-managers.
3. From a manager, walk down to disclosed vehicles and up to funding super funds.

Do not ship a generic graph explorer in MVP. Ship pre-scoped traversal modules on entity pages.

#### Similar-portfolio detection

Treat as a later-stage analytical layer. It is attractive but depends on high taxonomy quality and careful treatment of incomplete disclosure states. If built too early, it will mislead users.

#### Sector and geography exposure maps

Geography maps are strong once property and infrastructure asset matching is stable. Sector maps should wait until entity resolution and taxonomy coverage are mature enough not to produce noisy output.

## 12. UI and design system direction

### Design position

The interface reads like a well-typeset financial journal that happens to be interactive, not a SaaS dashboard with prettier fonts.

### Visual system

Colour:

1. Warm off-white or cream page ground.
2. Near-black text, not pure black.
3. Restrained red-orange accent for active states, deltas, and key highlights.
4. Fine gray-beige rules and container edges.

Typography roles:

1. Serif display for page titles, hero numbers, and section openers.
2. Neutral sans for body copy and interface labels.
3. Crisp mono for metadata, identifiers, dates, percentages, and provenance labels.

Spacing system:

1. Large vertical rhythm between sections.
2. Tight row spacing inside dense data tables, but generous padding around the table block itself.
3. Thin rules and whitespace, not heavy cards, should separate information zones.

### Editorial-meets-dense-data rules

#### How tables breathe

Tables sit inside quiet wide margins with clear captions, thin row dividers, and disciplined column hierarchy. Use boldness sparingly: company or asset name leads, value is the second anchor, metadata recedes into mono. Zebra striping avoided or nearly invisible. Sticky headers fine; sticky left rails fine; thick boxed table chrome not.

#### How filters stay calm

Filters belong in collapsible side panels or top drawers with grouped chips and quiet section labels. They should feel like editorial marginalia, not command centres. Default to a small set of high-value filters: reporting period, fund, option, asset class, disclosure completeness, direct versus aggregate.

#### How numbers lead

Oversized numbers reserved for one or two facts per page: disclosed direct holders, latest disclosed value, ownership percentage, change count. Within tables, numbers align right in mono and use muted separators so they scan quickly without dominating.

#### How metadata recedes

Dates, identifiers, source file references, lineages, and confidence scores render in mono, smaller size, lighter colour, and tighter spacing. Instantly available but never visually competing with names and values.

#### How completeness and confidence are signalled

Compact textual badges with minimal fill and a strong labelling scheme, not colourful pills everywhere. Example posture: a thin outlined badge with concise labels like `Direct`, `Manager Rollup`, `Name Only`, `Value Band`, `Reviewed`, `High Confidence`. Confidence not shown as a raw score by default; tiers with score on hover or detail view.

### Component inventory

1. Dense holdings table.
2. Filter chip row.
3. Metadata block.
4. Section header with inline counts.
5. Period delta sparkline or mini-bar.
6. Disclosure completeness badge.
7. Entity confidence indicator.
8. Alias panel.
9. Relationship strip or diagram.
10. Provenance drawer with source-row details (must support multiple source-row references for metadata-attached rows).
11. Comparison table for current versus prior period.
12. Value-band badge and facet.

### Page composition

Each major page opens editorially:

1. Strong title.
2. One-sentence descriptor.
3. Two or three oversized key metrics.
4. Then dense structured data below.

The editorial opening wins attention; the dense tables win retention.

## 13. Stage-by-stage roadmap

### Stage 0 - Planning and Architecture (complete)

Deliverables:

1. Master brief v2 (this document).
2. Architecture decisions record (ADR-01 through ADR-09).
3. Canonical schema proposal.
4. Worked-example walkthrough document (verified against eight source files).
5. Design direction.
6. Adapter spec prompt for Stage 1 (Hesta).

In scope:

1. Planning only.

Out of scope:

1. Any implementation.

Demo outcome:

1. A written plan that can drive execution without re-opening first principles, plus row-level walkthroughs that expose schema weak points before code exists.

### Stage 1 - Hesta adapter + canonical schema freeze

Deliverables:

1. Hesta adapter (`HestaPhdAdapter`).
2. Postgres schema v1 with all fields specified in Section 6, including `value_band_raw` and portfolio-posture exclusion.
3. File registration workflow.
4. Shared normalisation layer for nulls, dates, values, percentages, and identifiers - Hesta-specific rules implemented per Section 8 normalisation table.
5. End-to-end ingest for one Hesta file, one reporting period.
6. Ugly admin ingestion view.
7. Internal JSON API for ingest admin and a basic entity read model.
8. Core holdings indexes per ADR-02.
9. Adapter-contract test suite: given a known Hesta file, produces a deterministic canonical output.

In scope:

1. Deterministic canonical load for Hesta only.
2. Source-row provenance.
3. Basic disclosure completeness tagging (`fully_disclosed`, `value_only`, `ownership_only`, `name_only`, `aggregate_total`).
4. UTF-8 decode with `errors='replace'` and replacement-count logging, even though Hesta does not trigger it in current files.

Out of scope:

1. Entity resolution beyond trivial identifier support.
2. Premium frontend.
3. Multi-fund comparisons.
4. Other adapters.
5. Metadata-attachment merging (not needed for Hesta; introduced in Stage 2 for the Sunsuper schema).

Risks:

1. Premature schema freeze before Aware, ART, and UniSuper stress it. Mitigation: Hesta was chosen specifically because its shape is a strict subset of the canonical contract; anything the contract needs to hold must hold for Hesta first.
2. Shipping without restatement-aware file versioning would create silent data corruption later. Mitigation: ADR-05 versioning in place from day one.

Demo outcome:

1. Show a user that one Hesta file lands in Postgres with row-level provenance, normalised values, queryable internally-managed private holdings (Assemble HoldCo, Industry Super Holdings, Frontier Advisors, Land Services WA, Generate Capital PBC), and externally-managed manager rollups clearly distinguished.

### Stage 2 - Multi-adapter ingest

Deliverables:

1. Aware adapter (with Table 1 / 2-4 separation; Tables 2-4 skipped per portfolio-posture rule).
2. Sunsuper-schema path for ART-Sunsuper, plus a thin AustralianSuper adapter that reuses only the proven shared duplicate-view merge logic.
3. ART-QSuper adapter.
4. UniSuper state-machine adapter.
5. Host-Plus state-machine adapter (reusing UniSuper base class).
6. Approved taxonomy mapping tables.
7. Schema-drift detection.
8. Review workflow for mapping approval.
9. AustralianSuper slice-by-slice mapping approval beyond `Member Direct`, and Cbus onboarding once real sample files are acquired.

In scope:

1. Multi-schema ingest.
2. Human-approved mapping configs.
3. Staging versus production gating.
4. Per-adapter normalisation rules.
5. Encoding-replacement logging with Host-Plus as the baseline test case.

Out of scope:

1. Deep entity resolution UI.
2. Styled user-facing pages.

Risks:

1. UniSuper complexity exposing schema gaps not caught by Hesta.
2. Sunsuper-schema duplicate-view merging edge cases.
3. Host-Plus encoding corruption fluctuation between periods.
4. AustralianSuper already proves the shared 24-column family is not byte-compatible across funds; Cbus may introduce a further schema change when real files arrive.

Demo outcome:

1. Show the same company or manager (IFM Investors; Industry Super Holdings; Blackbird Ventures; Generate Capital) appearing across Hesta, Aware, ART, UniSuper, and Host-Plus source data with disclosure states preserved.

### Stage 3 - Entity resolution

Deliverables:

1. Entity resolution engine.
2. Alias tables and manual override tables.
3. Match review queue.
4. Company, fund, and manager detail pages in data-first form.

In scope:

1. Resolved entity views.
2. Confidence scoring.
3. Human merge and no-merge workflows.
4. IFM Investors canonical case as review-queue test data.
5. Cross-fund ownership dispute handling per Section 10 company-page rule.

Out of scope:

1. Final design system.
2. Geographic mapping polish.

Risks:

1. False merges harming trust.
2. Review queue operational load larger than expected.

Demo outcome:

1. Show a canonical company page that unifies multiple raw disclosed names into one reviewed entity with period-over-period holdings and per-fund disclosure variance where present.

### Stage 4 - Premium frontend

Deliverables:

1. Premium frontend.
2. Design system.
3. Search experience.
4. Homepage.
5. Interaction polish.

In scope:

1. Editorial visual system.
2. Calm dense-data pages.
3. Fast search and filtering.
4. Value-band and completeness badges per Section 12 component inventory.

Out of scope:

1. ASIC cross-reference depth.
2. Public-markets signal layer.

Risks:

1. Over-designing before data trust is earned.

Demo outcome:

1. Show a finance professional a polished company and fund page they would plausibly bookmark and revisit.

### Stage 5 - ASIC and property map

Deliverables:

1. ASIC large proprietary company cross-reference.
2. Property and infrastructure geo-map.
3. Address-based cross-fund matching workflows.

In scope:

1. Australian entity enrichment.
2. Geography-based asset exploration using Sunsuper-schema geo-coordinates plus address-geocoded disclosures from other funds.

Out of scope:

1. Complete national property matching perfection.

Risks:

1. Address standardisation noise.
2. ASIC access or workflow complexity.

Demo outcome:

1. Show who appears to own stakes in a mapped infrastructure or property asset across funds and periods.

### Stage 6 - Optional public-markets layer

Deliverables:

1. Optional public-markets signal layer.
2. Integration of director trades, substantial holders, and scheme tracking if strategically justified.

In scope:

1. Only if the private-markets core is already trusted and sticky.

Out of scope:

1. Anything that dilutes the product back into a generic markets portal.

Risks:

1. Product dilution.

Demo outcome:

1. Show a thin but relevant public-markets context layer that complements rather than overwhelms the core product.

## 14. Key risks

1. PHD format variance is partly characterised and partly unknown; review-gated AustralianSuper shapes and still-unseen Cbus files may still expose additional schema variance.
2. Entity resolution will have a persistent ambiguity floor.
3. Semi-annual schema drift can silently corrupt data if not gated hard.
4. Redistribution and terms-of-use review may constrain downstream product behaviour even if the data is public.
5. Fund websites are the upstream system of record; there is no central APRA API, so file discovery, registration, and retention are operational risks.
6. Re-filings and restatements can create silent duplication or false period-over-period moves if source-file versioning is weak. Mitigated by ADR-05.
7. Upstream encoding corruption (observed in Host-Plus) can silently mask content drift. Mitigated by replacement-count logging per ADR on Host-Plus encoding.
8. Sunsuper-schema duplicate-view merging can miss an entity if normalised names diverge across views. Mitigated by logging any unmerged duplicates to review queue.
9. MVP scope can balloon if the team tries to solve graph analytics, ASIC enrichment, and polished UI simultaneously.

## 15. Manual curation vs automation

### Human-in-the-loop in v1

1. New-fund schema approval.
2. Schema-drift review and mapping updates.
3. Taxonomy mapping approval.
4. Entity-merge and no-merge review queue.
5. Ambiguous alias resolution.
6. Address-match review for high-value property and infrastructure assets.
7. Sunsuper-schema duplicate-view grouping edge cases where automatic merging is ambiguous.

### Fully automatable in v1

1. Value, percentage, date, null-sentinel, and currency-text normalisation (with per-adapter configuration per Section 8).
2. Deterministic adapter execution using approved configs.
3. Security-identifier matching where identifiers exist.
4. Reporting-period assignment from file registration.
5. Idempotent row hashing and ingestion.
6. Period-over-period diffing.
7. ABN-based entity resolution once ABN is known and curated.
8. UTF-8 decode with `errors='replace'` and replacement-count logging.
9. Sunsuper-schema duplicate-view metadata attachment where grouping is unambiguous.
10. Detection and exclusion of portfolio-posture rows (derivative exposure summaries).

## 16. Acceptance criteria per stage

### Stage 0 (met)

1. Architecture decisions are explicit (ADR-01 through ADR-09).
2. MVP scope is narrow and defensible.
3. Known audit findings are reflected as design constraints.
4. A separate decisions record exists for stack, indexing, mapping workflow, entity-resolution timing, restatements, API posture, match policy, disclosure-completeness enum, and percentage storage.
5. Worked-example walkthroughs exist for Hesta, Aware, the Sunsuper schema, ART-QSuper, UniSuper, and Host-Plus using verified row shapes.
6. The five Stage 0 decisions (sequencing pivot to Hesta, value-band handling, portfolio-posture drop, Host-Plus encoding, Sunsuper-schema metadata attachment) are integrated into the master brief and reflected in schema and adapter specs.

### Stage 1

1. A Hesta file can be registered, parsed, normalised, validated, and loaded without manual row editing.
2. Canonical holdings rows include all required provenance, completeness, and metadata fields including `value_band_raw` (NULL for Hesta but column exists).
3. Admin view can inspect ingested rows and trace them back to source.
4. Internal API serves ingest admin state and a basic entity read model without coupling the UI directly to database tables.
5. Portfolio-posture rows, if Hesta ever publishes any, are detected and skipped, not emitted as holdings.
6. Adapter-contract test suite produces deterministic canonical output for a frozen Hesta test file.

### Stage 2

1. Aware, the Sunsuper schema, ART-QSuper, UniSuper, and Host-Plus files ingest through separate approved adapters.
2. Sunsuper-schema duplicate views are merged via metadata attachment; unmerged duplicates log to review queue.
3. Unknown schema drift blocks production ingest and opens a review item.
4. Taxonomy mappings are versioned and human-approved.
5. Per-adapter normalisation rules per Section 8 are implemented and tested.
6. Encoding replacement-count baseline is established for Host-Plus.

### Stage 3

1. Entity resolution produces confidence-scored matches.
2. Reviewers can approve merges or preserve distinct entities.
3. Company, fund, and manager pages render resolved data and show unresolved ambiguity clearly.
4. IFM Investors canonical case resolves to a single entity with distinct manager, issuer, and ownership relationships.

### Stage 4

1. Search returns relevant entities and aliases quickly.
2. Page layout supports dense holdings tables without losing premium editorial feel.
3. Disclosure completeness and confidence are always visible without clutter.
4. Value-band rows surface on a separate UI facet and never appear in computed dollar totals.

### Stage 5

1. ASIC cross-reference enriches a meaningful subset of Australian private entities.
2. Property and infrastructure map can display matched assets with clear confidence and provenance.

### Stage 6

1. Optional public-markets layer does not confuse the core proposition.
2. Private-markets product surfaces remain the primary navigation and value driver.

## 17. Open questions and assumptions requiring validation

### Settled in Stage 0 (no longer open)

1. Stage 1 sequencing: Hesta first (v2 change - was Aware).
2. Value-band disclosure representation: `value_band_raw` nullable column + `name_only` classification.
3. Sunsuper-schema duplicate views: metadata attachment to single precise row.
4. Portfolio-posture derivative tables: dropped from Stage 1.
5. Host-Plus encoding corruption: tolerate via `errors='replace'` with logging.
6. Percentage storage: decimal fractions (ADR-09).
7. Disclosure-completeness enum: five states (ADR-07).
8. Entity-resolution timing: post-ingest batch (ADR-04).
9. Restatement handling: versioned `source_files` + immutable `holdings` (ADR-05).
10. Match policy: no fuzzy-only auto-merge (ADR-08).

### Still open

1. Assumption: initial product focuses on a small number of reporting periods rather than backfilling long history immediately. Recommendation: yes, start with the latest one or two periods.
2. Assumption: manual file registration workflow is acceptable before building crawlers. Recommendation: yes, for MVP.
3. Assumption: exposure totals shown separately by disclosure completeness rather than rolled into one "total exposure" number. Recommendation: yes, non-negotiable.
4. Assumption: entity pages prefer showing reviewed entities only, with unresolved rows clearly separated. Recommendation: yes.
5. Open question: should investment options be first-class navigation in the user-facing product at MVP, or mostly a filter within fund pages?
6. Open question: should manager pages include named fund vehicles as a first-class section in v1, or only as related entities?
7. Open question: what redistribution rights apply to republishing normalised holdings data and row-level extracts from super-fund sites?
8. Open question: what degree of manual research effort is acceptable for ASIC enrichment in Stage 5 if automated linkage is incomplete?
9. Open question: should homepage "what changed this period" be fully algorithmic or lightly curated in the first polished release?
10. Open question (Stage 4): precise UI treatment of cross-fund ownership disputes (the Industry Super Holdings case). The data-layer rule is settled - store raw disclosures per fund, never compute cross-fund totals silently. The visual treatment is a Stage 4 decision.
11. Open question (Stage 3): handling the "per-option slice" interpretation of the Sunsuper-schema `% Ownership` column. Observed behaviour is that the same entity appears at dramatically different percentages across options of the same fund (Industry Super Holdings at 0.18% in ARST Stable vs 14.32% in ARBA Balanced), which suggests the column may express per-option allocation slice rather than fund-level cap-table ownership. Settle during Stage 3 entity-resolution design.

## 5 highest-risk assumptions, ranked

1. Entity resolution quality will be high enough to support trusted company and manager pages without overwhelming manual review.
2. Review-gated expansions such as broader AustralianSuper shapes, plus still-unseen funds such as Cbus, will fit the adapter-plus-mapping model without requiring a materially different ingestion architecture. AustralianSuper already has a working thin-wrapper implementation with one approved official slice; Cbus still carries higher uncertainty because no real sample file has been observed.
3. Public redistribution of normalised holdings data and extracts will be legally and commercially acceptable.
4. Users will accept explicit incompleteness labels instead of demanding a single blended exposure number.
5. Semi-annual data cadence is frequent enough to produce weekly return behaviour when paired with change tracking and relationship discovery.

## 5 most important product decisions with recommendation and reasoning

1. Make disclosure completeness a first-class dimension everywhere.
   Recommendation: yes.
   Reasoning: it is the main difference between differentiated truth and misleading simplification.

2. Use one adapter per fund, with ART split into two.
   Recommendation: yes.
   Reasoning: the audit - now verified against eight source files - disproves the idea of a universal parser.

3. Do not unwind nested vehicles in v1.
   Recommendation: yes.
   Reasoning: recording explicit relationships preserves truth while avoiding false precision.

4. **Start with Hesta for the first end-to-end adapter (v2 change - was Aware).**
   Recommendation: yes.
   Reasoning: Hesta has the cleanest flat schema and ships the canonical-contract freeze fastest. Aware's richer private-company gold seam (RUMIN8, FSSSP, HARRISON AI) comes online in Stage 2, but stabilising the contract matters more than demo-day dataset breadth.

5. Treat human review as product infrastructure, not temporary ops.
   Recommendation: yes.
   Reasoning: schema approval, taxonomy approval, and entity resolution ambiguity are enduring characteristics of the data.

## 5 concrete reasons a finance professional would return weekly

1. To see which funds added, exited, or resized disclosed positions in the latest reporting cycle.
2. To check whether a private company or infrastructure asset has newly appeared across super-fund disclosures.
3. To map which managers are gaining or losing mandate exposure across major funds.
4. To pressure-test a pitch, mandate, or investment thesis against real disclosed ownership patterns.
5. To use reviewed aliases and entity links as a faster starting point than rebuilding the same ownership map from raw files.
