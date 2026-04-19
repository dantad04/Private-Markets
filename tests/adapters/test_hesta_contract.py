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
from tests.hesta_fixture import FIXTURE_PATH


CONTRACT_PATH = Path("tests/adapters/contracts/hesta/canonical_output.json")


def make_contract_metadata() -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id="contract-fixture-hesta",
        fund_id="hesta",
        suspected_adapter_key="HestaPhdAdapter",
        reporting_period_id=None,
        source_url=str(FIXTURE_PATH),
        checksum="contract-fixture-sha256-placeholder",
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


def load_committed_contract() -> dict[str, object]:
    return json.loads(CONTRACT_PATH.read_text(encoding="utf-8"))


class TestHestaFrozenContract(unittest.TestCase):
    maxDiff = None

    def test_hesta_fixture_matches_frozen_contract(self) -> None:
        result = HestaPhdAdapter().parse(make_contract_metadata(), FIXTURE_PATH.read_bytes())
        actual = serialise_parse_result(result)
        expected = load_committed_contract()

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
        mismatches.append("first mismatched holdings:\n" + "\n\n".join(row_mismatches))

    return "Frozen Hesta contract drift detected.\n\n" + "\n\n".join(mismatches)
