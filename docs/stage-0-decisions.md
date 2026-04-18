# Stage 0 Decisions Record

This document freezes the contract-level decisions that should not be left implicit before Stage 1 begins.

## ADR-01: Backend And Data-Plane Stack

Chosen:

1. Python 3.12 for the backend and ingestion plane.
2. FastAPI for internal APIs and admin workflows.
3. SQLAlchemy 2.0 for ORM and query composition.
4. Alembic for migrations.
5. Pydantic v2 for boundary validation.
6. Pytest for unit, integration, and ingestion-contract tests.
7. Next.js, React, and TypeScript for the user-facing frontend starting in Stage 3.

Rejected:

1. An all-TypeScript stack for Stage 1 ingestion.
2. A dataframe-first architecture using pandas or Polars as the core execution model.

Rationale:

The ingestion problem is parser-heavy, provenance-heavy, and stateful. Python gives the cleanest path to deterministic CSV parsing, coercion, validation, and operational tooling without forcing the data plane to share the frontend stack. A dataframe-first approach is attractive for ad hoc analysis but too lossy for row-level provenance and UniSuper-style parser state. The user-facing interface can still be TypeScript later without infecting the ingestion contract now.

## ADR-02: Holdings Query And Index Strategy

Chosen:

1. Index the `holdings` table deliberately in Stage 1 rather than “after performance problems appear.”
2. Add a unique index on `source_file_id + source_row_hash`.
3. Add B-tree indexes on `entity_id + reporting_period_id`, `source_fund_id + source_option_id + reporting_period_id`, `manager_entity_id + reporting_period_id`, `canonical_asset_class_id + reporting_period_id`, and `security_identifier_type + security_identifier_value`.
4. Add trigram GIN indexes on normalized holding names and normalized addresses.
5. Add a partial unique index on `entities.abn` where present.
6. Enable `pg_trgm` early; defer PostGIS until Stage 5.

Rejected:

1. Treating indexing as an implementation detail to be deferred.
2. Adding geospatial extensions before the property map is an actual shipped surface.

Rationale:

The largest table is predictable in advance. The core queries are also predictable in advance: by entity, fund, period, asset class, identifier, and address. Indexing is therefore part of the schema contract, not optional tuning. `pg_trgm` is required early for search and candidate generation. PostGIS is useful later but would add operational weight before there is a user-facing geospatial workload.

## ADR-03: LLM-Assisted Mapping Workflow

Chosen:

1. Use `gpt-5.4` for review-time draft mapping proposals.
2. Feed the model the observed headers, representative sample rows, canonical field definitions, asset-class enum, and prior approved mapping when available.
3. Require structured output covering field mappings, taxonomy mappings, coercion rules, confidence scores, and explicit unknowns.
4. Store only human-approved mappings as executable configs.

Rejected:

1. Human-only manual mapping from scratch for every new fund or drift event.
2. Runtime execution of model-generated mappings.
3. Auto-approval of model proposals.

Rationale:

Mapping work is repetitive enough for model assistance but critical enough that determinism matters. The model should make the reviewer faster, not become part of the ingestion runtime. This keeps the operating model efficient without smuggling nondeterminism into production.

## ADR-04: Entity Resolution Timing

Chosen:

1. Run entity resolution after ingest as a rerunnable batch over the newly activated slice.
2. Re-run resolution when approved aliases, ABN enrichment, or manual overrides change the candidate landscape.

Rejected:

1. Inline matching during parse.
2. Lazy matching at read time.

Rationale:

Inline matching makes ingestion nondeterministic and harder to audit. Lazy matching pushes latency and inconsistency into user-facing pages. A batch resolver keeps ingestion clean, keeps review operations bounded, and makes re-resolution possible without re-parsing source files.

## ADR-05: Re-Filings And Restatements

Chosen:

1. Treat `source_files` as the versioned filing store.
2. Keep `holdings` immutable and tie every row to a specific source file version.
3. Allow one active source file per `fund + option + reporting_period + adapter lineage` slice.
4. Model restatements through `supersedes_source_file_id`, `version_number`, and `is_current_version`.
5. Scope `source_row_hash` idempotency within a source file, not globally.

Rejected:

1. In-place mutation of holdings rows when a restatement arrives.
2. A global row hash that assumes rows are stable across filing versions.

Rationale:

Restatements are not rare enough to hand-wave away. If the versioning model is weak, the product will later misstate adds, exits, and sizing changes. Immutable observations plus versioned source files preserve auditability and keep current views clean.

## ADR-06: API Shape

Chosen:

1. Ship an internal JSON API in Stage 1 and Stage 2.
2. Stabilize explicit endpoints for ingest admin, review queues, search, company detail, fund detail, and manager detail.
3. Defer any public API until after the internal read models are proven.

Rejected:

1. Direct UI reads from database tables as the long-term pattern.
2. GraphQL as the first contract.
3. A public API promise during MVP.

Rationale:

The product still needs room to settle its read models and disclosure semantics. Explicit internal endpoints create discipline without overcommitting to a public contract too early. GraphQL would add design surface area precisely when the data model is still being pressure-tested.

## ADR-07: Disclosure Completeness Stays A Five-State Enum

Chosen:

1. `fully_disclosed`
2. `value_only`
3. `ownership_only`
4. `name_only`
5. `aggregate_total`

Rejected:

1. Adding `partially_disclosed` as a sixth catch-all state.

Rationale:

The enum exists to explain what the row says about exposure, not to score how many descriptive columns happen to be populated. A sixth “partial” bucket would become a junk drawer and weaken the product’s most important semantic distinction. Extra metadata like address or coordinates should remain metadata.

## ADR-08: No Fuzzy-Only Auto-Merge In V1

Chosen:

1. Auto-accept only deterministic identifier matches or prior human-approved alias overrides.
2. Route even very high fuzzy scores into a fast-review queue unless they are backed by deterministic evidence.
3. Treat manager, company, and fund-vehicle pools separately before any fuzzy scoring occurs.

Rejected:

1. Score-only auto-merge bands such as `0.95 to 1.00`.

Rationale:

False merges in this product are expensive and sticky. “ABC Capital Pty Ltd” and “ABC Capital Partners” can look close enough numerically to merge while being economically different entities. Review load is a cheaper cost than losing trust.

## ADR-09: Canonical Percentage Storage Uses Decimal Fractions

Chosen:

1. Store normalized percentages such as ownership and weighting as decimal fractions, so `4%` becomes `0.04`.

Rejected:

1. Storing presentation-form percentages such as `4`.
2. Mixing conventions across fields or adapters.

Rationale:

Canonical storage should optimize for computation, not display. Decimal fractions avoid repeated interpretation bugs, align with most analytical tooling, and make cross-fund normalization unambiguous.
