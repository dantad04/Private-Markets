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
FIXTURE_PATH = (REPO_ROOT / "tests/fixtures/hesta_synthetic_high_growth_contract.csv").resolve()
EXPECTED_TOTAL_ROWS = int(
    json.loads((REPO_ROOT / "tests/fixtures/hesta_expected_outputs.json").read_text(encoding="utf-8"))["summary"][
        "total_rows_emitted"
    ]
)


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Run the Stage 1 Hesta smoke path against a fresh database.")
    parser.add_argument(
        "--database-backend",
        choices=("sqlite", "postgres"),
        default="sqlite",
        help="Database backend to use when --database-url is not supplied.",
    )
    parser.add_argument("--database-url", help="Optional SQLAlchemy database URL. Defaults to a temporary SQLite file.")
    parser.add_argument("--port", type=int, help="Optional fixed localhost port for uvicorn.")
    parser.add_argument(
        "--fixture-path",
        default=str(FIXTURE_PATH),
        help="Path to the Hesta fixture to ingest.",
    )
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
    with urlopen(request, timeout=10) as response:
        return json.loads(response.read().decode("utf-8"))


def request_text(url: str) -> str:
    with urlopen(url, timeout=10) as response:
        return response.read().decode("utf-8")


def wait_for_server(base_url: str, process: subprocess.Popen[str]) -> None:
    deadline = time.time() + 20
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
        ["psql", "-h", "127.0.0.1", "-p", str(port), "-U", "postgres", "-d", "postgres", "-c", "CREATE DATABASE stage1_smoke"],
        env=env,
    )
    return (
        f"postgresql+psycopg://postgres@127.0.0.1:{port}/stage1_smoke",
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
    fixture_path = Path(args.fixture_path).resolve()
    require_executable("alembic")
    require_executable("uvicorn")

    with tempfile.TemporaryDirectory(prefix="stage1-hesta-smoke-") as tempdir:
        tempdir_path = Path(tempdir)
        env = os.environ.copy()
        postgres_shutdown_command: list[str] | None = None

        if args.database_url:
            database_url = args.database_url
        elif args.database_backend == "postgres":
            database_url, postgres_shutdown_command = start_temp_postgres(tempdir_path, env)
        else:
            database_url = f"sqlite:///{tempdir_path / 'stage1_smoke.db'}"

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

                ingest_payload = {
                    "file_path": str(fixture_path),
                    "fund_code": "hesta",
                    "fund_name": "HESTA",
                }
                ingest_response = request_json("POST", f"{base_url}/admin/ingest/local-file", ingest_payload)
                if ingest_response["rows_inserted"] != EXPECTED_TOTAL_ROWS:
                    raise RuntimeError(f"Expected {EXPECTED_TOTAL_ROWS} inserted rows, got {ingest_response}")

                source_file_id = ingest_response["source_file_id"]
                admin_ui_html = request_text(f"{base_url}/admin/ui/source-files/{source_file_id}")
                if "Generate Capital PBC" not in admin_ui_html:
                    raise RuntimeError("Admin UI detail page did not render the expected Hesta holding")

                source_files_payload = request_json("GET", f"{base_url}/admin/source-files")
                if len(source_files_payload) != 1:
                    raise RuntimeError(f"Expected exactly one source file in admin API listing, got {source_files_payload}")

                source_file_detail = request_json("GET", f"{base_url}/admin/source-files/{source_file_id}")
                if source_file_detail["total_rows"] != EXPECTED_TOTAL_ROWS:
                    raise RuntimeError(f"Admin source-file detail returned unexpected row count: {source_file_detail}")

                entity_query = urlencode({"name": "Generate Capital PBC"})
                entity_detail = request_json("GET", f"{base_url}/entities/by-name?{entity_query}")
                if entity_detail["observation_count"] != 1:
                    raise RuntimeError(f"Entity read model returned unexpected observation count: {entity_detail}")
                if entity_detail["observations"][0]["ownership_pct"] != "0.0138":
                    raise RuntimeError(f"Entity read model returned unexpected ownership value: {entity_detail}")

                print(
                    json.dumps(
                        {
                            "database_backend": args.database_backend if not args.database_url else "explicit_url",
                            "database_url": database_url,
                            "migration_stdout": migration.stdout.strip(),
                            "tables_present": table_names,
                            "ingest_response": ingest_response,
                            "admin_source_files": source_files_payload,
                            "entity_detail": entity_detail,
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
