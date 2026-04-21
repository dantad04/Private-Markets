# AGENTS.md

## What this repo is

A premium intelligence product for Australian private markets that normalises APRA
Portfolio Holdings Disclosure data. The differentiator is preserving disclosure
completeness and row-level provenance — direct named holdings are never blended
with manager-level aggregate exposure.

## Current project state

- `docs/master-brief.md` remains the ground truth. When in doubt, defer to it.
- `docs/project-status-through-stage4.md` holds the detailed stage lock-in.
- Stages 1–4 acceptance criteria are met at stage scope on current `HEAD`.
- Stage 2 acceptance remains met; Cbus onboarding is contingently deferred
  pending real sample files and is not a current blocker.
- Stage 5 is the active implementation stage.
- The current IFM reviewed-ABN work is accepted as a bounded Stage 5 ASIC
  cross-reference proof slice.
- That proof slice does **not** mean Stage 5 acceptance criterion 1 is met at
  stage scope.
- No property or infrastructure map work has started in this proof slice.
- The first Stage 5 implementation boundary is ASIC cross-reference proof work,
  not property or infrastructure map work.
- Do not reopen Stages 2, 3, or 4 unless you find a real regression.
- Do not broaden a Stage 5 task beyond one bounded brief-aligned slice.

## What is frozen

- `docs/master-brief.md` as source of truth, with
  `docs/project-status-through-stage4.md` as the detailed current-state lock-in.
- Stages 1–4 acceptance at stage scope on current `HEAD`.
- Stage 2 acceptance, with Cbus onboarding still contingently deferred pending
  real sample files and not a live blocker.
- The canonical holdings schema (§6 of the master brief), including
  `disclosure_completeness` enum, `value_band_raw`, `is_aggregate`, and the
  provenance fields.
- The five-value `disclosure_completeness` enum. Do not add a sixth state.
- Hesta Stage 1. Do not touch unless a real bug appears.
- Aware and ART-QSuper frozen contract fixtures. Regenerate only via the
  documented `--confirm` workflow with a recorded reason.
- Current sequencing position: Stage 5 starts with bounded ASIC
  cross-reference proof work. Do not jump ahead to the property or
  infrastructure map as the first Stage 5 slice.

## What can change, with discipline

- Schema additions via forward Alembic migrations. Do not edit the Stage 1
  migration; it is real history now.
- Bounded Stage 5 entity-enrichment and provenance work, if the brief-aligned
  slice calls for it.
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
