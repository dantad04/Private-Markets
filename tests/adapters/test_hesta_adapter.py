from __future__ import annotations

import csv
from datetime import datetime
from decimal import Decimal
import io
import json
import unittest

from adapters.base import SourceFileMetadata
from adapters.hesta import HestaPhdAdapter
from adapters.hesta_errors import (
    InvalidDateError,
    InvalidNumericError,
    MalformedRowError,
    MultipleOptionsError,
    UnexpectedNullTokenError,
    UnknownAssetClassError,
)
from adapters.hesta_normalisation import infer_identifier_type, parse_numeric, parse_percent, parse_uk_date
from tests.hesta_fixture import EXPECTED_PATH, FIXTURE_PATH, load_expected_outputs


def make_metadata(source_file_id: str = "fixture-hesta") -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id=source_file_id,
        fund_id="hesta",
        suspected_adapter_key="HestaPhdAdapter",
        reporting_period_id=None,
        source_url=str(FIXTURE_PATH),
        checksum="fixture",
        received_at=datetime(2026, 4, 18, 0, 0, 0),
    )


def load_fixture_bytes() -> bytes:
    return FIXTURE_PATH.read_bytes()


def mutate_fixture(mutator) -> bytes:
    with FIXTURE_PATH.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    mutator(rows)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


def serialise_record(record) -> dict[str, object]:
    data = {}
    for field_name, value in record.__dict__.items():
        if isinstance(value, Decimal):
            data[field_name] = str(value)
        elif isinstance(value, datetime):
            data[field_name] = value.isoformat()
        elif hasattr(value, "isoformat") and not isinstance(value, (str, list, dict)):
            data[field_name] = value.isoformat()
        else:
            data[field_name] = value
    return data


