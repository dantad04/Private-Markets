from __future__ import annotations

from dataclasses import fields, is_dataclass
from datetime import date, datetime
from decimal import Decimal
import difflib
import json
from pathlib import Path
import unittest

from adapters.base import AdapterParseResult, SourceFileMetadata
from adapters.hostplus import HostPlusPhdStateMachineAdapter


FIXTURE_PATH = Path("tests/fixtures/hostplus_real_extract.csv")
CONTRACT_PATH = Path("tests/adapters/contracts/hostplus/canonical_output.json")
HOSTPLUS_FIXTURE_DIR = Path("tests/fixtures/real/hostplus")
CONTRACT_CASES = (
    ("high_growth", FIXTURE_PATH, CONTRACT_PATH, "contract-fixture-hostplus", "contract-fixture-hostplus-sha256-placeholder"),
    (
        "australian_shares",
        HOSTPLUS_FIXTURE_DIR / "australian-shares.csv",
        Path("tests/adapters/contracts/hostplus/australian_shares_canonical_output.json"),
        "contract-fixture-hostplus-australian-shares",
        "contract-fixture-hostplus-australian-shares-sha256-placeholder",
    ),
    (
        "australian_shares_indexed",
        HOSTPLUS_FIXTURE_DIR / "australian-shares-indexed.csv",
        Path("tests/adapters/contracts/hostplus/australian_shares_indexed_canonical_output.json"),
        "contract-fixture-hostplus-australian-shares-indexed",
        "contract-fixture-hostplus-australian-shares-indexed-sha256-placeholder",
    ),
    (
        "cash",
        HOSTPLUS_FIXTURE_DIR / "cash.csv",
        Path("tests/adapters/contracts/hostplus/cash_canonical_output.json"),
        "contract-fixture-hostplus-cash",
        "contract-fixture-hostplus-cash-sha256-placeholder",
    ),
    (
        "indexed_high_growth",
        HOSTPLUS_FIXTURE_DIR / "indexed-high-growth.csv",
        Path("tests/adapters/contracts/hostplus/indexed_high_growth_canonical_output.json"),
        "contract-fixture-hostplus-indexed-high-growth",
        "contract-fixture-hostplus-indexed-high-growth-sha256-placeholder",
    ),
    (
        "international_shares",
        HOSTPLUS_FIXTURE_DIR / "international-shares.csv",
        Path("tests/adapters/contracts/hostplus/international_shares_canonical_output.json"),
        "contract-fixture-hostplus-international-shares",
        "contract-fixture-hostplus-international-shares-sha256-placeholder",
    ),
    (
        "sri_high_growth",
        HOSTPLUS_FIXTURE_DIR / "sri-high-growth.csv",
        Path("tests/adapters/contracts/hostplus/sri_high_growth_canonical_output.json"),
        "contract-fixture-hostplus-sri-high-growth",
        "contract-fixture-hostplus-sri-high-growth-sha256-placeholder",
    ),
    (
        "balanced",
        HOSTPLUS_FIXTURE_DIR / "balanced.csv",
        Path("tests/adapters/contracts/hostplus/balanced_canonical_output.json"),
        "contract-fixture-hostplus-balanced",
        "contract-fixture-hostplus-balanced-sha256-placeholder",
    ),
    (
        "conservative",
        HOSTPLUS_FIXTURE_DIR / "conservative.csv",
        Path("tests/adapters/contracts/hostplus/conservative_canonical_output.json"),
        "contract-fixture-hostplus-conservative",
        "contract-fixture-hostplus-conservative-sha256-placeholder",
    ),
    (
        "defensive",
        HOSTPLUS_FIXTURE_DIR / "defensive.csv",
        Path("tests/adapters/contracts/hostplus/defensive_canonical_output.json"),
        "contract-fixture-hostplus-defensive",
        "contract-fixture-hostplus-defensive-sha256-placeholder",
    ),
    (
        "growth",
        HOSTPLUS_FIXTURE_DIR / "growth.csv",
        Path("tests/adapters/contracts/hostplus/growth_canonical_output.json"),
        "contract-fixture-hostplus-growth",
        "contract-fixture-hostplus-growth-sha256-placeholder",
    ),
    (
        "stable",
        HOSTPLUS_FIXTURE_DIR / "stable.csv",
        Path("tests/adapters/contracts/hostplus/stable_canonical_output.json"),
        "contract-fixture-hostplus-stable",
        "contract-fixture-hostplus-stable-sha256-placeholder",
    ),
    (
        "sri_balanced",
        HOSTPLUS_FIXTURE_DIR / "sri-balanced.csv",
        Path("tests/adapters/contracts/hostplus/sri_balanced_canonical_output.json"),
        "contract-fixture-hostplus-sri-balanced",
        "contract-fixture-hostplus-sri-balanced-sha256-placeholder",
    ),
    (
        "sri_defensive",
        HOSTPLUS_FIXTURE_DIR / "sri-defensive.csv",
        Path("tests/adapters/contracts/hostplus/sri_defensive_canonical_output.json"),
        "contract-fixture-hostplus-sri-defensive",
        "contract-fixture-hostplus-sri-defensive-sha256-placeholder",
    ),
    (
        "bonds",
        HOSTPLUS_FIXTURE_DIR / "bonds.csv",
        Path("tests/adapters/contracts/hostplus/bonds_canonical_output.json"),
        "contract-fixture-hostplus-bonds",
        "contract-fixture-hostplus-bonds-sha256-placeholder",
    ),
    (
        "bonds_indexed",
        HOSTPLUS_FIXTURE_DIR / "bonds-indexed.csv",
        Path("tests/adapters/contracts/hostplus/bonds_indexed_canonical_output.json"),
        "contract-fixture-hostplus-bonds-indexed",
        "contract-fixture-hostplus-bonds-indexed-sha256-placeholder",
    ),
    (
        "indexed_balanced",
        HOSTPLUS_FIXTURE_DIR / "indexed-balanced.csv",
        Path("tests/adapters/contracts/hostplus/indexed_balanced_canonical_output.json"),
        "contract-fixture-hostplus-indexed-balanced",
        "contract-fixture-hostplus-indexed-balanced-sha256-placeholder",
    ),
    (
        "indexed_conservative",
        HOSTPLUS_FIXTURE_DIR / "indexed-conservative.csv",
        Path("tests/adapters/contracts/hostplus/indexed_conservative_canonical_output.json"),
        "contract-fixture-hostplus-indexed-conservative",
        "contract-fixture-hostplus-indexed-conservative-sha256-placeholder",
    ),
    (
        "indexed_defensive",
        HOSTPLUS_FIXTURE_DIR / "indexed-defensive.csv",
        Path("tests/adapters/contracts/hostplus/indexed_defensive_canonical_output.json"),
        "contract-fixture-hostplus-indexed-defensive",
        "contract-fixture-hostplus-indexed-defensive-sha256-placeholder",
    ),
    (
        "indexed_growth",
        HOSTPLUS_FIXTURE_DIR / "indexed-growth.csv",
        Path("tests/adapters/contracts/hostplus/indexed_growth_canonical_output.json"),
        "contract-fixture-hostplus-indexed-growth",
        "contract-fixture-hostplus-indexed-growth-sha256-placeholder",
    ),
    (
        "indexed_stable",
        HOSTPLUS_FIXTURE_DIR / "indexed-stable.csv",
        Path("tests/adapters/contracts/hostplus/indexed_stable_canonical_output.json"),
        "contract-fixture-hostplus-indexed-stable",
        "contract-fixture-hostplus-indexed-stable-sha256-placeholder",
    ),
)


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


def load_committed_contract(contract_path: Path) -> dict[str, object]:
    return json.loads(contract_path.read_text(encoding="utf-8"))


class TestHostPlusFrozenContract(unittest.TestCase):
    maxDiff = None

    def test_hostplus_fixtures_match_frozen_contracts(self) -> None:
        adapter = HostPlusPhdStateMachineAdapter()
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

    return f"Frozen Host-Plus contract drift detected for {label}.\n\n" + "\n\n".join(mismatches)
