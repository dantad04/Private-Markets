from __future__ import annotations

from argparse import ArgumentParser
from datetime import date
import json
import os
from pathlib import Path
import shutil
import socket
import subprocess
import tempfile
import time
from urllib.error import HTTPError, URLError
from urllib.parse import urlencode
from urllib.request import Request, urlopen

from sqlalchemy import create_engine, func, inspect, select
from sqlalchemy.orm import Session

from app.db.models import Holding, InvestmentOption, ReportingPeriod, SchemaReviewQueue


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_PATH = (REPO_ROOT / "tests/fixtures/real/UniSuper.csv").resolve()
EXPECTED_MAPPING_VERSION_ID = "unisuper-stage2-v1"
EXPECTED_FINGERPRINT = "7dc5e32ce188c76fae55f3f4a1c0f09d79eb55ceb9c27a378cb905f222b31cb5"
EXPECTED_OPTIONS = {
    "Australian Bond",
    "Australian Dividend Income",
    "Australian Income",
    "Australian Shares",
    "Balanced",
    "Cash",
    "Conservative",
    "Conservative Balanced",
    "Global Companies in Asia",
    "Global Environmental Opportunities",
    "Growth",
    "High Growth",
    "International Shares",
    "Listed Property",
    "Sustainable Balanced",
    "Sustainable High Growth",
}


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Run the UniSuper 2025-12-31 latest-period smoke path against a fresh database.")
    parser.add_argument(
        "--database-backend",
        choices=("sqlite", "postgres"),
        default="sqlite",
        help="Database backend to use when --database-url is not supplied.",
    )
    parser.add_argument("--database-url", help="Optional SQLAlchemy database URL.")
    parser.add_argument("--port", type=int, help="Optional fixed localhost port for uvicorn.")
    return parser


def run_command(command: list[str], *, env: dict[str, str]) -> subprocess.CompletedProcess[str]:
    result = subprocess.run(
        command,
        cwd=REPO_ROOT,
        env=env,
        capture_output=True,
        text=True,
        check=False,
    )
    if result.returncode != 0:
        raise RuntimeError(
            "Command failed: {command}\nstdout:\n{stdout}\nstderr:\n{stderr}".format(
                command=" ".join(command),
                stdout=result.stdout.strip(),
                stderr=result.stderr.strip(),
            )
        )
    return result


def choose_port() -> int:
    with socket.socket(socket.AF_INET, socket.SOCK_STREAM) as sock:
        sock.bind(("127.0.0.1", 0))
        return int(sock.getsockname()[1])


def request_json(method: str, url: str, payload: dict[str, object] | None = None) -> dict[str, object] | list[object]:
    body = None
    headers = {}
    if payload is not None:
        body = json.dumps(payload).encode("utf-8")
        headers["Content-Type"] = "application/json"
    request = Request(url, data=body, headers=headers, method=method)
    with urlopen(request, timeout=60) as response:
        return json.loads(response.read().decode("utf-8"))


def request_text(url: str) -> str:
    with urlopen(url, timeout=60) as response:
        return response.read().decode("utf-8")


