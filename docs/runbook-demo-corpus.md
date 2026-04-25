# Private Beta Demo Corpus Runbook

This runbook loads and smokes the accepted latest-period demo corpus for a
passworded portfolio/interview URL. It does not deploy, add auth, add public
indexing controls, or start Stage 6.

## Scope

Included:

- HESTA: 9 Superannuation files, 14,620 expected rows, period 2025-12-31.
- Aware Super: 14 IFA/IFB Investment Funds files, 19,132 expected rows, period
  2025-12-31.
- UniSuper: full source file, 25,404 expected rows, period 2025-12-31.
- AustralianSuper: 10 Superannuation files including Socially Aware, 22,917
  expected rows, period 2025-12-31.
- Cbus: 11 Superannuation files, 13,352 expected rows, period 2025-12-31.

Excluded:

- Hostplus latest-period coverage. It is accepted at stage scope but held out of
  this focused demo corpus.
- Australian Retirement Trust real 16-column minimal slice. The 27-row fixture is
  too thin for this demo.
- Legacy synthetic `ArtQsuperPhdAdapter` and `ArtSunsuperPhdAdapter` fixtures.
  They remain parser-shape evidence only.

## Prerequisites

- PostgreSQL is running and reachable.
- `DATABASE_URL` is set to a PostgreSQL SQLAlchemy URL such as
  `postgresql+psycopg://postgres@127.0.0.1:5432/private_markets_demo`.
- Python dependencies from `requirements.txt` are installed.
- Run commands from the repo root.

The demo tooling refuses to run against SQLite. Do not set or add a `PORT`
variable for this runbook; Railway provides `$PORT` only at deploy runtime and
deployment is out of scope here.

## Load

```bash
export DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:5432/private_markets_demo'
python3 -m scripts.load_demo_corpus
```

The loader runs `alembic upgrade head`, ingests each manifest file through the
existing fund-specific loader/governance paths, seeds the existing IFM manager
dependency needed by the manager page, runs deterministic entity resolution for
the loaded reporting period, and seeds the accepted AustralianSuper Stable
seven-row matched-asset proof.

The script is safely re-runnable. On an already-loaded database, source files are
matched by checksum and holdings are skipped through the existing
`source_file_id + source_row_hash` idempotency constraint.

## Smoke

```bash
export DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:5432/private_markets_demo'
python3 -m scripts.smoke_demo_corpus
```

The smoke checks:

- Exact current source-file count per included fund.
- Per-file and per-fund row counts against `config/demo_corpus_manifest.json`.
- Mapping-version IDs recorded on loaded source files.
- Representative source-file API and UI detail routes.
- Representative entity observation lookups for each fund.
- Canonical IFM manager search and manager detail page.
- Fund detail pages for all included funds.
- AustralianSuper Stable matched-asset proof API and UI page.

Any mismatch exits non-zero.

## Reset Or Wipe

For a disposable local database:

```bash
dropdb private_markets_demo
createdb private_markets_demo
export DATABASE_URL='postgresql+psycopg://postgres@127.0.0.1:5432/private_markets_demo'
python3 -m scripts.load_demo_corpus
python3 -m scripts.smoke_demo_corpus
```

If the database name, user, host, or port differ, update only the shell
connection values. Do not add repo `.env` templates in this slice.

## If Smoke Fails

1. Read the first failing message; the scripts fail on the first mismatch.
2. Confirm `DATABASE_URL` points at the intended PostgreSQL database, not SQLite
   or a stale database.
3. Re-run `python3 -m scripts.load_demo_corpus` to prove idempotent loading.
4. If a row-count or mapping-version mismatch persists, compare the affected
   file path in `config/demo_corpus_manifest.json` with the accepted fixture and
   the current adapter/governance tests before changing the manifest.
5. If a route fails but corpus counts pass, inspect the specific read-model seed
   dependency named in the failure, such as IFM manager resolution or the
   AustralianSuper Stable matched-asset proof.

## Non-Goals

- No deployment.
- No auth or password handling.
- No public indexing controls.
- No Dockerfile.
- No `.env` template.
- No new adapters, mappings, schema changes, migrations, funds, periods, or
  Stage 5 map expansion.
- No Stage 6 work.
