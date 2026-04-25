from __future__ import annotations

from dataclasses import dataclass
from datetime import date
import hashlib
import json
import os
from pathlib import Path
from typing import Any

from sqlalchemy.engine import make_url


REPO_ROOT = Path(__file__).resolve().parents[1]
DEFAULT_MANIFEST_PATH = REPO_ROOT / "config/demo_corpus_manifest.json"


class DemoCorpusError(RuntimeError):
    """Raised when the demo corpus manifest or runtime environment is invalid."""


@dataclass(frozen=True)
class ManifestSourceFile:
    path: Path
    expected_rows: int
    mapping_version_id: str | None


@dataclass(frozen=True)
class ManifestFund:
    fund_code: str
    fund_name: str
    adapter_key: str
    mapping_versions: tuple[str, ...]
    reporting_period: date
    expected_source_file_count: int
    expected_row_count: int
    row_count_tolerance: int
    source_files: tuple[ManifestSourceFile, ...]


@dataclass(frozen=True)
class DemoCorpusManifest:
    manifest_name: str
    manifest_version: int
    reporting_period: date
    row_count_tolerance: int
    funds: tuple[ManifestFund, ...]
    smoke_checks: dict[str, Any]


def load_manifest(path: Path = DEFAULT_MANIFEST_PATH) -> DemoCorpusManifest:
    manifest_path = path if path.is_absolute() else REPO_ROOT / path
    raw = json.loads(manifest_path.read_text(encoding="utf-8"))
    reporting_period = date.fromisoformat(str(raw["reporting_period"]))
    default_tolerance = int(raw.get("row_count_tolerance", 0))

    funds: list[ManifestFund] = []
    for fund_payload in raw["funds"]:
        fund_period = date.fromisoformat(str(fund_payload.get("reporting_period", raw["reporting_period"])))
        source_files = tuple(
            ManifestSourceFile(
                path=_resolve_repo_path(str(file_payload["path"])),
                expected_rows=int(file_payload["expected_rows"]),
                mapping_version_id=file_payload.get("mapping_version_id"),
            )
            for file_payload in fund_payload["source_files"]
        )
        fund = ManifestFund(
            fund_code=str(fund_payload["fund_code"]),
            fund_name=str(fund_payload["fund_name"]),
            adapter_key=str(fund_payload["adapter_key"]),
            mapping_versions=tuple(str(item) for item in fund_payload.get("mapping_versions", [])),
            reporting_period=fund_period,
            expected_source_file_count=int(fund_payload["expected_source_file_count"]),
            expected_row_count=int(fund_payload["expected_row_count"]),
            row_count_tolerance=int(fund_payload.get("row_count_tolerance", default_tolerance)),
            source_files=source_files,
        )
        _validate_fund(fund)
        funds.append(fund)

    return DemoCorpusManifest(
        manifest_name=str(raw["manifest_name"]),
        manifest_version=int(raw["manifest_version"]),
        reporting_period=reporting_period,
        row_count_tolerance=default_tolerance,
        funds=tuple(funds),
        smoke_checks=dict(raw.get("smoke_checks", {})),
    )


def require_postgres_database_url(database_url: str | None = None) -> str:
    resolved = database_url or os.getenv("DATABASE_URL")
    if not resolved:
        raise DemoCorpusError("DATABASE_URL must be set to a PostgreSQL database URL.")

    driver_name = make_url(resolved).drivername
    if driver_name.startswith("sqlite"):
        raise DemoCorpusError("Refusing to run demo corpus tooling against SQLite; use PostgreSQL.")
    if not (driver_name == "postgres" or driver_name.startswith("postgresql")):
        raise DemoCorpusError(f"Demo corpus tooling requires PostgreSQL, got driver {driver_name!r}.")
    return resolved


def sha256_file(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _resolve_repo_path(value: str) -> Path:
    path = Path(value)
    return path if path.is_absolute() else (REPO_ROOT / path).resolve()


def _validate_fund(fund: ManifestFund) -> None:
    if len(fund.source_files) != fund.expected_source_file_count:
        raise DemoCorpusError(
            f"{fund.fund_code} expected {fund.expected_source_file_count} source files but manifest lists "
            f"{len(fund.source_files)}"
        )
    row_total = sum(source_file.expected_rows for source_file in fund.source_files)
    if row_total != fund.expected_row_count:
        raise DemoCorpusError(
            f"{fund.fund_code} expected row count {fund.expected_row_count} does not match file total {row_total}"
        )
    missing_files = [str(source_file.path) for source_file in fund.source_files if not source_file.path.exists()]
    if missing_files:
        raise DemoCorpusError(f"{fund.fund_code} manifest references missing source files: {missing_files}")
