from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import asdict, dataclass
from datetime import UTC, datetime
import json
import os
from pathlib import Path
import subprocess
import sys

from sqlalchemy import func, select

from app.db.models import Entity, Holding, ReportingPeriod, SourceFile
from app.db.session import get_engine
from app.entity_resolution.australiansuper_stable_matched_assets import (
    ensure_australiansuper_stable_matched_asset_proof,
)
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.entity_resolution.ifm_seed import IFM_CANONICAL_NAME, ensure_ifm_seed
from app.ingest.loader import (
    LoadSummary,
    get_or_create_reporting_period,
    ingest_australiansuper_local_file,
    ingest_aware_local_file,
    ingest_cbus_local_file,
    ingest_hesta_local_file,
    ingest_unisuper_local_file,
)
from scripts.demo_corpus import (
    DEFAULT_MANIFEST_PATH,
    DemoCorpusError,
    ManifestFund,
    ManifestSourceFile,
    REPO_ROOT,
    load_manifest,
    require_postgres_database_url,
)


LOADERS = {
    "HestaPhdAdapter": ingest_hesta_local_file,
    "AwarePhdAdapter": ingest_aware_local_file,
    "UniSuperPhdStateMachineAdapter": ingest_unisuper_local_file,
    "AustralianSuperPhdAdapter": ingest_australiansuper_local_file,
    "CbusPhdAdapter": ingest_cbus_local_file,
}


@dataclass(frozen=True)
class LoadedSourceFileSummary:
    path: str
    source_file_id: int
    expected_rows: int
    rows_staged: int
    rows_inserted: int
    rows_skipped_existing: int
    mapping_version_id: str | None
    expected_mapping_version_id: str | None
    encoding_replacement_count: int
    schema_fingerprint: str
    warnings: list[str]


@dataclass(frozen=True)
class LoadedFundSummary:
    fund_code: str
    fund_name: str
    adapter_key: str
    reporting_period: str
    expected_source_file_count: int
    loaded_source_file_count: int
    expected_row_count: int
    rows_staged: int
    rows_inserted: int
    rows_skipped_existing: int
    row_count_tolerance: int
    mapping_versions: list[str | None]
    encoding_replacement_count: int
    source_files: list[LoadedSourceFileSummary]


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Load the accepted private-beta demo corpus into PostgreSQL.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Path to the demo corpus manifest JSON.",
    )
    return parser


