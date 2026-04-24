from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
import difflib
import json
from pathlib import Path
import unittest

from adapters.base import AdapterParseResult, SourceFileMetadata
from adapters.cbus import CbusPhdAdapter


CONTRACT_CASES = (
    (
        "high_growth",
        Path("tests/fixtures/real/cbus/super-high-growth__1_.csv"),
        Path("tests/adapters/contracts/cbus/canonical_output.json"),
        "contract-fixture-cbus",
        "contract-fixture-cbus-sha256-placeholder",
    ),
    (
        "property",
        Path("tests/fixtures/real/cbus/super-property__1_.csv"),
        Path("tests/adapters/contracts/cbus/property_canonical_output.json"),
        "contract-fixture-cbus-property",
        "contract-fixture-cbus-property-sha256-placeholder",
    ),
    (
        "overseas_shares",
        Path("tests/fixtures/real/cbus/super-overseas-shares.csv"),
        Path("tests/adapters/contracts/cbus/overseas_shares_canonical_output.json"),
        "contract-fixture-cbus-overseas-shares",
        "contract-fixture-cbus-overseas-shares-sha256-placeholder",
    ),
    (
        "australian_shares",
        Path("tests/fixtures/real/cbus/super-australian-shares__1_.csv"),
        Path("tests/adapters/contracts/cbus/australian_shares_canonical_output.json"),
        "contract-fixture-cbus-australian-shares",
        "contract-fixture-cbus-australian-shares-sha256-placeholder",
    ),
    (
        "cash",
        Path("tests/fixtures/real/cbus/super-cash.csv"),
        Path("tests/adapters/contracts/cbus/cash_canonical_output.json"),
        "contract-fixture-cbus-cash",
        "contract-fixture-cbus-cash-sha256-placeholder",
    ),
    (
        "growth",
        Path("tests/fixtures/real/cbus/super-growth__1_.csv"),
        Path("tests/adapters/contracts/cbus/growth_canonical_output.json"),
        "contract-fixture-cbus-growth",
        "contract-fixture-cbus-growth-sha256-placeholder",
    ),
    (
        "conservative",
        Path("tests/fixtures/real/cbus/super-conservative.csv"),
        Path("tests/adapters/contracts/cbus/conservative_canonical_output.json"),
        "contract-fixture-cbus-conservative",
        "contract-fixture-cbus-conservative-sha256-placeholder",
    ),
    (
        "growth_plus",
        Path("tests/fixtures/real/cbus/super-growth-plus.csv"),
        Path("tests/adapters/contracts/cbus/growth_plus_canonical_output.json"),
        "contract-fixture-cbus-growth-plus",
        "contract-fixture-cbus-growth-plus-sha256-placeholder",
    ),
    (
        "conservative_growth",
        Path("tests/fixtures/real/cbus/super-conservative-growth.csv"),
        Path("tests/adapters/contracts/cbus/conservative_growth_canonical_output.json"),
        "contract-fixture-cbus-conservative-growth",
        "contract-fixture-cbus-conservative-growth-sha256-placeholder",
    ),
    (
        "diversified_fixed_interest",
        Path("tests/fixtures/real/cbus/super-diversified-fixed-interest.csv"),
        Path("tests/adapters/contracts/cbus/diversified_fixed_interest_canonical_output.json"),
        "contract-fixture-cbus-diversified-fixed-interest",
        "contract-fixture-cbus-diversified-fixed-interest-sha256-placeholder",
    ),
    (
        "indexed_diversified",
        Path("tests/fixtures/real/cbus/super-indexed-diversified.csv"),
        Path("tests/adapters/contracts/cbus/indexed_diversified_canonical_output.json"),
        "contract-fixture-cbus-indexed-diversified",
        "contract-fixture-cbus-indexed-diversified-sha256-placeholder",
    ),
)


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


def load_committed_contract(contract_path: Path) -> dict[str, object]:
    return json.loads(contract_path.read_text(encoding="utf-8"))


class TestCbusFrozenContract(unittest.TestCase):
    maxDiff = None

    def test_cbus_fixtures_match_frozen_contracts(self) -> None:
        for label, fixture_path, contract_path, source_file_id, checksum in CONTRACT_CASES:
            with self.subTest(label=label):
                result = CbusPhdAdapter().parse(
                    make_contract_metadata(
                        fixture_path=fixture_path,
                        source_file_id=source_file_id,
                        checksum=checksum,
                    ),
                    fixture_path.read_bytes(),
                )
                actual = serialise_parse_result(result)
                expected = load_committed_contract(contract_path)

                if actual != expected:
                    self.fail(_build_contract_mismatch_message(expected, actual))


def _build_contract_mismatch_message(expected: dict[str, object], actual: dict[str, object]) -> str:
    mismatches: list[str] = []

    for key in ("schema_fingerprint", "adapter_warnings", "structural_metadata", "parse_statistics"):
        if expected.get(key) != actual.get(key):
            diff = "\n".join(
                difflib.unified_diff(
                    json.dumps(expected.get(key), indent=2, ensure_ascii=False, sort_keys=True).splitlines(),
                    json.dumps(actual.get(key), indent=2, ensure_ascii=False, sort_keys=True).splitlines(),
                    fromfile=f"expected.{key}",
                    tofile=f"actual.{key}",
                    lineterm="",
                )
            )
            mismatches.append(f"{key} mismatch:\n{diff}")

    expected_holdings = expected.get("holdings", [])
    actual_holdings = actual.get("holdings", [])
    if len(expected_holdings) != len(actual_holdings):
        mismatches.append(
            f"holdings length mismatch: expected {len(expected_holdings)} rows, got {len(actual_holdings)} rows"
        )

    compared = min(len(expected_holdings), len(actual_holdings))
    row_mismatches: list[str] = []
    for index in range(compared):
        if expected_holdings[index] == actual_holdings[index]:
            continue
        expected_row = expected_holdings[index]
        actual_row = actual_holdings[index]
        row_mismatches.append(
            "row index {index} (source_row_number expected={expected_row_number}, actual={actual_row_number})\n"
            "expected: {expected_json}\n"
            "actual:   {actual_json}".format(
                index=index,
                expected_row_number=expected_row.get("source_row_number"),
                actual_row_number=actual_row.get("source_row_number"),
                expected_json=json.dumps(expected_row, ensure_ascii=False, sort_keys=False),
                actual_json=json.dumps(actual_row, ensure_ascii=False, sort_keys=False),
            )
        )
        if len(row_mismatches) == 5:
            break
    if row_mismatches:
        mismatches.append("first row mismatches:\n" + "\n".join(row_mismatches))

    return "\n\n".join(mismatches)
