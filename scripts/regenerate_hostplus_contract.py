from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
import sys

from adapters.base import AdapterParseResult, SourceFileMetadata
from adapters.hostplus import HostPlusPhdStateMachineAdapter


FIXTURE_PATH = Path("tests/fixtures/hostplus_real_extract.csv")
OUTPUT_PATH = Path("tests/adapters/contracts/hostplus/canonical_output.json")
HOSTPLUS_FIXTURE_DIR = Path("tests/fixtures/real/hostplus")
CONTRACT_CASES = (
    (FIXTURE_PATH, OUTPUT_PATH, "contract-fixture-hostplus", "contract-fixture-hostplus-sha256-placeholder"),
    (
        HOSTPLUS_FIXTURE_DIR / "australian-shares.csv",
        Path("tests/adapters/contracts/hostplus/australian_shares_canonical_output.json"),
        "contract-fixture-hostplus-australian-shares",
        "contract-fixture-hostplus-australian-shares-sha256-placeholder",
    ),
    (
        HOSTPLUS_FIXTURE_DIR / "australian-shares-indexed.csv",
        Path("tests/adapters/contracts/hostplus/australian_shares_indexed_canonical_output.json"),
        "contract-fixture-hostplus-australian-shares-indexed",
        "contract-fixture-hostplus-australian-shares-indexed-sha256-placeholder",
    ),
    (
        HOSTPLUS_FIXTURE_DIR / "cash.csv",
        Path("tests/adapters/contracts/hostplus/cash_canonical_output.json"),
        "contract-fixture-hostplus-cash",
        "contract-fixture-hostplus-cash-sha256-placeholder",
    ),
    (
        HOSTPLUS_FIXTURE_DIR / "indexed-high-growth.csv",
        Path("tests/adapters/contracts/hostplus/indexed_high_growth_canonical_output.json"),
        "contract-fixture-hostplus-indexed-high-growth",
        "contract-fixture-hostplus-indexed-high-growth-sha256-placeholder",
    ),
    (
        HOSTPLUS_FIXTURE_DIR / "international-shares.csv",
        Path("tests/adapters/contracts/hostplus/international_shares_canonical_output.json"),
        "contract-fixture-hostplus-international-shares",
        "contract-fixture-hostplus-international-shares-sha256-placeholder",
    ),
    (
        HOSTPLUS_FIXTURE_DIR / "sri-high-growth.csv",
        Path("tests/adapters/contracts/hostplus/sri_high_growth_canonical_output.json"),
        "contract-fixture-hostplus-sri-high-growth",
        "contract-fixture-hostplus-sri-high-growth-sha256-placeholder",
    ),
    (
        HOSTPLUS_FIXTURE_DIR / "balanced.csv",
        Path("tests/adapters/contracts/hostplus/balanced_canonical_output.json"),
        "contract-fixture-hostplus-balanced",
        "contract-fixture-hostplus-balanced-sha256-placeholder",
    ),
    (
        HOSTPLUS_FIXTURE_DIR / "conservative.csv",
        Path("tests/adapters/contracts/hostplus/conservative_canonical_output.json"),
        "contract-fixture-hostplus-conservative",
        "contract-fixture-hostplus-conservative-sha256-placeholder",
    ),
    (
        HOSTPLUS_FIXTURE_DIR / "defensive.csv",
        Path("tests/adapters/contracts/hostplus/defensive_canonical_output.json"),
        "contract-fixture-hostplus-defensive",
        "contract-fixture-hostplus-defensive-sha256-placeholder",
    ),
    (
        HOSTPLUS_FIXTURE_DIR / "growth.csv",
        Path("tests/adapters/contracts/hostplus/growth_canonical_output.json"),
        "contract-fixture-hostplus-growth",
        "contract-fixture-hostplus-growth-sha256-placeholder",
    ),
    (
        HOSTPLUS_FIXTURE_DIR / "stable.csv",
        Path("tests/adapters/contracts/hostplus/stable_canonical_output.json"),
        "contract-fixture-hostplus-stable",
        "contract-fixture-hostplus-stable-sha256-placeholder",
    ),
    (
        HOSTPLUS_FIXTURE_DIR / "sri-balanced.csv",
        Path("tests/adapters/contracts/hostplus/sri_balanced_canonical_output.json"),
        "contract-fixture-hostplus-sri-balanced",
        "contract-fixture-hostplus-sri-balanced-sha256-placeholder",
    ),
    (
        HOSTPLUS_FIXTURE_DIR / "sri-defensive.csv",
        Path("tests/adapters/contracts/hostplus/sri_defensive_canonical_output.json"),
        "contract-fixture-hostplus-sri-defensive",
        "contract-fixture-hostplus-sri-defensive-sha256-placeholder",
    ),
)
WARNING_TEXT = "THIS REWRITES THE STAGE 2 HOST-PLUS CONTRACT. COMMIT THE CHANGE WITH AN EXPLICIT MESSAGE EXPLAINING WHY."


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Regenerate the frozen Host-Plus adapter contract artifact.")
    parser.add_argument("--confirm", action="store_true", help="Actually rewrite canonical_output.json. Required.")
    return parser


