# AGENTS.md

## What this repo is

A premium intelligence product for Australian private markets that normalises APRA
Portfolio Holdings Disclosure data. The differentiator is preserving disclosure
completeness and row-level provenance — direct named holdings are never blended
with manager-level aggregate exposure. # Task: ART-Sunsuper adapter (Stage 2, narrow vertical slice)

Read `AGENTS.md` and the master brief before starting. This task implements the
ART-Sunsuper adapter with duplicate-view metadata attachment. It is the next
Stage 2 pressure test and exercises a rule no existing adapter touches.

## Do not

- Do not touch Hesta. Stage 1 is frozen.
- Do not broaden the admin / review UI beyond what this adapter strictly needs.
- Do not start UniSuper or Host-Plus.
- Do not edit the Stage 1 Alembic migration. Use forward migrations.
- Do not generalise shared abstractions across adapters speculatively. If you
  notice duplication, note it in the report; do not refactor now.

## Scope: narrow vertical slice

Implement ART-Sunsuper for one option code, one reporting period, using a
single fixture CSV. Breadth comes later.

## Functional requirements

1. New adapter class `ArtSunsuperPhdAdapter` following the base adapter
   interface used by Hesta / Aware / ART-QSuper.

2. ART-Sunsuper-specific parsing:
   - 24-column source schema
   - observed option codes of the `AR**` form in this ART narrow slice
   - `AR**` is **not** a valid cross-fund identity rule; confirmed AustralianSuper files also use `AR**` codes
   - dates derived from file registration (no row-level date column)
   - `nan`, `n/a`, and empty as null sentinels
   - ownership stored as bare decimal (`0.18` means 18%) — do not strip `%`,
     do not divide by 100 a second time; canonical storage remains decimal
     fraction per ADR-09
   - `$ Value` as raw float
   - `Classification`, geo-coordinates, `Value Range`, `Location`, `Address`
     preserved as metadata where present

3. Duplicate-view metadata attachment:
   - group source rows by `(option_code, asset_class, normalized_name)`
   - the **precise row** is the one with `$ Value` populated and a filter
     indicating a management-style bucket (e.g. `Externally Managed`)
   - the **metadata row(s)** are those with the same normalised name under a
     broader filter (`All Assets`, `Private Equity`) and typically empty
     `$ Value`
   - emit one canonical `holdings` row carrying the precise row's value plus
     the metadata row's `classification_raw`, `geo_lat`, `geo_lng`,
     `value_band_raw`, `location_raw`, and `address` where present
   - populate `metadata_attached_from_row_numbers` with the source row numbers
     of the attached metadata rows
   - preserve **all** contributing source-row payloads in `raw_payload_json`
     as an array, one entry per source row, each tagged with its source row
     number

4. `raw_payload_json` array support:
   - if the current column stores a single JSON object, add a forward Alembic
     migration to make it array-capable, and update the load path accordingly
   - existing Hesta / Aware / ART-QSuper rows must remain readable. If that
     requires wrapping legacy payloads in a single-element array at read time
     or via a data migration, pick one approach and justify it in the report

5. Ambiguity handling:
   - if a group contains two or more `$ Value`-bearing rows (e.g. same entity
     under different asset classes, or conflicting precise rows), do not merge
   - emit the rows separately and create an entry in `schema_review_queue`
     (or the appropriate existing queue) describing the ambiguity, the source
     file id, the group key, and the conflicting source row numbers

6. Derivative / portfolio-posture rows:
   - detect and skip rows that are derivative exposure summaries (`Derivatives`
     filter rows and any equivalent posture rows)
   - they must not appear in the `holdings` table
   - log a count of skipped posture rows in adapter-run metadata

7. Governance plumbing:
   - add an approved mapping seed `art-sunsuper-stage2-v1` (or equivalent) with
     taxonomy mappings for the source asset classes present in the fixture
   - ingested ART-Sunsuper source files must carry `mapping_version_id`
   - schema drift on ART-Sunsuper must block ingest and queue into
     `schema_review_queue`, reusing existing wiring

## Test-first discipline

Write the frozen contract fixture and tests **before** the adapter
implementation where possible. Tests must constrain the implementation, not
confirm it. That means asserting specific canonical outputs, not "output was
produced".

Required test cases:

1. **Single-source case**: a row that appears only once in the source file
   produces one canonical holding with `metadata_attached_from_row_numbers`
   empty and `raw_payload_json` containing a single-element array.

2. **Metadata-attachment case**: IFM Investors (or an equivalent entity
   present in the fixture) appears with a precise `$ Value` row and a
   separate metadata row carrying `Classification` and optional geo. The
   canonical holding must:
   - carry the precise row's `value_aud`
   - carry the metadata row's `classification_raw` and coordinates
   - have `metadata_attached_from_row_numbers` containing the metadata row's
     source row number
   - have `raw_payload_json` as an array with both source-row payloads, each
     tagged with its source row number

