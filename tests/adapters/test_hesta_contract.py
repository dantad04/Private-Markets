from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
import difflib
import json
from pathlib import Path
import unittest

from adapters.base import AdapterParseResult, SourceFileMetadata, SourceNormalisedHoldingRecord
from adapters.hesta import HestaPhdAdapter
CONTRACT_CASES = (
    (
        "synthetic_high_growth",
        Path("tests/fixtures/hesta_synthetic_high_growth_contract.csv"),
        Path("tests/adapters/contracts/hesta/canonical_output.json"),
        "contract-fixture-hesta",
        "contract-fixture-sha256-placeholder",
    ),
    (
        "australian_shares",
        Path("tests/fixtures/real/hesta/Australian-Shares-super-assets.csv"),
        Path("tests/adapters/contracts/hesta/australian_shares_canonical_output.json"),
        "contract-fixture-hesta-australian-shares",
        "contract-fixture-hesta-australian-shares-sha256-placeholder",
    ),
    (
        "balanced_growth",
        Path("tests/fixtures/real/hesta/Balanced-Growth-super-assets.csv"),
        Path("tests/adapters/contracts/hesta/balanced_growth_canonical_output.json"),
        "contract-fixture-hesta-balanced-growth",
        "contract-fixture-hesta-balanced-growth-sha256-placeholder",
    ),
    (
        "conservative",
        Path("tests/fixtures/real/hesta/Conservative-super-assets.csv"),
        Path("tests/adapters/contracts/hesta/conservative_canonical_output.json"),
        "contract-fixture-hesta-conservative",
        "contract-fixture-hesta-conservative-sha256-placeholder",
    ),
    (
        "diversified_bonds",
        Path("tests/fixtures/real/hesta/Diversified-Bonds-super-assets.csv"),
        Path("tests/adapters/contracts/hesta/diversified_bonds_canonical_output.json"),
        "contract-fixture-hesta-diversified-bonds",
        "contract-fixture-hesta-diversified-bonds-sha256-placeholder",
    ),
    (
        "high_growth",
        Path("tests/fixtures/real/hesta/High-Growth-super-assets (1).csv"),
        Path("tests/adapters/contracts/hesta/high_growth_canonical_output.json"),
        "contract-fixture-hesta-high-growth",
        "contract-fixture-hesta-high-growth-sha256-placeholder",
    ),
    (
        "indexed_balanced_growth",
        Path("tests/fixtures/real/hesta/Indexed-Balanced-Growth-super-assets.csv"),
        Path("tests/adapters/contracts/hesta/indexed_balanced_growth_canonical_output.json"),
        "contract-fixture-hesta-indexed-balanced-growth",
        "contract-fixture-hesta-indexed-balanced-growth-sha256-placeholder",
    ),
    (
        "international_shares",
        Path("tests/fixtures/real/hesta/International-Shares-super-assets.csv"),
        Path("tests/adapters/contracts/hesta/international_shares_canonical_output.json"),
        "contract-fixture-hesta-international-shares",
        "contract-fixture-hesta-international-shares-sha256-placeholder",
    ),
    (
        "property_and_infrastructure",
        Path("tests/fixtures/real/hesta/Property-and-Infrastructure-super-assets.csv"),
        Path("tests/adapters/contracts/hesta/property_and_infrastructure_canonical_output.json"),
        "contract-fixture-hesta-property-and-infrastructure",
        "contract-fixture-hesta-property-and-infrastructure-sha256-placeholder",
    ),
    (
        "sustainable_growth",
        Path("tests/fixtures/real/hesta/Sustainable-Growth-super-assets.csv"),
        Path("tests/adapters/contracts/hesta/sustainable_growth_canonical_output.json"),
        "contract-fixture-hesta-sustainable-growth",
        "contract-fixture-hesta-sustainable-growth-sha256-placeholder",
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
        fund_id="hesta",
        suspected_adapter_key="HestaPhdAdapter",
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
        value = getattr(instance, field.name)
        data[field.name] = _serialise_value(value)
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


class TestHestaFrozenContract(unittest.TestCase):
    maxDiff = None

    def test_hesta_fixtures_match_frozen_contracts(self) -> None:
        adapter = HestaPhdAdapter()
        for label, fixture_path, contract_path, source_file_id, checksum in CONTRACT_CASES:
            with self.subTest(contract=label):
                result = adapter.parse(
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
                    self.fail(_build_contract_mismatch_message(label, expected, actual))


def _build_contract_mismatch_message(label: str, expected: dict[str, object], actual: dict[str, object]) -> str:
    mismatches: list[str] = []

    for key in ("schema_fingerprint", "adapter_warnings", "structural_metadata", "parse_statistics"):
        if expected.get(key) != actual.get(key):
            diff = "\n".join(
                difflib.unified_diff(
                    json.dumps(expected.get(key), indent=2, ensure_ascii=False, sort_keys=True).splitlines(),
                    json.dumps(actual.get(key), indent=2, ensure_ascii=False, sort_keys=True).splitlines(),
                    fromfile=f"expected.{label}.{key}",
                    tofile=f"actual.{label}.{key}",
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
        mismatches.append("first mismatched holdings:\n" + "\n\n".join(row_mismatches))

    return f"Frozen Hesta contract drift detected for {label}.\n\n" + "\n\n".join(mismatches)
