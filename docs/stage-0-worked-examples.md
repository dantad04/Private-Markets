# Stage 0 Worked Examples

This document pressure-tests the Stage 0 schema and pipeline against concrete row shapes before any Stage 1 code exists.

## Important limitation

The workspace now contains a small number of literal source CSV files, including AustralianSuper real files added during the Stage 2 compatibility audit and thin-adapter implementation. The examples below still use only facts explicitly verified in the real files and mark any unavailable source values as `pending exact sample` rather than guessing them.

That is not a minor caveat. Before Stage 1 schema freeze, this document should be updated with literal row snapshots for:

1. One Aware direct private-company row.
2. One legacy shared-family Sunsuper-schema `name_only` private-equity row.
3. One UniSuper section-header-driven row.

## Canonical normalization conventions used below

1. Percentages are stored as decimal fractions, so `4%` becomes `0.04`.
2. Currency text such as `"$9,144,447"` is stripped and stored as numeric `9144447`.
3. Null sentinels such as `-`, `nan`, `n/a`, and empty string normalize to SQL `NULL`.
4. Unknown values not present in the prompt remain `pending exact sample`, not assumed.

## Example 1: Aware Direct Private Company Row

### Verified source facts

1. Fund: Aware.
2. Adapter: `AwarePhdAdapter`.
3. Holding name: `RUMIN8 PTY LTD`.
4. Category: internally managed unlisted equity.
5. Ownership disclosed: `4%`.
6. Aware exposes management style and asset class in separate source columns.
7. Aware embeds reporting date in the table header label rather than in a row column.

### File registration outcome

| Field | Value | Note |
| --- | --- | --- |
| `source_fund_id` | `Aware` | Verified |
| `adapter_key` | `AwarePhdAdapter` | Verified |
| `reporting_period` | `pending exact sample` | Must come from file registration because the row does not carry its own date |
| `source_url` | `pending exact sample` | Not in prompt |
| `schema_fingerprint` | `aware_v1_pending` | Placeholder until literal file is registered |

### Source-parsed record

| Field | Value | Note |
| --- | --- | --- |
| `source_asset_class_raw` | `unlisted equity` | Verified conceptually from audit; exact label casing pending file |
| `management_style_raw` | `internally managed` | Verified conceptually from audit; exact label casing pending file |
| `raw_name` | `RUMIN8 PTY LTD` | Verified |
| `ownership_pct_raw` | `4%` | Verified |
| `value_aud_raw` | `pending exact sample` | Not stated in prompt |
| `units_raw` | `pending exact sample` | Not stated in prompt |
| `security_identifier_raw` | `NULL or pending exact sample` | Private company rows often lack one, but do not assume |
| `address_raw` | `pending exact sample` | Not stated in prompt |
| `source_row_number` | `pending exact sample` | Requires literal file |

### Canonical holding row

| Canonical field | Value | Note |
| --- | --- | --- |
| `raw_name` | `RUMIN8 PTY LTD` | Verified |
| `canonical_asset_class` | `unlisted_equity` | Direct consequence of audit finding |
| `is_aggregate` | `false` | This is a named end-asset, not a rollup |
| `ownership_pct` | `0.04` | Normalized from `4%` |
| `value_aud` | `pending exact sample` | Do not guess |
| `units` | `pending exact sample` | Do not guess |
| `security_identifier_value` | `pending exact sample` | Do not guess |
| `address` | `pending exact sample` | Do not guess |
| `geo_lat` | `NULL` | No audit evidence that Aware provides this on this row |
| `geo_lng` | `NULL` | No audit evidence that Aware provides this on this row |
| `disclosure_completeness` | `pending exact sample: fully_disclosed or ownership_only` | Depends on whether the literal row carries AUD value |
| `entity_id` | `unresolved in Stage 0` | Resolution is a later layer |

### Decision surfaced by this example

This row proves that management style and asset class must both survive parse. It also proves that completeness cannot be guessed from the audit summary alone; the literal row must settle whether the canonical state is `ownership_only` or `fully_disclosed`.

## Example 2: Sunsuper-Schema `name_only` Private-Equity Row

### Legacy parser-shape facts

1. Legacy fixture lineage: synthetic ART-Sunsuper/shared-family shape using the shared 24-column Sunsuper schema.
2. Adapter: `SunsuperSchemaPhdAdapter`.
3. Example row name: `Delphi Ventures VIII, L.P.`
4. Category: private equity.
5. AUD value is not populated.
6. The row must be retained as a relationship record rather than dropped.
7. Reporting period is derived from file provenance, not a row date column.
8. This fixture is parser-shape evidence only; it is not source-domain verified Australian Retirement Trust evidence.