def run_alembic_upgrade_head(env: dict[str, str]) -> str:
    result = subprocess.run(
        [sys.executable, "-m", "alembic", "upgrade", "head"],
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise DemoCorpusError(
            "alembic upgrade head failed\nstdout:\n{stdout}\nstderr:\n{stderr}".format(
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
            )
        )
    return result.stdout.strip()


def load_fund(session, fund: ManifestFund, reporting_period_id: int) -> LoadedFundSummary:
    loader = LOADERS.get(fund.adapter_key)
    if loader is None:
        raise DemoCorpusError(f"No demo corpus loader is registered for adapter {fund.adapter_key!r}")

    source_summaries: list[LoadedSourceFileSummary] = []
    for source_file in fund.source_files:
        summary = loader(
            session,
            fund_code=fund.fund_code,
            fund_name=fund.fund_name,
            file_path=str(source_file.path),
            reporting_period_id=reporting_period_id,
            received_at=datetime(2026, 4, 25, tzinfo=UTC),
        )
        loaded = _source_file_summary(session, source_file=source_file, summary=summary)
        if loaded.rows_staged != source_file.expected_rows:
            raise DemoCorpusError(
                f"{fund.fund_code} {source_file.path.name} staged {loaded.rows_staged} rows; "
                f"expected {source_file.expected_rows}"
            )
        if loaded.mapping_version_id != source_file.mapping_version_id:
            raise DemoCorpusError(
                f"{fund.fund_code} {source_file.path.name} mapping version {loaded.mapping_version_id!r}; "
                f"expected {source_file.mapping_version_id!r}"
            )
        source_summaries.append(loaded)

    rows_staged = sum(item.rows_staged for item in source_summaries)
    row_delta = abs(rows_staged - fund.expected_row_count)
    if row_delta > fund.row_count_tolerance:
        raise DemoCorpusError(
            f"{fund.fund_code} staged {rows_staged} rows; expected {fund.expected_row_count} "
            f"+/- {fund.row_count_tolerance}"
        )

    return LoadedFundSummary(
        fund_code=fund.fund_code,
        fund_name=fund.fund_name,
        adapter_key=fund.adapter_key,
        reporting_period=fund.reporting_period.isoformat(),
        expected_source_file_count=fund.expected_source_file_count,
        loaded_source_file_count=len(source_summaries),
        expected_row_count=fund.expected_row_count,
        rows_staged=rows_staged,
        rows_inserted=sum(item.rows_inserted for item in source_summaries),
        rows_skipped_existing=sum(item.rows_skipped_existing for item in source_summaries),
        row_count_tolerance=fund.row_count_tolerance,
        mapping_versions=sorted({item.mapping_version_id for item in source_summaries}, key=lambda item: item or ""),
        encoding_replacement_count=sum(item.encoding_replacement_count for item in source_summaries),
        source_files=source_summaries,
    )


def seed_demo_read_model_dependencies(session, *, reporting_period_id: int) -> dict[str, object]:
    ifm_entity = ensure_ifm_seed(session)
    resolution_summary = resolve_entities_deterministically(session, reporting_period_id=reporting_period_id)
    matched_asset_relationships = ensure_australiansuper_stable_matched_asset_proof(session)
    unresolved_rows_remaining = int(
        session.scalar(
            select(func.count(Holding.id)).where(
                Holding.reporting_period_id == reporting_period_id,
                Holding.raw_name.is_not(None),
                Holding.entity_id.is_(None),
            )
        )
        or 0
    )
    return {
        "ifm_entity_id": ifm_entity.id,
        "ifm_canonical_name": IFM_CANONICAL_NAME,
        "deterministic_resolution": {
            "reporting_period_id": resolution_summary.reporting_period_id,
            "holdings_scanned": resolution_summary.holdings_scanned,
            "holdings_skipped_prelinked": resolution_summary.holdings_skipped_prelinked,
            "total_matches": resolution_summary.total_matches,
            "exact_name_auto_links": resolution_summary.exact_name_auto_links,
            "unresolved_rows_remaining": unresolved_rows_remaining,
        },
        "matched_asset_relationship_count": len(matched_asset_relationships),
    }


def _source_file_summary(
    session,
    *,
    source_file: ManifestSourceFile,
    summary: LoadSummary,
) -> LoadedSourceFileSummary:
    loaded_source_file = session.get(SourceFile, summary.source_file_id)
    if loaded_source_file is None:
        raise DemoCorpusError(f"Loaded source file {summary.source_file_id} disappeared before summary")
    return LoadedSourceFileSummary(
        path=str(source_file.path.relative_to(REPO_ROOT)),
        source_file_id=summary.source_file_id,
        expected_rows=source_file.expected_rows,
        rows_staged=summary.rows_staged,
        rows_inserted=summary.rows_inserted,
        rows_skipped_existing=summary.rows_skipped_existing,
        mapping_version_id=loaded_source_file.mapping_version_id,
        expected_mapping_version_id=source_file.mapping_version_id,
        encoding_replacement_count=int(loaded_source_file.encoding_replacement_count or 0),
        schema_fingerprint=summary.schema_fingerprint,
        warnings=summary.warnings,
    )


def main() -> int:
    args = build_parser().parse_args()
    manifest = load_manifest(args.manifest)
    database_url = require_postgres_database_url()

    env = os.environ.copy()
    env["DATABASE_URL"] = database_url
    migration_stdout = run_alembic_upgrade_head(env)

    engine = get_engine(database_url)
    try:
        with session_scope(engine) as session:
            reporting_period = get_or_create_reporting_period(session, manifest.reporting_period)
            fund_summaries = [
                load_fund(session, fund=fund, reporting_period_id=reporting_period.id)
                for fund in manifest.funds
            ]
            read_model_summary = seed_demo_read_model_dependencies(
                session,
                reporting_period_id=reporting_period.id,
            )
            entity_count = int(session.scalar(select(func.count(Entity.id))) or 0)
            total_current_rows = int(
                session.scalar(
                    select(func.count(Holding.id))
                    .join(SourceFile, SourceFile.id == Holding.source_file_id)
                    .where(
                        SourceFile.is_current_version.is_(True),
                        SourceFile.ingest_status == "loaded",
                    )
                )
                or 0
            )
            output = {
                "manifest_name": manifest.manifest_name,
                "manifest_version": manifest.manifest_version,
                "database_url_driver": "postgresql",
                "reporting_period": manifest.reporting_period.isoformat(),
                "alembic_stdout": migration_stdout,
                "funds": [_to_jsonable_fund_summary(summary) for summary in fund_summaries],
                "read_model_dependencies": read_model_summary,
                "entity_count": entity_count,
                "total_expected_rows": sum(fund.expected_row_count for fund in manifest.funds),
                "total_rows_staged": sum(summary.rows_staged for summary in fund_summaries),
                "total_rows_inserted": sum(summary.rows_inserted for summary in fund_summaries),
                "total_rows_skipped_existing": sum(summary.rows_skipped_existing for summary in fund_summaries),
                "total_current_rows": total_current_rows,
            }
    finally:
        engine.dispose()

    print(json.dumps(output, indent=2, sort_keys=True))
    return 0


def _to_jsonable_fund_summary(summary: LoadedFundSummary) -> dict[str, object]:
    payload = asdict(summary)
    payload["source_files"] = [asdict(item) for item in summary.source_files]
    return payload


class session_scope:
    def __init__(self, engine):
        self.engine = engine
        self.session = None

    def __enter__(self):
        from sqlalchemy.orm import Session

        self.session = Session(self.engine)
        return self.session

    def __exit__(self, exc_type, exc, traceback) -> bool:
        if self.session is None:
            return False
        try:
            if exc_type is None:
                self.session.commit()
            else:
                self.session.rollback()
        finally:
            self.session.close()
        return False


if __name__ == "__main__":
    raise SystemExit(main())
