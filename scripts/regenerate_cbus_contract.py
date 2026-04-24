from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
import sys

from adapters.base import AdapterParseResult, SourceFileMetadata
from adapters.cbus import CbusPhdAdapter


CONTRACT_CASES = (
    (
        Path("tests/fixtures/real/cbus/super-property__1_.csv"),
        Path("tests/adapters/contracts/cbus/property_canonical_output.json"),
        "contract-fixture-cbus-property",
        "contract-fixture-cbus-property-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/cbus/super-overseas-shares.csv"),
        Path("tests/adapters/contracts/cbus/overseas_shares_canonical_output.json"),
        "contract-fixture-cbus-overseas-shares",
        "contract-fixture-cbus-overseas-shares-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/cbus/super-australian-shares__1_.csv"),
        Path("tests/adapters/contracts/cbus/australian_shares_canonical_output.json"),
        "contract-fixture-cbus-australian-shares",
        "contract-fixture-cbus-australian-shares-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/cbus/super-cash.csv"),
        Path("tests/adapters/contracts/cbus/cash_canonical_output.json"),
        "contract-fixture-cbus-cash",
        "contract-fixture-cbus-cash-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/cbus/super-growth__1_.csv"),
        Path("tests/adapters/contracts/cbus/growth_canonical_output.json"),
        "contract-fixture-cbus-growth",
        "contract-fixture-cbus-growth-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/cbus/super-conservative.csv"),
        Path("tests/adapters/contracts/cbus/conservative_canonical_output.json"),
        "contract-fixture-cbus-conservative",
        "contract-fixture-cbus-conservative-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/cbus/super-growth-plus.csv"),
        Path("tests/adapters/contracts/cbus/growth_plus_canonical_output.json"),
        "contract-fixture-cbus-growth-plus",
        "contract-fixture-cbus-growth-plus-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/cbus/super-conservative-growth.csv"),
        Path("tests/adapters/contracts/cbus/conservative_growth_canonical_output.json"),
        "contract-fixture-cbus-conservative-growth",
        "contract-fixture-cbus-conservative-growth-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/cbus/super-diversified-fixed-interest.csv"),
        Path("tests/adapters/contracts/cbus/diversified_fixed_interest_canonical_output.json"),
        "contract-fixture-cbus-diversified-fixed-interest",
        "contract-fixture-cbus-diversified-fixed-interest-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/cbus/super-indexed-diversified.csv"),
        Path("tests/adapters/contracts/cbus/indexed_diversified_canonical_output.json"),
        "contract-fixture-cbus-indexed-diversified",
        "contract-fixture-cbus-indexed-diversified-sha256-placeholder",
    ),
)
WARNING_TEXT = (
    "THIS REWRITES THE CBUS CONTRACTS. COMMIT THE CHANGE WITH AN EXPLICIT MESSAGE EXPLAINING WHY."
)


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Regenerate the frozen Cbus adapter contract artifacts.")
    parser.add_argument("--confirm", action="store_true", help="Actually rewrite the committed contract files.")
    return parser


def make_contract_metadata(
    *,
    fixture_path: Path,
    source_file_id: str,
    checksum: str,
) -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id=source_file_id,
        fund_id="cbus",
        suspected_adapter_key="CbusPhdAdapter",
        reporting_period_id=None,
        source_url=str(fixture_path),
        checksum=checksum,
        received_at=datetime(2026, 4, 24, 0, 0, 0),
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


def render_contract(
    *,
    fixture_path: Path,
    source_file_id: str,
    checksum: str,
) -> str:
    raw_bytes = fixture_path.read_bytes()
    result = CbusPhdAdapter().parse(
        make_contract_metadata(
            fixture_path=fixture_path,
            source_file_id=source_file_id,
            checksum=checksum,
        ),
        raw_bytes,
    )
    return json.dumps(serialise_parse_result(result), indent=2, ensure_ascii=False, sort_keys=True) + "\n"


def main() -> int:
    args = build_parser().parse_args()
    print(WARNING_TEXT)
    if not args.confirm:
        print("Run again with --confirm to rewrite the contract files.")
        return 1

    for fixture_path, contract_path, source_file_id, checksum in CONTRACT_CASES:
        rendered = render_contract(fixture_path=fixture_path, source_file_id=source_file_id, checksum=checksum)
        contract_path.write_text(rendered, encoding="utf-8")
        print(f"Wrote {contract_path}")
    return 0


if __name__ == "__main__":
    sys.exit(main())