class TestHestaAdapterAgainstFixture(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = HestaPhdAdapter()
        cls.result = cls.adapter.parse(make_metadata(), load_fixture_bytes())
        cls.expected = load_expected_outputs()

    def test_expected_summary_counts(self) -> None:
        summary = self.expected["summary"]
        self.assertEqual(summary["total_rows_emitted"], self.result.structural_metadata["total_rows_emitted"])
        self.assertEqual(summary["total_rows_aggregate"], self.result.structural_metadata["total_rows_aggregate"])
        self.assertEqual(
            summary["disclosure_completeness_counts"],
            self.result.parse_statistics["disclosure_completeness_counts"],
        )
        self.assertEqual(
            summary["canonical_asset_class_counts"],
            self.result.parse_statistics["canonical_asset_class_counts"],
        )

    def test_expected_golden_rows(self) -> None:
        rows_by_number = {record.source_row_number: record for record in self.result.holdings}
        for golden in self.expected["golden_rows"]:
            record = rows_by_number[golden["source_row_number"]]
            self.assertEqual(
                golden["raw_csv"],
                ",".join(record.raw_payload_json),
                msg=f"raw CSV mismatch at row {golden['source_row_number']}",
            )
            serialised = serialise_record(record)
            for key, expected_value in golden["expected"].items():
                self.assertEqual(
                    expected_value,
                    serialised[key],
                    msg=f"field {key} mismatch at row {golden['source_row_number']}",
                )

    def test_expected_warning_profile(self) -> None:
        self.assertEqual(["row 3: negative value_aud"], self.result.adapter_warnings)

    def test_synthetic_name_only_branch(self) -> None:
        synthetic = (
            "Effective Date,Option,Asset Class,Internal/External,Name/kind of investment item,Units,"
            "Value (AUD),Weighting,% Ownership / Property Held,Currency,Security Identifier\n"
            "31/12/2025,High Growth,Unlisted Equity,Internally Managed,Synthetic HoldCo Pty Ltd,,,,,,\n"
        ).encode("utf-8")
        result = self.adapter.parse(make_metadata("synthetic-name-only"), synthetic)
        self.assertEqual(1, len(result.holdings))
        self.assertEqual("name_only", result.holdings[0].disclosure_completeness)


class TestHestaAdapterErrors(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = HestaPhdAdapter()

    def test_wrong_column_count_raises(self) -> None:
        mutated = mutate_fixture(lambda rows: rows.__setitem__(1, rows[1][:-1]))
        with self.assertRaises(MalformedRowError):
            self.adapter.parse(make_metadata(), mutated)

    def test_unknown_asset_class_raises(self) -> None:
        def mutator(rows):
            rows[1][2] = "Crypto"

        mutated = mutate_fixture(mutator)
        with self.assertRaises(UnknownAssetClassError):
            self.adapter.parse(make_metadata(), mutated)

    def test_mmdd_date_raises(self) -> None:
        def mutator(rows):
            rows[1][0] = "12/31/2025"

        mutated = mutate_fixture(mutator)
        with self.assertRaises(InvalidDateError):
            self.adapter.parse(make_metadata(), mutated)

    def test_dollar_formatted_value_raises(self) -> None:
        def mutator(rows):
            rows[1][6] = "$1,234"

        mutated = mutate_fixture(mutator)
        with self.assertRaises(InvalidNumericError):
            self.adapter.parse(make_metadata(), mutated)

    def test_unexpected_null_token_raises(self) -> None:
        def mutator(rows):
            rows[1][9] = "-"

        mutated = mutate_fixture(mutator)
        with self.assertRaises(UnexpectedNullTokenError):
            self.adapter.parse(make_metadata(), mutated)

    def test_multiple_options_raises(self) -> None:
        def mutator(rows):
            rows[2][1] = "Balanced"

        mutated = mutate_fixture(mutator)
        with self.assertRaises(MultipleOptionsError):
            self.adapter.parse(make_metadata(), mutated)


class TestHestaNormalisationPureFunctions(unittest.TestCase):
    def test_parse_uk_date(self) -> None:
        self.assertEqual("2025-12-31", parse_uk_date("31/12/2025", 2).isoformat())
        self.assertEqual("2024-02-29", parse_uk_date("29/02/2024", 2).isoformat())
        with self.assertRaises(InvalidDateError):
            parse_uk_date("31/31/2025", 2)

    def test_parse_percent(self) -> None:
        self.assertEqual(Decimal("0.169"), parse_percent("16.90%", 2, "% Ownership / Property Held"))
        self.assertEqual(Decimal("1"), parse_percent("100.00%", 2, "% Ownership / Property Held"))
        self.assertIsNone(parse_percent("", 2, "% Ownership / Property Held"))
        with self.assertRaises(InvalidNumericError):
            parse_percent("16.90", 2, "% Ownership / Property Held")

    def test_parse_numeric(self) -> None:
        self.assertEqual(Decimal("5.7E-7"), parse_numeric("5.7e-07", 2, "Weighting"))
        self.assertEqual(Decimal("-3141"), parse_numeric("-3141", 2, "Value (AUD)"))
        self.assertIsNone(parse_numeric("", 2, "Units"))
        with self.assertRaises(InvalidNumericError):
            parse_numeric("$1,234", 2, "Value (AUD)")

    def test_infer_identifier_type(self) -> None:
        self.assertEqual("ISIN", infer_identifier_type("AU000000APA1"))
        self.assertEqual("UNKNOWN", infer_identifier_type("APA"))
        self.assertIsNone(infer_identifier_type(""))


class TestHestaAdapterDeterminism(unittest.TestCase):
    def setUp(self) -> None:
        self.adapter = HestaPhdAdapter()
        self.raw_bytes = load_fixture_bytes()

    def test_same_input_produces_identical_output(self) -> None:
        first = self.adapter.parse(make_metadata("fixture-a"), self.raw_bytes)
        second = self.adapter.parse(make_metadata("fixture-a"), self.raw_bytes)
        first_serialised = [serialise_record(record) for record in first.holdings]
        second_serialised = [serialise_record(record) for record in second.holdings]
        self.assertEqual(first_serialised, second_serialised)
        self.assertEqual(first.schema_fingerprint, second.schema_fingerprint)
        self.assertEqual(first.parse_statistics, second.parse_statistics)

    def test_schema_fingerprint_is_stable_across_runs(self) -> None:
        first = self.adapter.parse(make_metadata("fixture-a"), self.raw_bytes)
        second = self.adapter.parse(make_metadata("fixture-a"), self.raw_bytes)
        self.assertEqual(first.schema_fingerprint.encode("utf-8"), second.schema_fingerprint.encode("utf-8"))

    def test_metadata_variation_only_changes_provenance(self) -> None:
        first = self.adapter.parse(make_metadata("fixture-a"), self.raw_bytes)
        second = self.adapter.parse(make_metadata("fixture-b"), self.raw_bytes)
        self.assertEqual(len(first.holdings), len(second.holdings))

        first_records = [serialise_record(record) for record in first.holdings]
        second_records = [serialise_record(record) for record in second.holdings]

        for left, right in zip(first_records, second_records):
            self.assertNotEqual(left["source_file_id"], right["source_file_id"])
            left = {k: v for k, v in left.items() if k != "source_file_id"}
            right = {k: v for k, v in right.items() if k != "source_file_id"}
            self.assertEqual(left, right)
