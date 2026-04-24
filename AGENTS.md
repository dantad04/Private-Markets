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
- Stage 2 acceptance remains met; Cbus High Growth Accumulation Option is now
  covered by a bounded Stage 2 late-add adapter slice from a verified real
  file, while further Cbus options / periods remain future onboarding work.
- Stage 5 is complete at stage-scope acceptance.
- The current IFM reviewed-ABN work and the Virtual Communities reviewed
  identity reconciliation are accepted as bounded Stage 5 ASIC
  cross-reference proof slices.
- Virtual Communities is now reconciled and reviewed at bounded proof-slice
  scope.
- Bentham Asset Management Pty Ltd dependency creation is complete as a bounded
  Stage 5 proof slice.
- Bentham Asset Management Pty Ltd now has a completed one-entity reviewed
  identity layer on top of the earlier dependency slice.
- The current Bentham slice stays correctly within the Stage 5 ASIC / ABR
  boundary.
- The accepted Wellington dependency preflight established that the fresh
  repo-native state had no directly eligible unreviewed canonical Australian
  private manager / company entities, and that Wellington Management Australia
  Pty Ltd is the cleanest next direct candidate for a bounded canonical manager
  dependency slice.
- Wellington Management Australia Pty Ltd dependency creation is complete as a
  bounded Stage 5 proof slice.
- Wellington Management Australia Pty Ltd now has a completed one-entity
  reviewed identity layer on top of the earlier dependency slice.
- The current Wellington slice stays correctly within the Stage 5 ASIC / ABR
  boundary.
- The accepted Catalyst dependency preflight established that the fresh
  repo-native state had no directly eligible unreviewed canonical Australian
  private manager / company entities, and that Catalyst Investment Managers Pty
  Ltd is the cleanest next direct candidate for a bounded canonical manager
  dependency slice.
- Catalyst Investment Managers Pty Ltd dependency creation is complete as a
  bounded Stage 5 proof slice.
- The current Catalyst slice correctly stops short of reviewed ABR / ASIC
  identity enrichment.
- Catalyst Investment Managers Pty Ltd now has a completed one-entity reviewed
  identity layer on top of the earlier dependency slice.
- The current Catalyst slice stays correctly within the Stage 5 ASIC / ABR
  boundary.
- The accepted Alphinity dependency preflight established that the fresh
  repo-native state had no directly eligible unreviewed canonical Australian
  private manager / company entities.
- Alphinity Investment Management Pty Ltd is the cleanest next direct
  candidate for a bounded canonical manager dependency slice.
- Alphinity Investment Management Pty Ltd dependency creation is complete as a
  bounded Stage 5 proof slice.
- The current Alphinity slice correctly stops short of reviewed ABR / ASIC
  identity enrichment.
- Alphinity Investment Management Pty Ltd now has a completed one-entity
  reviewed identity layer on top of the earlier dependency slice.
- The current Alphinity slice stays correctly within the Stage 5 ASIC / ABR
  boundary.
- The fresh repo-native state has no directly eligible unreviewed canonical
  Australian private manager / company entities left in the currently
  renderable set.
- Palisade Investment Partners Limited has tight manager evidence, but its
  current ABR classification as an Australian Public Company makes it a weaker
  fit for the next Stage 5 acceptance-criterion-1 slice.
- Brandon Capital Partners is the cleanest next unresolved Australian private
  candidate from the current repo-native manager evidence.
- The correct next slice is Brandon Capital Partners canonical manager
  dependency creation only.
- Brandon Capital Partners dependency creation is complete as a bounded Stage 5
  proof slice.
- The current Brandon slice correctly stops short of reviewed ABR / ASIC
  identity enrichment.
- Stafford Capital Partners dependency creation is accepted as a dependency-only
  preparatory Stage 5 slice.
- The Stafford dependency slice is not counted as Stage 5 acceptance criterion
  1 progress.
- No brief-aligned scope drift occurred in the Stafford dependency slice.
- No property or infrastructure map work started in the Stafford dependency
  slice.
- No reviewed ABR / ASIC enrichment was completed in the Stafford dependency
  slice.
- Stafford Capital Partners reviewed identity enrichment is accepted as a
  one-entity reviewed identity proof slice.
- The Stafford reviewed-identity slice is still not counted as Stage 5
  acceptance criterion 1 progress under the strict master-brief wording.
- No brief-aligned scope drift occurred in the Stafford reviewed-identity
  slice.
- No property or infrastructure map work started in the Stafford reviewed-
  identity slice.
- No broad ASIC / ABR sweep occurred in the Stafford reviewed-identity slice.
- No unrelated cleanup occurred in the Stafford reviewed-identity slice.
- Brandon Capital Partners does not require an identity-reconciliation slice.
- Under current repo conventions, the observed Brandon Capital Partners form
  versus the ABR legal-form BRANDON CAPITAL PARTNERS PTY LTD wording is an
  alias-level variant only.
- The correct next slice is Brandon Capital Partners straight reviewed identity
  enrichment in place.
- The S2Search Australia Pty Ltd and Validly Pty Ltd ASIC cross-reference batch
  is accepted.
- Stage 5 acceptance criterion 1 is now met at stage scope: the accepted
  status/runbook checkpoint is 18 populated ASIC cross-reference entities
  including IFM.
- Stage 5 acceptance criterion 2 is now met at stage scope: the accepted
  bounded proof is the seven-row AustralianSuper Stable matched-asset map
  route at `/admin/ui/matched-assets/australiansuper-stable-stage5-proof`.
- The accepted criterion-2 proof uses a server-rendered SVG coordinate plot,
  an adjacent seven-item plotted-asset list, and the retained provenance table
  to display exactly seven matched property/infrastructure assets with visible
  confidence and source-row provenance.
- The criterion-2 proof uses no geocoding, no external map provider, no
  cross-option matching, and no cross-fund matching.
- The criterion-2 proof is a bounded Stage 5 acceptance proof; it is not
  complete national, super-fund-wide, property, or infrastructure map coverage.
- Stage 5 overall is now complete at stage-scope acceptance.
- No Stage 6 or public-markets work has started.
- The 18-count checkpoint is recorded only in status/runbook context; it does
  not rewrite the master brief's qualitative Stage 5 acceptance criterion.
- The seven-row map-proof checkpoint is recorded only in status/runbook context;
  it does not rewrite the master brief's qualitative Stage 5 acceptance
  criterion or claim comprehensive map coverage.
- Do not reopen Stages 2, 3, or 4 unless you find a real regression.
- Do not broaden future roadmap work beyond one bounded brief-aligned slice.

## What is frozen

- `docs/master-brief.md` as source of truth, with
  `docs/project-status-through-stage4.md` as the detailed current-state lock-in.
- Stages 1–4 acceptance at stage scope on current `HEAD`.
- Stage 2 acceptance, with Cbus High Growth now covered by a bounded
  verified-file late-add adapter slice; further Cbus options / periods remain
  future onboarding work and are not a live blocker.
- The canonical holdings schema (§6 of the master brief), including
  `disclosure_completeness` enum, `value_band_raw`, `is_aggregate`, and the
  provenance fields.
- The five-value `disclosure_completeness` enum. Do not add a sixth state.
- Hesta Stage 1. Do not touch unless a real bug appears.
- Aware and ART-QSuper frozen contract fixtures. Regenerate only via the
  documented `--confirm` workflow with a recorded reason.
- Current sequencing position: Stage 5 is complete at stage-scope acceptance.
  Do not start Stage 6, public-markets work, or product-grade map expansion
  without a separate bounded task.

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
