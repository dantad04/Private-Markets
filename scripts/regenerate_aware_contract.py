from __future__ import annotations

from argparse import ArgumentParser
from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
import json
from pathlib import Path
import sys

from adapters.aware import AwarePhdAdapter
from adapters.base import AdapterParseResult, SourceFileMetadata


CONTRACT_CASES = (
    (
        Path("tests/fixtures/aware_synthetic_table1_minimal.csv"),
        Path("tests/adapters/contracts/aware/canonical_output.json"),
        "contract-fixture-aware",
        "contract-fixture-aware-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/aware/IFA-Australian-Equities.csv"),
        Path("tests/adapters/contracts/aware/ifa_australian_equities_canonical_output.json"),
        "contract-fixture-aware-ifa-australian-equities",
        "contract-fixture-aware-ifa-australian-equities-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/aware/IFA-Balanced.csv"),
        Path("tests/adapters/contracts/aware/ifa_balanced_canonical_output.json"),
        "contract-fixture-aware-ifa-balanced",
        "contract-fixture-aware-ifa-balanced-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/aware/IFA-Capital-Stable.csv"),
        Path("tests/adapters/contracts/aware/ifa_capital_stable_canonical_output.json"),
        "contract-fixture-aware-ifa-capital-stable",
        "contract-fixture-aware-ifa-capital-stable-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/aware/IFA-Cash.csv"),
        Path("tests/adapters/contracts/aware/ifa_cash_canonical_output.json"),
        "contract-fixture-aware-ifa-cash",
        "contract-fixture-aware-ifa-cash-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/aware/IFA-Growth.csv"),
        Path("tests/adapters/contracts/aware/ifa_growth_canonical_output.json"),
        "contract-fixture-aware-ifa-growth",
        "contract-fixture-aware-ifa-growth-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/aware/IFA-International-Equities.csv"),
        Path("tests/adapters/contracts/aware/ifa_international_equities_canonical_output.json"),
        "contract-fixture-aware-ifa-international-equities",
        "contract-fixture-aware-ifa-international-equities-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/aware/IFA-Moderate.csv"),
        Path("tests/adapters/contracts/aware/ifa_moderate_canonical_output.json"),
        "contract-fixture-aware-ifa-moderate",
        "contract-fixture-aware-ifa-moderate-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/aware/IFB-Australian-Equities.csv"),
        Path("tests/adapters/contracts/aware/ifb_australian_equities_canonical_output.json"),
        "contract-fixture-aware-ifb-australian-equities",
        "contract-fixture-aware-ifb-australian-equities-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/aware/IFB-Balanced.csv"),
        Path("tests/adapters/contracts/aware/ifb_balanced_canonical_output.json"),
        "contract-fixture-aware-ifb-balanced",
        "contract-fixture-aware-ifb-balanced-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/aware/IFB-Capital-Stable.csv"),
        Path("tests/adapters/contracts/aware/ifb_capital_stable_canonical_output.json"),
        "contract-fixture-aware-ifb-capital-stable",
        "contract-fixture-aware-ifb-capital-stable-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/aware/IFB-Cash.csv"),
        Path("tests/adapters/contracts/aware/ifb_cash_canonical_output.json"),
        "contract-fixture-aware-ifb-cash",
        "contract-fixture-aware-ifb-cash-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/aware/IFB-Growth.csv"),
        Path("tests/adapters/contracts/aware/ifb_growth_canonical_output.json"),
        "contract-fixture-aware-ifb-growth",
        "contract-fixture-aware-ifb-growth-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/aware/IFB-International-Equities.csv"),
        Path("tests/adapters/contracts/aware/ifb_international_equities_canonical_output.json"),
        "contract-fixture-aware-ifb-international-equities",
        "contract-fixture-aware-ifb-international-equities-sha256-placeholder",
    ),
    (
        Path("tests/fixtures/real/aware/IFB-Moderate.csv"),
        Path("tests/adapters/contracts/aware/ifb_moderate_canonical_output.json"),
        "contract-fixture-aware-ifb-moderate",
        "contract-fixture-aware-ifb-moderate-sha256-placeholder",
    ),
)
WARNING_TEXT = "THIS REWRITES THE STAGE 2 AWARE CONTRACTS. COMMIT THE CHANGE WITH AN EXPLICIT MESSAGE EXPLAINING WHY."


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Regenerate the frozen Aware adapter contract artifact.")
    parser.add_argument(
        "--confirm",
        action="store_true",
        help="Actually rewrite canonical_output.json. Required.",
    )
    return parser


def make_contract_metadata(*, fixture_path: Path, source_file_id: str, checksum: str) -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id=source_file_id,
        fund_id="aware",
        suspected_adapter_key="AwarePhdAdapter",
        reporting_period_id=None,
        source_url=str(fixture_path),
        checksum=checksum,
        received_at=datetime(2026, 1, 1, 0, 0, 0),
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

    adapter = AwarePhdAdapter()
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
        output_path.write_text(
            json.dumps(payload, indent=2, ensure_ascii=False) + "\n",
            encoding="utf-8",
        )
        print(f"Wrote {output_path}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