def make_contract_metadata(*, fixture_path: Path, source_file_id: str, checksum: str) -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id=source_file_id,
        fund_id="hostplus",
        suspected_adapter_key="HostPlusPhdStateMachineAdapter",
        reporting_period_id=1,
        source_url=str(fixture_path),
        checksum=checksum,
        received_at=datetime(2026, 1, 1, 0, 0, 0),
        reporting_period_end_date=date(2025, 12, 31),
    )


def _canonical_decimal_string(value: Decimal) -> str:
    if value == 0:
        return "0"
    rendered = format(value.normalize(), "f")
    if "." in rendered:
        rendered = rendered.rstrip("0").rstrip(".")
    return rendered or "0"


def _serialise_scalar(value):
    if isinstance(value, Decimal):
        return _canonical_decimal_string(value)
    if isinstance(value, (datetime, date)):
        return value.isoformat()
    return value


def _serialise_ordered_dataclass(instance) -> dict[str, object]:
    data: dict[str, object] = {}
    for field in fields(instance):
        data[field.name] = _serialise_value(getattr(instance, field.name))
    return data


def _serialise_mapping(value: dict[object, object]) -> dict[str, object]:
    serialised: dict[str, object] = {}
    for key in sorted(value.keys(), key=lambda item: str(item)):
        serialised[str(key)] = _serialise_value(value[key])
    return serialised


def _serialise_value(value):
    if is_dataclass(value):
        return _serialise_ordered_dataclass(value)
    if isinstance(value, dict):
        return _serialise_mapping(value)
    if isinstance(value, list):
        return [_serialise_value(item) for item in value]
    return _serialise_scalar(value)


def serialise_parse_result(result: AdapterParseResult) -> dict[str, object]:
    return {
        "holdings": [_serialise_ordered_dataclass(record) for record in result.holdings],
        "structural_metadata": _serialise_mapping(result.structural_metadata),
        "parse_statistics": _serialise_mapping(result.parse_statistics),
        "schema_fingerprint": result.schema_fingerprint,
        "adapter_warnings": list(result.adapter_warnings),
    }


def main() -> int:
    args = build_parser().parse_args()
    print(WARNING_TEXT)
    if not args.confirm:
        print("Refusing to rewrite without --confirm.", file=sys.stderr)
        return 1

    adapter = HostPlusPhdStateMachineAdapter()
    for fixture_path, output_path, source_file_id, checksum in CONTRACT_CASES:
        result = adapter.parse(
            make_contract_metadata(
                fixture_path=fixture_path,
                source_file_id=source_file_id,
                checksum=checksum,
            ),
            fixture_path.read_bytes(),
        )
        payload = serialise_parse_result(result)
        output_path.parent.mkdir(parents=True, exist_ok=True)
        output_path.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
        print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
