from __future__ import annotations

from argparse import ArgumentParser
import json
from pathlib import Path
from urllib.parse import urlencode

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import Session

from app.api.app import create_app
from app.db.models import Entity, Fund, Holding, ReportingPeriod, SourceFile
from app.db.session import get_engine
from scripts.demo_corpus import (
    DEFAULT_MANIFEST_PATH,
    DemoCorpusError,
    ManifestFund,
    ManifestSourceFile,
    load_manifest,
    require_postgres_database_url,
    sha256_file,
)


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Smoke-check an already-loaded private-beta demo corpus on PostgreSQL.")
    parser.add_argument(
        "--manifest",
        type=Path,
        default=DEFAULT_MANIFEST_PATH,
        help="Path to the demo corpus manifest JSON.",
    )
    return parser


def assert_manifest_loaded(session: Session, manifest) -> dict[str, object]:
    observed_funds: list[dict[str, object]] = []
    period = session.scalar(
        select(ReportingPeriod).where(ReportingPeriod.period_end_date == manifest.reporting_period)
    )
    if period is None:
        raise DemoCorpusError(f"Reporting period {manifest.reporting_period.isoformat()} is not loaded")

    for fund in manifest.funds:
        observed_funds.append(assert_fund_loaded(session, fund=fund, reporting_period_id=period.id))

    total_rows = sum(int(fund_summary["observed_row_count"]) for fund_summary in observed_funds)
    expected_rows = sum(fund.expected_row_count for fund in manifest.funds)
    if total_rows != expected_rows:
        raise DemoCorpusError(f"Loaded current row total {total_rows} did not match manifest total {expected_rows}")
    return {
        "reporting_period_id": period.id,
        "funds": observed_funds,
        "total_expected_rows": expected_rows,
        "total_observed_rows": total_rows,
    }


def assert_fund_loaded(session: Session, *, fund: ManifestFund, reporting_period_id: int) -> dict[str, object]:
    fund_row = session.scalar(select(Fund).where(Fund.code == fund.fund_code))
    if fund_row is None:
        raise DemoCorpusError(f"Fund {fund.fund_code!r} is not loaded")

    source_files = session.scalars(
        select(SourceFile)
        .where(
            SourceFile.fund_id == fund_row.id,
            SourceFile.adapter_key == fund.adapter_key,
            SourceFile.reporting_period_id == reporting_period_id,
            SourceFile.is_current_version.is_(True),
            SourceFile.ingest_status == "loaded",
        )
        .order_by(SourceFile.id.asc())
    ).all()
    if len(source_files) != fund.expected_source_file_count:
        raise DemoCorpusError(
            f"{fund.fund_code} current loaded source-file count {len(source_files)} did not match "
            f"{fund.expected_source_file_count}"
        )

    observed_source_files = [
        assert_source_file_loaded(session, fund=fund, source_file=source_file)
        for source_file in fund.source_files
    ]
    observed_rows = sum(int(item["observed_rows"]) for item in observed_source_files)
    row_delta = abs(observed_rows - fund.expected_row_count)
    if row_delta > fund.row_count_tolerance:
        raise DemoCorpusError(
            f"{fund.fund_code} observed {observed_rows} rows; expected {fund.expected_row_count} "
            f"+/- {fund.row_count_tolerance}"
        )

    return {
        "fund_code": fund.fund_code,
        "adapter_key": fund.adapter_key,
        "expected_source_file_count": fund.expected_source_file_count,
        "observed_source_file_count": len(source_files),
        "expected_row_count": fund.expected_row_count,
        "observed_row_count": observed_rows,
        "source_files": observed_source_files,
    }


def assert_source_file_loaded(
    session: Session,
    *,
    fund: ManifestFund,
    source_file: ManifestSourceFile,
) -> dict[str, object]:
    checksum = sha256_file(source_file.path)
    rows = session.scalars(
        select(SourceFile)
        .join(Fund, Fund.id == SourceFile.fund_id)
        .where(
            Fund.code == fund.fund_code,
            SourceFile.adapter_key == fund.adapter_key,
            SourceFile.checksum == checksum,
            SourceFile.is_current_version.is_(True),
            SourceFile.ingest_status == "loaded",
        )
    ).all()
    if len(rows) != 1:
        raise DemoCorpusError(f"{fund.fund_code} expected one loaded current source file for {source_file.path}")
    loaded = rows[0]
    if loaded.mapping_version_id != source_file.mapping_version_id:
        raise DemoCorpusError(
            f"{fund.fund_code} {source_file.path.name} mapping version {loaded.mapping_version_id!r}; "
            f"expected {source_file.mapping_version_id!r}"
        )

    observed_rows = int(
        session.scalar(select(func.count(Holding.id)).where(Holding.source_file_id == loaded.id)) or 0
    )
    if observed_rows != source_file.expected_rows:
        raise DemoCorpusError(
            f"{fund.fund_code} {source_file.path.name} observed {observed_rows} rows; "
            f"expected {source_file.expected_rows}"
        )
    return {
        "path": str(source_file.path),
        "source_file_id": loaded.id,
        "expected_rows": source_file.expected_rows,
        "observed_rows": observed_rows,
        "mapping_version_id": loaded.mapping_version_id,
        "encoding_replacement_count": int(loaded.encoding_replacement_count or 0),
    }


