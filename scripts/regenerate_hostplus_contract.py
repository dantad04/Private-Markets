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
WARNING_TEXT = "THIS REWRITES THE STAGE 2 HOST-PLUS CONTRACT. COMMIT THE CHANGE WITH AN EXPLICIT MESSAGE EXPLAINING WHY."


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Regenerate the frozen Host-Plus adapter contract artifact.")
    parser.add_argument("--confirm", action="store_true", help="Actually rewrite canonical_output.json. Required.")
    return parser


def make_contract_metadata() -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id="contract-fixture-hostplus",
        fund_id="hostplus",
        suspected_adapter_key="HostPlusPhdStateMachineAdapter",
        reporting_period_id=1,
        source_url=str(FIXTURE_PATH),
        checksum="contract-fixture-hostplus-sha256-placeholder",
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

    result = HostPlusPhdStateMachineAdapter().parse(make_contract_metadata(), FIXTURE_PATH.read_bytes())
    payload = serialise_parse_result(result)
    OUTPUT_PATH.parent.mkdir(parents=True, exist_ok=True)
    OUTPUT_PATH.write_text(json.dumps(payload, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")
    print(f"Wrote {OUTPUT_PATH}")
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
