from __future__ import annotations

from collections import Counter
import csv
from datetime import datetime
from decimal import Decimal
import io
from pathlib import Path
import unittest

from adapters.base import SourceFileMetadata
from adapters.cbus import CbusPhdAdapter
from adapters.cbus_errors import CbusFileIdentityError, CbusHeaderMismatchError


FIXTURE_PATH = Path("tests/fixtures/real/cbus/super-high-growth__1_.csv").resolve()
PROPERTY_PATH = Path("tests/fixtures/real/cbus/super-property__1_.csv").resolve()
OVERSEAS_SHARES_PATH = Path("tests/fixtures/real/cbus/super-overseas-shares.csv").resolve()
AUSTRALIAN_SHARES_PATH = Path("tests/fixtures/real/cbus/super-australian-shares__1_.csv").resolve()
CASH_PATH = Path("tests/fixtures/real/cbus/super-cash.csv").resolve()
GROWTH_PATH = Path("tests/fixtures/real/cbus/super-growth__1_.csv").resolve()
CONSERVATIVE_PATH = Path("tests/fixtures/real/cbus/super-conservative.csv").resolve()
GROWTH_PLUS_PATH = Path("tests/fixtures/real/cbus/super-growth-plus.csv").resolve()
CONSERVATIVE_GROWTH_PATH = Path("tests/fixtures/real/cbus/super-conservative-growth.csv").resolve()
DIVERSIFIED_FIXED_INTEREST_PATH = Path("tests/fixtures/real/cbus/super-diversified-fixed-interest.csv").resolve()
INDEXED_DIVERSIFIED_PATH = Path("tests/fixtures/real/cbus/super-indexed-diversified.csv").resolve()

BATCH_1_CASES = (
    (
        PROPERTY_PATH,
        "Property Accumulation Option",
        106,
        {"2": 3, "3": 5, "4": 5},
        Counter({"fully_disclosed": 46, "value_only": 37, "ownership_only": 16, "aggregate_total": 7}),
        58,
        16,
    ),
    (
        OVERSEAS_SHARES_PATH,
        "Overseas Shares Accumulation Option",
        1421,
        {"2": 4, "3": 6, "4": 4},
        Counter({"fully_disclosed": 1367, "value_only": 46, "aggregate_total": 6, "name_only": 2}),
        14,
        0,
    ),
    (
        AUSTRALIAN_SHARES_PATH,
        "Australian Shares Accumulation Option",
        353,
        {"2": 4, "3": 6, "4": 4},
        Counter({"fully_disclosed": 316, "value_only": 29, "aggregate_total": 6, "name_only": 2}),
        36,
        0,
    ),
    (
        CASH_PATH,
        "Cash Accumulation Option",
        16,
        {"3": 3},
        Counter({"value_only": 13, "aggregate_total": 3}),
        0,
        0,
    ),
)

BATCH_2_CASES = (
    (
        GROWTH_PATH,
        "Growth Accumulation Option",
        2281,
        {"2": 5, "3": 7, "4": 5},
        Counter({"fully_disclosed": 2068, "value_only": 141, "ownership_only": 36, "name_only": 21, "aggregate_total": 15}),
        140,
        29,
    ),
    (
        CONSERVATIVE_PATH,
        "Conservative Accumulation Option",
        2279,
        {"2": 5, "3": 7, "4": 5},
        Counter({"fully_disclosed": 2061, "value_only": 138, "ownership_only": 36, "name_only": 29, "aggregate_total": 15}),
        140,
        29,
    ),
    (
        GROWTH_PLUS_PATH,
        "Growth Plus Accumulation Option",
        2278,
        {"2": 5, "3": 7, "4": 5},
        Counter({"fully_disclosed": 2068, "value_only": 138, "ownership_only": 36, "name_only": 21, "aggregate_total": 15}),
        140,
        29,
    ),
    (
        CONSERVATIVE_GROWTH_PATH,
        "Conservative Growth Accumulation Option",
        2251,
        {"2": 5, "3": 7, "4": 5},
        Counter({"fully_disclosed": 2068, "value_only": 116, "ownership_only": 32, "name_only": 21, "aggregate_total": 14}),
        140,
        29,
    ),
    (
        DIVERSIFIED_FIXED_INTEREST_PATH,
        "Diversified Fixed Interest Accumulation Option",
        74,
        {"2": 5, "3": 4, "4": 4},
        Counter({"value_only": 50, "name_only": 19, "aggregate_total": 5}),
        0,
        0,
    ),
    (
        INDEXED_DIVERSIFIED_PATH,
        "Indexed Diversified Accumulation Option",
        44,
        {"2": 2, "3": 4, "4": 2},
        Counter({"value_only": 30, "fully_disclosed": 7, "aggregate_total": 5, "name_only": 2}),
        0,
        0,
    ),
)


