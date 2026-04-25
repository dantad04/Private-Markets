from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
import difflib
import json
from pathlib import Path
import unittest

from adapters.aware import AwarePhdAdapter
from adapters.base import AdapterParseResult, SourceFileMetadata


CONTRACT_CASES = (
    (
        "synthetic",
        Path("tests/fixtures/aware_synthetic_table1_minimal.csv"),
        Path("tests/adapters/contracts/aware/canonical_output.json"),
        "contract-fixture-aware",
        "contract-fixture-aware-sha256-placeholder",
    ),
    (
        "ifa_australian_equities",
        Path("tests/fixtures/real/aware/IFA-Australian-Equities.csv"),
        Path("tests/adapters/contracts/aware/ifa_australian_equities_canonical_output.json"),
        "contract-fixture-aware-ifa-australian-equities",
        "contract-fixture-aware-ifa-australian-equities-sha256-placeholder",
    ),
    (
        "ifa_balanced",
        Path("tests/fixtures/real/aware/IFA-Balanced.csv"),
        Path("tests/adapters/contracts/aware/ifa_balanced_canonical_output.json"),
        "contract-fixture-aware-ifa-balanced",
        "contract-fixture-aware-ifa-balanced-sha256-placeholder",
    ),
    (
        "ifa_capital_stable",
        Path("tests/fixtures/real/aware/IFA-Capital-Stable.csv"),
        Path("tests/adapters/contracts/aware/ifa_capital_stable_canonical_output.json"),
        "contract-fixture-aware-ifa-capital-stable",
        "contract-fixture-aware-ifa-capital-stable-sha256-placeholder",
    ),
    (
        "ifa_cash",
        Path("tests/fixtures/real/aware/IFA-Cash.csv"),
        Path("tests/adapters/contracts/aware/ifa_cash_canonical_output.json"),
        "contract-fixture-aware-ifa-cash",
        "contract-fixture-aware-ifa-cash-sha256-placeholder",
    ),
    (
        "ifa_growth",
        Path("tests/fixtures/real/aware/IFA-Growth.csv"),
        Path("tests/adapters/contracts/aware/ifa_growth_canonical_output.json"),
        "contract-fixture-aware-ifa-growth",
        "contract-fixture-aware-ifa-growth-sha256-placeholder",
    ),
    (
        "ifa_international_equities",
        Path("tests/fixtures/real/aware/IFA-International-Equities.csv"),
        Path("tests/adapters/contracts/aware/ifa_international_equities_canonical_output.json"),
        "contract-fixture-aware-ifa-international-equities",
        "contract-fixture-aware-ifa-international-equities-sha256-placeholder",
    ),
    (
        "ifa_moderate",
        Path("tests/fixtures/real/aware/IFA-Moderate.csv"),
        Path("tests/adapters/contracts/aware/ifa_moderate_canonical_output.json"),
        "contract-fixture-aware-ifa-moderate",
        "contract-fixture-aware-ifa-moderate-sha256-placeholder",
    ),
    (
        "ifb_australian_equities",
        Path("tests/fixtures/real/aware/IFB-Australian-Equities.csv"),
        Path("tests/adapters/contracts/aware/ifb_australian_equities_canonical_output.json"),
        "contract-fixture-aware-ifb-australian-equities",
        "contract-fixture-aware-ifb-australian-equities-sha256-placeholder",
    ),
    (
        "ifb_balanced",
        Path("tests/fixtures/real/aware/IFB-Balanced.csv"),
        Path("tests/adapters/contracts/aware/ifb_balanced_canonical_output.json"),
        "contract-fixture-aware-ifb-balanced",
        "contract-fixture-aware-ifb-balanced-sha256-placeholder",
    ),
    (
        "ifb_capital_stable",
        Path("tests/fixtures/real/aware/IFB-Capital-Stable.csv"),
        Path("tests/adapters/contracts/aware/ifb_capital_stable_canonical_output.json"),
        "contract-fixture-aware-ifb-capital-stable",
        "contract-fixture-aware-ifb-capital-stable-sha256-placeholder",
    ),
    (
        "ifb_cash",
        Path("tests/fixtures/real/aware/IFB-Cash.csv"),
        Path("tests/adapters/contracts/aware/ifb_cash_canonical_output.json"),
        "contract-fixture-aware-ifb-cash",
        "contract-fixture-aware-ifb-cash-sha256-placeholder",
    ),
    (
        "ifb_growth",
        Path("tests/fixtures/real/aware/IFB-Growth.csv"),
        Path("tests/adapters/contracts/aware/ifb_growth_canonical_output.json"),
        "contract-fixture-aware-ifb-growth",
        "contract-fixture-aware-ifb-growth-sha256-placeholder",
    ),
    (
        "ifb_international_equities",
        Path("tests/fixtures/real/aware/IFB-International-Equities.csv"),
        Path("tests/adapters/contracts/aware/ifb_international_equities_canonical_output.json"),
        "contract-fixture-aware-ifb-international-equities",
        "contract-fixture-aware-ifb-international-equities-sha256-placeholder",
    ),
    (
        "ifb_moderate",
        Path("tests/fixtures/real/aware/IFB-Moderate.csv"),
        Path("tests/adapters/contracts/aware/ifb_moderate_canonical_output.json"),
        "contract-fixture-aware-ifb-moderate",
        "contract-fixture-aware-ifb-moderate-sha256-placeholder",
    ),
)


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


class TestAwareFrozenContract(unittest.TestCase):
    maxDiff = None

    def test_aware_fixtures_match_frozen_contracts(self) -> None:
        adapter = AwarePhdAdapter()
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
        mismatches.append("first mismatched holdings:\n" + "\n\n".join(row_mismatches))

    return f"Frozen Aware contract drift detected for {label}.\n\n" + "\n\n".join(mismatches)