def assert_routes(client: TestClient, session: Session, manifest, manifest_summary: dict[str, object]) -> dict[str, object]:
    source_file_checks: list[dict[str, object]] = []
    fund_summaries = manifest_summary["funds"]
    for fund_summary in fund_summaries:
        first_source = fund_summary["source_files"][0]
        source_file_id = int(first_source["source_file_id"])
        api_response = client.get(f"/admin/source-files/{source_file_id}", params={"page": 1, "size": 50})
        _assert_ok_non_empty(api_response.status_code, api_response.text, f"source-file API {source_file_id}")
        detail = api_response.json()
        if int(detail["total_rows"]) != int(first_source["expected_rows"]):
            raise DemoCorpusError(
                f"Source-file detail {source_file_id} returned {detail['total_rows']} rows; "
                f"expected {first_source['expected_rows']}"
            )
        ui_response = client.get(f"/admin/ui/source-files/{source_file_id}", params={"page": 1, "size": 50})
        _assert_ok_non_empty(ui_response.status_code, ui_response.text, f"source-file UI {source_file_id}")
        source_file_checks.append(
            {
                "fund_code": fund_summary["fund_code"],
                "source_file_id": source_file_id,
                "total_rows": detail["total_rows"],
            }
        )

    entity_checks = []
    for check in manifest.smoke_checks.get("entity_observation_lookups", []):
        query = urlencode({"name": check["name"]})
        response = client.get(f"/entities/by-name?{query}")
        _assert_ok_non_empty(response.status_code, response.text, f"entity lookup {check['name']}")
        payload = response.json()
        if not any(row["fund_code"] == check["fund_code"] for row in payload["observations"]):
            raise DemoCorpusError(
                f"Entity lookup {check['name']!r} did not include fund {check['fund_code']!r}"
            )
        entity_checks.append(
            {
                "fund_code": check["fund_code"],
                "name": check["name"],
                "observation_count": payload["observation_count"],
            }
        )

    manager_search = manifest.smoke_checks["canonical_manager_search"]
    search_response = client.get("/search", params={"q": manager_search["query"], "kind": "manager"})
    _assert_ok_non_empty(search_response.status_code, search_response.text, "manager search")
    search_payload = search_response.json()
    if not any(row["title"] == manager_search["expected_title"] for row in search_payload["results"]):
        raise DemoCorpusError(f"Manager search did not return {manager_search['expected_title']!r}")

    fund_page_checks = []
    for fund in manifest.funds:
        response = client.get(f"/admin/ui/funds/{fund.fund_code}")
        _assert_ok_non_empty(response.status_code, response.text, f"fund detail page {fund.fund_code}")
        if fund.fund_name not in response.text:
            raise DemoCorpusError(f"Fund detail page for {fund.fund_code} did not include {fund.fund_name!r}")
        fund_page_checks.append(fund.fund_code)

    manager_check = manifest.smoke_checks["manager_detail"]
    ifm_entity = session.scalar(
        select(Entity).where(
            Entity.entity_type == "manager",
            Entity.canonical_name == manager_check["canonical_name"],
        )
    )
    if ifm_entity is None:
        raise DemoCorpusError(f"Manager entity {manager_check['canonical_name']!r} is not seeded")
    manager_response = client.get(f"/admin/ui/managers/{ifm_entity.id}")
    _assert_ok_non_empty(manager_response.status_code, manager_response.text, "IFM manager detail page")
    if manager_check["canonical_name"] not in manager_response.text:
        raise DemoCorpusError("IFM manager detail page did not include the canonical manager name")

    proof_check = manifest.smoke_checks["matched_asset_proof"]
    proof_api_response = client.get(proof_check["api_path"])
    _assert_ok_non_empty(proof_api_response.status_code, proof_api_response.text, "matched-asset proof API")
    proof_payload = proof_api_response.json()
    if int(proof_payload["matched_asset_count"]) != int(proof_check["expected_rows"]):
        raise DemoCorpusError(
            f"Matched-asset proof returned {proof_payload['matched_asset_count']} rows; "
            f"expected {proof_check['expected_rows']}"
        )
    proof_ui_response = client.get(proof_check["path"])
    _assert_ok_non_empty(proof_ui_response.status_code, proof_ui_response.text, "matched-asset proof page")
    if "data-map-panel=\"australiansuper-stable-stage5-proof\"" not in proof_ui_response.text:
        raise DemoCorpusError("Matched-asset proof page did not render the map proof panel")

    return {
        "source_file_detail_checks": source_file_checks,
        "entity_observation_lookup_checks": entity_checks,
        "manager_search_result_count": search_payload["result_count"],
        "fund_detail_pages_checked": fund_page_checks,
        "manager_detail_entity_id": ifm_entity.id,
        "matched_asset_proof_rows": proof_payload["matched_asset_count"],
    }


def _assert_ok_non_empty(status_code: int, text: str, label: str) -> None:
    if status_code != 200:
        raise DemoCorpusError(f"{label} returned HTTP {status_code}: {text[:500]}")
    if not text.strip():
        raise DemoCorpusError(f"{label} returned an empty response")


def main() -> int:
    args = build_parser().parse_args()
    manifest = load_manifest(args.manifest)
    database_url = require_postgres_database_url()
    engine = get_engine(database_url)
    try:
        with Session(engine) as session:
            manifest_summary = assert_manifest_loaded(session, manifest)
            client = TestClient(create_app())
            route_summary = assert_routes(client, session, manifest, manifest_summary)
            print(
                json.dumps(
                    {
                        "manifest_name": manifest.manifest_name,
                        "manifest_version": manifest.manifest_version,
                        "reporting_period": manifest.reporting_period.isoformat(),
                        "manifest_summary": manifest_summary,
                        "route_summary": route_summary,
                    },
                    indent=2,
                    sort_keys=True,
                )
            )
    finally:
        engine.dispose()
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