### File registration outcome

| Field | Value | Note |
| --- | --- | --- |
| `source_fund_id` | `Australian Retirement Trust` | Legacy synthetic fixture context only; not source-domain verified |
| `adapter_key` | `SunsuperSchemaPhdAdapter` | Parser-shape fixture |
| `reporting_period` | `pending exact sample` | Derived from file provenance |
| `source_url` | `pending exact sample` | Not in prompt |
| `schema_fingerprint` | `art_sunsuper_v1_pending` | Placeholder until file registration |

### Source-parsed record

| Field | Value | Note |
| --- | --- | --- |
| `raw_name` | `Delphi Ventures VIII, L.P.` | Verified |
| `source_asset_class_raw` | `Private Equity` | Verified conceptually from audit; exact source label pending file |
| `value_aud_raw` | `NULL` | Verified |
| `ownership_pct_raw` | `NULL` | Not described in audit and should be treated as absent unless the literal row says otherwise |
| `classification_raw` | `NULL or pending exact sample` | Not stated for this row |
| `geo_lat_raw` | `NULL` | No evidence this row carries coordinates |
| `geo_lng_raw` | `NULL` | No evidence this row carries coordinates |

### Canonical holding row

| Canonical field | Value | Note |
| --- | --- | --- |
| `raw_name` | `Delphi Ventures VIII, L.P.` | Verified |
| `canonical_asset_class` | `unlisted_equity` | Recommended mapping for private-equity vehicle exposure in v1 |
| `is_aggregate` | `false` | It is a named row, not a subtotal |
| `value_aud` | `NULL` | Verified |
| `ownership_pct` | `NULL` | Verified by absence in prompt |
| `units` | `NULL` | No evidence of units |
| `disclosure_completeness` | `name_only` | This is the key contract test |
| `entity_type_candidate` | `fund_vehicle` | Should not default to manager or operating company |
| `source_row_hash` | `pending exact sample` | Requires literal row payload |

### Decision surfaced by this example

This row proves that `name_only` is not a parse failure and not an ignorable nuisance. The system must store it, let it resolve to a vehicle entity later, and expose it in search and relationship views even though it contributes no direct exposure number.

## Example 3: UniSuper Section-Header-Driven Row

### Verified source facts

1. UniSuper publishes many options in one CSV.
2. Option boundaries and asset-class sections are encoded in the file structure, not in a stable row schema.
3. Header rows reappear mid-file.
4. Header meaning changes by section.
5. `NAME OF FUND MANAGER` signals a manager-oriented row.
6. `NAME OF ISSUER/COUNTERPARTY` signals an issuer-oriented row.
7. `NAME OF INSTITUTION` signals a different semantic again.

### Parser-state walkthrough

| State field | Value | Why it matters |
| --- | --- | --- |
| `current_option` | `pending literal sample` | A UniSuper row is meaningless without current option scope |
| `current_section` | `pending literal sample` | Determines canonical asset class context |
| `active_header_name_column` | `NAME OF FUND MANAGER` or equivalent | Changes the meaning of the next data row |
| `row_type` | `data` | Only data rows become holdings |

### Canonical implication

If the active UniSuper header is `NAME OF FUND MANAGER` inside an externally managed section, the following row should usually become:

1. A named row with `is_aggregate = true`.
2. `disclosure_completeness = value_only` if a dollar value is present.
3. A manager-oriented entity candidate, not a direct company or property asset.

If the active header instead is `NAME OF ISSUER/COUNTERPARTY`, the identical column position would map to a different semantic role. That is why UniSuper cannot be ingested through a generic row parser.

### Decision surfaced by this example

This is the clearest proof that parser state is part of the data. A generic CSV import would silently misclassify rows because the same column position means different things at different moments in the file.

## What these examples already prove

1. The canonical model can accommodate direct holdings, `name_only` vehicle rows, and manager-level rollups without blending them.
2. Reporting period must be attached at file-registration time, not inferred from row columns.
3. `name_only` and `ownership_only` are legitimate states, not ingestion errors.
4. UniSuper parsing depends on state carried from surrounding rows, so its adapter must be a true state machine.
5. Restatement-aware provenance matters because every canonical record is tied back to a source file version, not just a row hash.

## What is still blocked before Stage 1 schema freeze

1. Literal source-row snapshots are still needed to replace the `pending exact sample` placeholders.
2. The exact completeness state of the Aware `RUMIN8 PTY LTD` row cannot be frozen until the row is attached.
3. The UniSuper example is structurally decisive but not yet literal because no sample row was provided in the workspace.