def make_metadata(source_file_id: str = "fixture-cbus") -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id=source_file_id,
        fund_id="cbus",
        suspected_adapter_key="CbusPhdAdapter",
        reporting_period_id=None,
        source_url=str(FIXTURE_PATH),
        checksum="fixture-cbus",
        received_at=datetime(2026, 4, 24, 0, 0, 0),
    )


def mutate_fixture(mutator) -> bytes:
    with FIXTURE_PATH.open("r", encoding="utf-8", newline="") as handle:
        rows = list(csv.reader(handle))
    mutator(rows)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


class TestCbusAdapterRealFile(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = CbusPhdAdapter()
        cls.result = cls.adapter.parse(make_metadata(), FIXTURE_PATH.read_bytes())
        cls.rows = {record.source_row_number: record for record in cls.result.holdings}

    def test_content_signal_verification_requires_cbus_file_header(self) -> None:
        mutated = mutate_fixture(lambda rows: rows.__setitem__(0, ["Not a Cbus PHD file"] + [""] * 13))
        with self.assertRaises(CbusFileIdentityError):
            self.adapter.parse(make_metadata("fixture-cbus-missing-header"), mutated)

    def test_table_header_drift_is_rejected(self) -> None:
        mutated = mutate_fixture(lambda rows: rows[1].__setitem__(12, "Market Value AUD"))
        with self.assertRaises(CbusHeaderMismatchError):
            self.adapter.parse(make_metadata("fixture-cbus-drifted-header"), mutated)

    def test_verified_file_shape_and_disclosure_distribution(self) -> None:
        self.assertEqual(
            "841a5229926cf6dc5073eeac34fe7d217560b16feb630f6ce8f01d35c9326be5",
            self.result.schema_fingerprint,
        )
        self.assertEqual(2271, self.result.structural_metadata["total_rows_read"])
        self.assertEqual(2249, self.result.structural_metadata["total_rows_emitted"])
        self.assertEqual(15, self.result.structural_metadata["total_rows_aggregate"])
        self.assertEqual({"2": 5, "3": 7, "4": 5}, self.result.structural_metadata["table_rows_skipped_by_table"])
        self.assertEqual(0, self.result.structural_metadata["encoding_replacement_count"])
        self.assertEqual(
            Counter(
                {
                    "fully_disclosed": 2068,
                    "value_only": 122,
                    "ownership_only": 36,
                    "aggregate_total": 15,
                    "name_only": 8,
                }
            ),
            Counter(record.disclosure_completeness for record in self.result.holdings),
        )

    def test_section_driven_columns_and_row_level_semantics(self) -> None:
        cash_row = self.rows[3]
        private_debt_row = self.rows[75]
        fixed_income_external_row = self.rows[83]
        listed_equity_row = self.rows[85]
        property_row = self.rows[2181]
        total_row = self.rows[2251]

        self.assertEqual("AUSTRALIA & NEW ZEALAND BANKING GROUP LTD", cash_row.raw_name)
        self.assertEqual("Cash", cash_row.source_asset_class_raw)
        self.assertEqual("cash", cash_row.canonical_asset_class_code)
        self.assertEqual(Decimal("-880824.54"), cash_row.value_aud)
        self.assertEqual("value_only", cash_row.disclosure_completeness)

        self.assertEqual("ANCORA BIDCO PTY LTD", private_debt_row.raw_name)
        self.assertEqual("private_debt", private_debt_row.canonical_asset_class_code)
        self.assertIsNone(private_debt_row.value_aud)
        self.assertEqual("name_only", private_debt_row.disclosure_completeness)

        self.assertEqual("IFM Investors", fixed_income_external_row.raw_name)
        self.assertEqual("external", fixed_income_external_row.source_subclass_raw)
        self.assertEqual(Decimal("108374772.53"), fixed_income_external_row.value_aud)
        self.assertEqual("value_only", fixed_income_external_row.disclosure_completeness)

        self.assertEqual("361 DEGREES INTERNATIONAL LTD COMMON STOCK HKD 0.1", listed_equity_row.raw_name)
        self.assertEqual("B51BL70", listed_equity_row.security_identifier_value)
        self.assertEqual("SEDOL", listed_equity_row.security_identifier_type)
        self.assertEqual(Decimal("94161.10"), listed_equity_row.units)
        self.assertEqual("fully_disclosed", listed_equity_row.disclosure_completeness)

        self.assertEqual("1 William St Brisbane", property_row.raw_name)
        self.assertEqual("1 William St, Brisbane", property_row.address_raw)
        self.assertEqual(Decimal("0.032624"), property_row.ownership_pct)
        self.assertEqual("ownership_only", property_row.disclosure_completeness)

        self.assertTrue(total_row.is_aggregate)
        self.assertIsNone(total_row.raw_name)
        self.assertEqual("multi_asset_other", total_row.canonical_asset_class_code)
        self.assertEqual("aggregate_total", total_row.disclosure_completeness)

    def test_table_2_3_4_portfolio_posture_rows_are_not_emitted(self) -> None:
        self.assertNotIn("Futures", [record.raw_name for record in self.result.holdings])
        self.assertNotIn("FX Forwards", [record.raw_name for record in self.result.holdings])
        self.assertNotIn("Derivatives TOTAL", [record.source_asset_class_raw for record in self.result.holdings])
        self.assertNotIn("AUD", [record.raw_name for record in self.result.holdings])

    def test_internal_property_rows_preserve_addresses(self) -> None:
        rows = [
            record
            for record in self.result.holdings
            if record.source_asset_class_raw == "Unlisted property internal" and not record.is_aggregate
        ]
        self.assertEqual(29, len(rows))
        self.assertEqual(29, len([record for record in rows if record.address_raw]))
        self.assertEqual(
            "East Walker St, North Sydney. 173-179 Walker St and 11-17 Hampden St, North Sydney",
            self.rows[2195].address_raw,
        )
        self.assertEqual("Newmarket, Randwick, 162 Barker St, Randwick", self.rows[2196].address_raw)

    def test_latest_period_batch_1_files_parse_without_adapter_changes(self) -> None:
        for (
            fixture_path,
            option_name,
            expected_rows,
            expected_skipped_rows,
            expected_completeness,
            expected_property_infrastructure_rows,
            expected_address_backed_property_infrastructure_rows,
        ) in BATCH_1_CASES:
            with self.subTest(option=option_name):
                result = self.adapter.parse(make_metadata(fixture_path.name), fixture_path.read_bytes())

                self.assertEqual([option_name], result.structural_metadata["observed_option_names"])
                self.assertEqual(2025, result.holdings[0].reporting_period_date.year)
                self.assertEqual(expected_rows, len(result.holdings))
                self.assertEqual(expected_skipped_rows, result.structural_metadata["table_rows_skipped_by_table"])
                self.assertNotIn("Futures", [record.raw_name for record in result.holdings])
                self.assertNotIn("FX Forwards", [record.raw_name for record in result.holdings])
                self.assertNotIn("Derivatives TOTAL", [record.source_asset_class_raw for record in result.holdings])
                self.assertEqual(
                    expected_completeness,
                    Counter(record.disclosure_completeness for record in result.holdings),
                )

                property_infrastructure_rows = [
                    record
                    for record in result.holdings
                    if record.canonical_asset_class_code
                    in {
                        "listed_property",
                        "unlisted_property",
                        "listed_infrastructure",
                        "unlisted_infrastructure",
                    }
                    and not record.is_aggregate
                ]
                self.assertEqual(expected_property_infrastructure_rows, len(property_infrastructure_rows))
                self.assertEqual(
                    expected_address_backed_property_infrastructure_rows,
                    len([record for record in property_infrastructure_rows if record.address_raw]),
                )

    def test_latest_period_batch_2_files_parse_with_fixed_income_external_label_tolerance(self) -> None:
        for (
            fixture_path,
            option_name,
            expected_rows,
            expected_skipped_rows,
            expected_completeness,
            expected_property_infrastructure_rows,
            expected_address_backed_property_infrastructure_rows,
        ) in BATCH_2_CASES:
            with self.subTest(option=option_name):
                result = self.adapter.parse(make_metadata(fixture_path.name), fixture_path.read_bytes())

                self.assertEqual([option_name], result.structural_metadata["observed_option_names"])
                self.assertEqual("2025-12-31", result.holdings[0].reporting_period_date.isoformat())
                self.assertEqual(expected_rows, len(result.holdings))
                self.assertEqual(expected_skipped_rows, result.structural_metadata["table_rows_skipped_by_table"])
                self.assertNotIn("Futures", [record.raw_name for record in result.holdings])
                self.assertNotIn("FX Forwards", [record.raw_name for record in result.holdings])
                self.assertNotIn("Derivatives TOTAL", [record.source_asset_class_raw for record in result.holdings])
                self.assertEqual(
                    expected_completeness,
                    Counter(record.disclosure_completeness for record in result.holdings),
                )

                fixed_income_external_rows = [
                    record
                    for record in result.holdings
                    if record.raw_payload_json[0] == "Fixed income external" and not record.is_aggregate
                ]
                self.assertTrue(fixed_income_external_rows)
                self.assertEqual(
                    {"Fixed Income External"},
                    {record.source_asset_class_raw for record in fixed_income_external_rows},
                )
                self.assertEqual({"external"}, {record.source_subclass_raw for record in fixed_income_external_rows})

                property_infrastructure_rows = [
                    record
                    for record in result.holdings
                    if record.canonical_asset_class_code
                    in {
                        "listed_property",
                        "unlisted_property",
                        "listed_infrastructure",
                        "unlisted_infrastructure",
                    }
                    and not record.is_aggregate
                ]
                self.assertEqual(expected_property_infrastructure_rows, len(property_infrastructure_rows))
                self.assertEqual(
                    expected_address_backed_property_infrastructure_rows,
                    len([record for record in property_infrastructure_rows if record.address_raw]),
                )


if __name__ == "__main__":
    unittest.main()
