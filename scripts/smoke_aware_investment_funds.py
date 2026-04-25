from __future__ import annotations

from argparse import ArgumentParser
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

from sqlalchemy import create_engine, inspect


REPO_ROOT = Path(__file__).resolve().parents[1]
FIXTURE_DIR = (REPO_ROOT / "tests/fixtures/real/aware").resolve()
EXPECTED_MAPPING_VERSION_ID = "aware-stage2-investment-funds-2025-12-31-v1"
EXPECTED_FINGERPRINT = "5f32c5b412bf04749982c45080dfec21e9e2e46911971d1a9d6e1f2277cb1e0a"
LATEST_PERIOD_BATCH_CASES = (
    ("IFA-Australian-Equities.csv", "Australian Equities", "SS8K", 329),
    ("IFA-Balanced.csv", "Balanced", "SS6K", 1968),
    ("IFA-Capital-Stable.csv", "Capital Stable", "SS5K", 1966),
    ("IFA-Cash.csv", "Cash", "SS3K", 25),
    ("IFA-Growth.csv", "Growth", "SS9K", 1965),
    ("IFA-International-Equities.csv", "International Equities", "SRCK", 1344),
    ("IFA-Moderate.csv", "Moderate", "SS7K", 1969),
    ("IFB-Australian-Equities.csv", "Australian Equities", "SR5K", 329),
    ("IFB-Balanced.csv", "Balanced", "SR2K", 1968),
    ("IFB-Capital-Stable.csv", "Capital Stable", "SRYK", 1966),
    ("IFB-Cash.csv", "Cash", "SRSK", 25),
    ("IFB-Growth.csv", "Growth", "SR6K", 1965),
    ("IFB-International-Equities.csv", "International Equities", "SR7K", 1344),
    ("IFB-Moderate.csv", "Moderate", "SR4K", 1969),
)


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Run the Aware 2025-12-31 Investment Funds smoke path against a fresh database.")
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
    with urlopen(request, timeout=20) as response:
        return json.loads(response.read().decode("utf-8"))


def request_text(url: str) -> str:
    with urlopen(url, timeout=20) as response:
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
            "CREATE DATABASE aware_smoke",
        ],
        env=env,
    )
    return (
        f"postgresql+psycopg://postgres@127.0.0.1:{port}/aware_smoke",
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


def main() -> int:
    args = build_parser().parse_args()
    require_executable("alembic")
    require_executable("uvicorn")

    with tempfile.TemporaryDirectory(prefix="aware-investment-funds-smoke-") as tempdir:
        tempdir_path = Path(tempdir)
        env = os.environ.copy()
        postgres_shutdown_command: list[str] | None = None

        if args.database_url:
            database_url = args.database_url
        elif args.database_backend == "postgres":
            database_url, postgres_shutdown_command = start_temp_postgres(tempdir_path, env)
        else:
            database_url = f"sqlite:///{tempdir_path / 'aware_smoke.db'}"

        env["DATABASE_URL"] = database_url

        try:
            migration = run_command(["alembic", "upgrade", "head"], env=env)
            table_names = assert_expected_tables(database_url)

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

                source_file_ids: list[int] = []
                for filename, _option_name, _option_code, expected_rows in LATEST_PERIOD_BATCH_CASES:
                    fixture_path = FIXTURE_DIR / filename
                    ingest_payload = {
                        "file_path": str(fixture_path),
                        "fund_code": "aware",
                        "fund_name": "Aware Super",
                    }
                    ingest_response = request_json("POST", f"{base_url}/admin/ingest/local-file/aware", ingest_payload)
                    if ingest_response["rows_inserted"] != expected_rows:
                        raise RuntimeError(f"Unexpected ingest response for {filename}: {ingest_response}")
                    if ingest_response["schema_fingerprint"] != EXPECTED_FINGERPRINT:
                        raise RuntimeError(f"Unexpected schema fingerprint for {filename}: {ingest_response}")
                    source_file_ids.append(int(ingest_response["source_file_id"]))

                source_files_payload = request_json("GET", f"{base_url}/admin/source-files")
                if len(source_files_payload) != len(LATEST_PERIOD_BATCH_CASES):
                    raise RuntimeError(f"Expected 14 source files, got {source_files_payload}")
                if sum(row["rows_loaded"] for row in source_files_payload) != 19132:
                    raise RuntimeError(f"Expected 19,132 loaded rows, got {source_files_payload}")
                if {row["mapping_version_id"] for row in source_files_payload} != {EXPECTED_MAPPING_VERSION_ID}:
                    raise RuntimeError(f"Unexpected mapping version in source-file list: {source_files_payload}")

                source_file_detail = request_json("GET", f"{base_url}/admin/source-files/{source_file_ids[-1]}")
                if source_file_detail["total_rows"] != 1969:
                    raise RuntimeError(f"Admin source-file detail returned unexpected row count: {source_file_detail}")
                if source_file_detail["source_file"]["investment_option_name"] != "Moderate":
                    raise RuntimeError(f"Admin source-file detail returned unexpected option: {source_file_detail}")
                if "aggregate_total" not in source_file_detail["disclosure_counts"]:
                    raise RuntimeError(f"Admin source-file detail did not expose aggregate totals: {source_file_detail}")

                admin_ui_html = request_text(f"{base_url}/admin/ui/source-files/{source_file_ids[-1]}")
                if "Aware Super" not in admin_ui_html or "Moderate" not in admin_ui_html:
                    raise RuntimeError("Admin UI detail page did not render the expected Aware source-file detail")

                entity_query = urlencode({"name": "STATE STREET BANK AND TRUST"})
                entity_detail = request_json("GET", f"{base_url}/entities/by-name?{entity_query}")
                if entity_detail["observation_count"] != 168:
                    raise RuntimeError(f"Entity read model returned unexpected observation count: {entity_detail}")
                if entity_detail["disclosure_completeness_counts"] != {"value_only": 168}:
                    raise RuntimeError(f"Entity read model returned unexpected disclosure counts: {entity_detail}")
                entity_detail_summary = {
                    "canonical_asset_class_counts": entity_detail["canonical_asset_class_counts"],
                    "disclosure_completeness_counts": entity_detail["disclosure_completeness_counts"],
                    "latest_reporting_period": entity_detail["latest_reporting_period"],
                    "lookup_name": entity_detail["lookup_name"],
                    "observation_count": entity_detail["observation_count"],
                }

                print(
                    json.dumps(
                        {
                            "database_backend": args.database_backend if not args.database_url else "explicit_url",
                            "database_url": database_url,
                            "migration_stdout": migration.stdout.strip(),
                            "tables_present": table_names,
                            "source_file_count": len(source_files_payload),
                            "source_file_ids": source_file_ids,
                            "total_rows_loaded": sum(row["rows_loaded"] for row in source_files_payload),
                            "entity_detail_summary": entity_detail_summary,
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