3. **Ambiguity case**: a crafted fixture row group with two `$ Value`-bearing
   rows for the same normalised name under different asset classes must
   produce two separate canonical rows and exactly one review-queue entry
   describing the conflict.

4. **Posture exclusion case**: a `Derivatives`-filter row must not appear in
   the resulting `holdings` rows, and the adapter-run metadata must report a
   non-zero skipped-posture count.

5. **Ownership decimal case**: a row with `% Ownership = 0.18` must produce
   `ownership_pct = 0.18` (canonical decimal fraction), not `0.0018`.

6. **`value_band_raw` case**: a row with `value_band_raw` populated and
   `$ Value` empty must produce `disclosure_completeness = "name_only"` and
   must not contribute to any exposure total.

Also include focused loader and admin-ingest tests analogous to the
ART-QSuper ones.

## Acceptance criteria

- ART-Sunsuper fixture ingests end-to-end through file registration, adapter,
  canonical load, and admin inspection.
- All six required test cases pass.
- Frozen contract fixture and regeneration script exist, matching the pattern
  used for Aware and ART-QSuper.
- `python3 -m pytest -q` passes with a test count higher than the prior 60.
- Hesta smoke path on Postgres still passes.
- No changes to the Stage 1 migration.
- `raw_payload_json` is array-capable and legacy adapters still read
  correctly.

## Report back with

- files changed
- the forward migration added (if any) and its reasoning
- how legacy `raw_payload_json` compatibility was handled
- tests added and tests run, with the total pytest count before and after
- any case where the fixture did not contain a natural example and you had
  to craft one
- any non-obvious decision, especially around the normalised-name function
  used for grouping
- what remains open for the next ART-Sunsuper iteration
The master brief in the repo is the source of truth. When in doubt, defer to it.

## Current focus

Stage 2, ART-Sunsuper adapter with duplicate-view metadata attachment.

Do not start UniSuper or Host-Plus until ART-Sunsuper is working end-to-end with
a frozen contract fixture and merge behaviour proven by tests.

## What is frozen

- The canonical holdings schema (§6 of the master brief), including
  `disclosure_completeness` enum, `value_band_raw`, `is_aggregate`, and the
  provenance fields.
- The five-value `disclosure_completeness` enum. Do not add a sixth state.
- Hesta Stage 1. Do not touch unless a real bug appears.
- Aware and ART-QSuper frozen contract fixtures. Regenerate only via the
  documented `--confirm` workflow with a recorded reason.
- Master-brief sequencing: Hesta → Aware → ART-QSuper → ART-Sunsuper → UniSuper
  → Host-Plus. Do not reorder.

## What can change, with discipline

- Schema additions via forward Alembic migrations. Do not edit the Stage 1
  migration; it is real history now.
- `raw_payload_json` needs to become array-capable to carry multiple source-row
  payloads after metadata attachment. This is a forward migration.
- New adapters, new mapping-version seeds, new taxonomy rows.
- New tests. Tests must constrain the implementation, not confirm it — assert
  specific canonical outputs, not "something was produced".

## Project rules

- Adapter-per-fund. No generic importer.
- Preserve disclosure completeness explicitly. Rows with `value_band_raw` but
  no precise value stay `name_only`.
- Derivative and portfolio-posture rows are not holdings and must be excluded.
  They may be counted for completeness checksums but never emitted as holdings.
- ART-Sunsuper duplicate views are merged by metadata attachment onto the
  precise value-bearing row — never dual-ingested.
- Ambiguous duplicates must not be silently merged. Emit separately and log or
  queue for review.
- Host-Plus decoding tolerates bad bytes with `errors="replace"` and logs the
  replacement count.
- No fuzzy-only auto-merge in entity resolution.
- Do not generalise governance abstractions speculatively. Pull shared code out
  only when a concrete second caller needs it.
- Flag roadmap drift explicitly in the task report. Do not quietly expand
  scope.

## Delivery rules for every task

Report back with:
- files changed
- commands run
- tests added and tests run
- acceptance criteria met, mapped to the task prompt
- risks introduced and what is deliberately out of scope
- what remains open
- any non-obvious decision you made that the prompt did not resolve

## Validation rules

For every meaningful change:
- `python3 -m py_compile` on changed Python files
- run focused tests for the touched adapter / loader / API area
- if migrations, runtime wiring, or API surfaces changed, run the Hesta smoke
  path on Postgres
- before calling the task done, run `python3 -m pytest -q` and report the count

Do not mark a task complete with failing or skipped tests unless the skip is
justified in the report.