def wait_for_server(base_url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.time() + 30
    while time.time() < deadline:
        if process.poll() is not None:
            output = ""
            if process.stdout is not None:
                output = process.stdout.read()
            raise RuntimeError(f"uvicorn exited before startup completed.\n{output}")
        try:
            request_text(f"{base_url}/admin/ui/source-files")
            return
        except (HTTPError, URLError):
            time.sleep(0.25)
    raise RuntimeError("Timed out waiting for uvicorn to boot")


def require_executable(name: str) -> None:
    if shutil.which(name) is None:
        raise RuntimeError(f"Required executable {name!r} was not found on PATH")


def start_temp_postgres(tempdir_path: Path, env: dict[str, str]) -> tuple[str, list[str]]:
    require_executable("initdb")
    require_executable("pg_ctl")
    require_executable("psql")

    data_dir = tempdir_path / "pgdata"
    log_path = tempdir_path / "postgres.log"
    port = choose_port()

    run_command(["initdb", "-D", str(data_dir), "-A", "trust", "-U", "postgres"], env=env)
    run_command(
        ["pg_ctl", "-D", str(data_dir), "-l", str(log_path), "-o", f"-p {port}", "-w", "start"],
        env=env,
    )
    run_command(
        [
            "psql",
            "-h",
            "127.0.0.1",
            "-p",
            str(port),
            "-U",
            "postgres",
            "-d",
            "postgres",
            "-c",
            "CREATE DATABASE unisuper_smoke",
        ],
        env=env,
    )
    return (
        f"postgresql+psycopg://postgres@127.0.0.1:{port}/unisuper_smoke",
        ["pg_ctl", "-D", str(data_dir), "-m", "fast", "stop"],
    )


def assert_expected_tables(database_url: str) -> list[str]:
    engine = create_engine(database_url, future=True)
    try:
        table_names = sorted(inspect(engine).get_table_names())
    finally:
        engine.dispose()
    expected = {
        "funds",
        "reporting_periods",
        "investment_options",
        "source_files",
        "canonical_asset_classes",
        "holdings",
        "entities",
        "entity_aliases",
        "entity_relationships",
        "holding_relationships",
        "adapter_mapping_versions",
        "taxonomy_mappings",
        "schema_review_queue",
    }
    missing = sorted(expected.difference(table_names))
    if missing:
        raise RuntimeError(f"Expected schema tables were missing after migration: {missing}")
    return table_names


def ensure_reporting_period(database_url: str) -> int:
    engine = create_engine(database_url, future=True)
    try:
        with Session(engine) as session:
            period = session.scalar(
                select(ReportingPeriod).where(ReportingPeriod.period_end_date == date(2025, 12, 31))
            )
            if period is None:
                period = ReportingPeriod(
                    period_end_date=date(2025, 12, 31),
                    disclosure_due_date=date(2026, 3, 31),
                    label="2025-12-31",
                    source_cycle="semi_annual",
                )
                session.add(period)
                session.commit()
            return int(period.id)
    finally:
        engine.dispose()


def load_db_summary(database_url: str) -> dict[str, object]:
    engine = create_engine(database_url, future=True)
    try:
        with Session(engine) as session:
            option_names = set(session.scalars(select(InvestmentOption.source_option_name)).all())
            if option_names != EXPECTED_OPTIONS:
                raise RuntimeError(f"Unexpected UniSuper options: {sorted(option_names)}")
            review_count = session.scalar(select(func.count(SchemaReviewQueue.id))) or 0
            if review_count != 0:
                raise RuntimeError(f"Expected no schema review queue items, got {review_count}")
            return {
                "aggregate_total_rows": int(
                    session.scalar(select(func.count(Holding.id)).where(Holding.is_aggregate.is_(True))) or 0
                ),
                "holding_rows": int(session.scalar(select(func.count(Holding.id))) or 0),
                "investment_options": sorted(option_names),
                "schema_review_queue_items": int(review_count),
            }
    finally:
        engine.dispose()


def main() -> int:
    args = build_parser().parse_args()
    require_executable("alembic")
    require_executable("uvicorn")

    with tempfile.TemporaryDirectory(prefix="unisuper-latest-period-smoke-") as tempdir:
        tempdir_path = Path(tempdir)
        env = os.environ.copy()
        postgres_shutdown_command: list[str] | None = None

        if args.database_url:
            database_url = args.database_url
        elif args.database_backend == "postgres":
            database_url, postgres_shutdown_command = start_temp_postgres(tempdir_path, env)
        else:
            database_url = f"sqlite:///{tempdir_path / 'unisuper_smoke.db'}"

        env["DATABASE_URL"] = database_url

        try:
            migration = run_command(["alembic", "upgrade", "head"], env=env)
            table_names = assert_expected_tables(database_url)
            reporting_period_id = ensure_reporting_period(database_url)

            port = args.port or choose_port()
            base_url = f"http://127.0.0.1:{port}"
            server = subprocess.Popen(
                ["uvicorn", "app.api.app:app", "--host", "127.0.0.1", "--port", str(port)],
                cwd=REPO_ROOT,
                env=env,
                stdout=subprocess.PIPE,
                stderr=subprocess.STDOUT,
                text=True,
            )
            try:
                wait_for_server(base_url, server)

                ingest_payload = {
                    "file_path": str(FIXTURE_PATH),
                    "fund_code": "unisuper",
                    "fund_name": "UniSuper",
                    "reporting_period_id": reporting_period_id,
                }
                ingest_response = request_json("POST", f"{base_url}/admin/ingest/local-file/unisuper", ingest_payload)
                if ingest_response["rows_inserted"] != 25404:
                    raise RuntimeError(f"Expected 25,404 inserted rows, got {ingest_response}")
                if ingest_response["schema_fingerprint"] != EXPECTED_FINGERPRINT:
                    raise RuntimeError(f"Unexpected schema fingerprint: {ingest_response}")
                if ingest_response["warnings"] != ["Decoded UniSuper source using cp1252 fallback after UTF-8 decode failed"]:
                    raise RuntimeError(f"Unexpected UniSuper adapter warnings: {ingest_response}")

                source_file_id = int(ingest_response["source_file_id"])
                source_files_payload = request_json("GET", f"{base_url}/admin/source-files")
                if len(source_files_payload) != 1:
                    raise RuntimeError(f"Expected exactly one source file, got {source_files_payload}")
                if source_files_payload[0]["rows_loaded"] != 25404:
                    raise RuntimeError(f"Expected 25,404 loaded rows, got {source_files_payload}")
                if source_files_payload[0]["mapping_version_id"] != EXPECTED_MAPPING_VERSION_ID:
                    raise RuntimeError(f"Unexpected mapping version in source-file list: {source_files_payload}")

                source_file_detail = request_json("GET", f"{base_url}/admin/source-files/{source_file_id}?page=1&size=200")
                if source_file_detail["total_rows"] != 25404:
                    raise RuntimeError(f"Admin source-file detail returned unexpected row count: {source_file_detail}")
                if source_file_detail["disclosure_counts"].get("aggregate_total") != 256:
                    raise RuntimeError(f"Admin source-file detail returned unexpected aggregate count: {source_file_detail}")
                if source_file_detail["holdings"][0]["source_option_name"] != "Conservative":
                    raise RuntimeError(f"Admin source-file detail returned unexpected first option: {source_file_detail}")

                last_page = source_file_detail["total_pages"]
                admin_ui_html = request_text(f"{base_url}/admin/ui/source-files/{source_file_id}?page={last_page}&size=200")
                if "UNISUPER_GLOBAL_COMPANIES_IN_ASIA" not in admin_ui_html:
                    raise RuntimeError("Admin UI detail page did not render the expected final UniSuper option")

                entity_query = urlencode({"name": "IFM INVESTORS PTY LIMITED"})
                entity_detail = request_json("GET", f"{base_url}/entities/by-name?{entity_query}")
                if entity_detail["observation_count"] != 9:
                    raise RuntimeError(f"Entity read model returned unexpected observation count: {entity_detail}")
                if entity_detail["disclosure_completeness_counts"] != {"ownership_only": 4, "value_only": 5}:
                    raise RuntimeError(f"Entity read model returned unexpected disclosure counts: {entity_detail}")

                db_summary = load_db_summary(database_url)
                print(
                    json.dumps(
                        {
                            "database_backend": args.database_backend if not args.database_url else "explicit_url",
                            "database_url": database_url,
                            "db_summary": db_summary,
                            "entity_detail_summary": {
                                "disclosure_completeness_counts": entity_detail["disclosure_completeness_counts"],
                                "latest_reporting_period": entity_detail["latest_reporting_period"],
                                "lookup_name": entity_detail["lookup_name"],
                                "observation_count": entity_detail["observation_count"],
                            },
                            "migration_stdout": migration.stdout.strip(),
                            "source_file_count": len(source_files_payload),
                            "source_file_id": source_file_id,
                            "tables_present": table_names,
                            "total_rows_loaded": source_files_payload[0]["rows_loaded"],
                        },
                        indent=2,
                        sort_keys=True,
                    )
                )
                return 0
            finally:
                server.terminate()
                try:
                    server.wait(timeout=10)
                except subprocess.TimeoutExpired:
                    server.kill()
                    server.wait(timeout=10)
        finally:
            if postgres_shutdown_command is not None:
                run_command(postgres_shutdown_command, env=env)


if __name__ == "__main__":
    raise SystemExit(main())
