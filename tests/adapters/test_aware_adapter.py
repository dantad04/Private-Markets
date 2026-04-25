from __future__ import annotations

from collections import Counter
from datetime import datetime
from decimal import Decimal
from pathlib import Path
import unittest

from adapters.aware import AwarePhdAdapter
from adapters.base import SourceFileMetadata


FIXTURE_PATH = Path("tests/fixtures/aware_synthetic_table1_minimal.csv").resolve()
REAL_SHAPE_FIXTURE_PATH = Path("tests/fixtures/aware_investment_funds_real_shape_minimal.csv").resolve()
REAL_FIXTURE_DIR = Path("tests/fixtures/real/aware").resolve()
REAL_SHAPE_FINGERPRINT = "5f32c5b412bf04749982c45080dfec21e9e2e46911971d1a9d6e1f2277cb1e0a"
LATEST_PERIOD_BATCH_CASES = (
    (REAL_FIXTURE_DIR / "IFA-Australian-Equities.csv", "Australian Equities", "SS8K", 329),
    (REAL_FIXTURE_DIR / "IFA-Balanced.csv", "Balanced", "SS6K", 1968),
    (REAL_FIXTURE_DIR / "IFA-Capital-Stable.csv", "Capital Stable", "SS5K", 1966),
    (REAL_FIXTURE_DIR / "IFA-Cash.csv", "Cash", "SS3K", 25),
    (REAL_FIXTURE_DIR / "IFA-Growth.csv", "Growth", "SS9K", 1965),
    (REAL_FIXTURE_DIR / "IFA-International-Equities.csv", "International Equities", "SRCK", 1344),
    (REAL_FIXTURE_DIR / "IFA-Moderate.csv", "Moderate", "SS7K", 1969),
    (REAL_FIXTURE_DIR / "IFB-Australian-Equities.csv", "Australian Equities", "SR5K", 329),
    (REAL_FIXTURE_DIR / "IFB-Balanced.csv", "Balanced", "SR2K", 1968),
    (REAL_FIXTURE_DIR / "IFB-Capital-Stable.csv", "Capital Stable", "SRYK", 1966),
    (REAL_FIXTURE_DIR / "IFB-Cash.csv", "Cash", "SRSK", 25),
    (REAL_FIXTURE_DIR / "IFB-Growth.csv", "Growth", "SR6K", 1965),
    (REAL_FIXTURE_DIR / "IFB-International-Equities.csv", "International Equities", "SR7K", 1344),
    (REAL_FIXTURE_DIR / "IFB-Moderate.csv", "Moderate", "SR4K", 1969),
)


def make_metadata(source_file_id: str = "fixture-aware") -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id=source_file_id,
        fund_id="aware",
        suspected_adapter_key="AwarePhdAdapter",
        reporting_period_id=None,
        source_url=str(FIXTURE_PATH),
        checksum="fixture-aware",
        received_at=datetime(2026, 4, 19, 0, 0, 0),
    )


def make_real_shape_metadata(
    source_file_id: str = "fixture-aware-investment-funds",
    fixture_path: Path = REAL_SHAPE_FIXTURE_PATH,
) -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id=source_file_id,
        fund_id="aware",
        suspected_adapter_key="AwarePhdAdapter",
        reporting_period_id=None,
        source_url=str(fixture_path),
        checksum="fixture-aware-investment-funds",
        received_at=datetime(2026, 4, 25, 0, 0, 0),
    )


class TestAwareAdapterSyntheticFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = AwarePhdAdapter()
        cls.result = cls.adapter.parse(make_metadata(), FIXTURE_PATH.read_bytes())
        cls.rows = {record.source_row_number: record for record in cls.result.holdings}

    def test_extracts_reporting_date_and_option_from_schedule_header(self) -> None:
        self.assertEqual(["AWARESYNTHHG"], self.result.structural_metadata["observed_options"])
        self.assertEqual(["2025-12-31"], self.result.structural_metadata["observed_reporting_dates"])
        self.assertEqual(
            ["ASSETS", "DERIVATIVES", "DERIVATIVES BY ASSET CLASS", "DERIVATIVES BY CURRENCY"],
            self.result.structural_metadata["observed_section_labels"],
        )
        self.assertEqual([1, 2, 3, 4], self.result.structural_metadata["observed_tables"])
        self.assertEqual(0, self.result.structural_metadata["encoding_replacement_count"])

    def test_parses_only_table_1_rows_and_skips_tables_2_to_4(self) -> None:
        self.assertEqual(19, self.result.structural_metadata["total_rows_emitted"])
        self.assertEqual({"2": 3, "3": 3, "4": 3}, self.result.structural_metadata["table_rows_skipped_by_table"])
        self.assertEqual(
            {
                "aggregate_total": 10,
                "fully_disclosed": 1,
                "name_only": 1,
                "ownership_only": 2,
                "value_only": 5,
            },
            self.result.parse_statistics["disclosure_completeness_counts"],
        )

    def test_selects_raw_name_by_context_not_first_non_empty(self) -> None:
        self.assertEqual("BANK ALPHA", self.rows[3].raw_name)
        self.assertEqual("ISSUER BOND CO", self.rows[4].raw_name)
        self.assertEqual("STATEFUL CREDIT PARTNERS", self.rows[6].raw_name)
        self.assertEqual("SYNTH LISTED EQUITY LTD", self.rows[7].raw_name)

    def test_emits_aggregate_rows_for_subtotals_and_total(self) -> None:
        subtotal = self.rows[12]
        total = self.rows[21]
        self.assertTrue(subtotal.is_aggregate)
        self.assertEqual("aggregate_total", subtotal.disclosure_completeness)
        self.assertEqual("cash", subtotal.canonical_asset_class_code)
        self.assertTrue(total.is_aggregate)
        self.assertEqual("multi_asset_other", total.canonical_asset_class_code)

    def test_parses_ownership_only_and_hundred_percent_cleanly(self) -> None:
        row = self.rows[8]
        self.assertEqual("ownership_only", row.disclosure_completeness)
        self.assertEqual(Decimal("1"), row.ownership_pct)

    def test_parses_externally_managed_value_only(self) -> None:
        row = self.rows[9]
        self.assertEqual("BLACKBIRD SYNTHETIC MANAGER", row.raw_name)
        self.assertEqual("value_only", row.disclosure_completeness)
        self.assertEqual(Decimal("5000000"), row.value_aud)

    def test_preserves_property_address_and_ownership(self) -> None:
        row = self.rows[10]
        self.assertEqual("SYNTH PROPERTY TRUST", row.raw_name)
        self.assertEqual("\"SYNTHETIC ESTATE\", 1 TEST STREET, SYDNEY NSW 2000", row.address_raw)
        self.assertEqual(Decimal("0.5"), row.ownership_pct)
        self.assertEqual("ownership_only", row.disclosure_completeness)

    def test_parses_name_only_private_debt_row(self) -> None:
        row = self.rows[5]
        self.assertEqual("PRIVATE DEBT BORROWER PTY LTD", row.raw_name)
        self.assertEqual("name_only", row.disclosure_completeness)
        self.assertEqual("private_debt", row.canonical_asset_class_code)

    def test_infers_asx_identifier_type(self) -> None:
        row = self.rows[7]
        self.assertEqual("SLE AU", row.security_identifier_value)
        self.assertEqual("ASX_CODE", row.security_identifier_type)

    def test_tracks_utf8_replacement_count_when_decode_replaces_bytes(self) -> None:
        raw_bytes = FIXTURE_PATH.read_bytes().replace(b"SYNTH PROPERTY TRUST", b"SYNTH PROP\xC0RTY TRUST", 1)
        result = self.adapter.parse(make_metadata("fixture-aware-replacement"), raw_bytes)
        self.assertEqual(1, result.structural_metadata["encoding_replacement_count"])
        self.assertEqual(["UTF-8 replacement characters: 1"], result.adapter_warnings)
        mutated_row = next(record for record in result.holdings if record.source_row_number == 10)
        self.assertIn("\ufffd", mutated_row.raw_name)


class TestAwareInvestmentFundsRealShapeFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = AwarePhdAdapter()
        cls.result = cls.adapter.parse(make_real_shape_metadata(), REAL_SHAPE_FIXTURE_PATH.read_bytes())

    def test_matches_approved_real_batch_fingerprint(self) -> None:
        self.assertEqual(REAL_SHAPE_FINGERPRINT, self.result.schema_fingerprint)
        self.assertEqual(
            [
                "CASH",
                "FIXED INCOME",
                "LISTED ALTERNATIVES",
                "LISTED EQUITY",
                "LISTED INFRASTRUCTURE",
                "LISTED PROPERTY",
                "TOTAL INVESTMENT ITEMS",
                "UNLISTED ALTERNATIVES",
                "UNLISTED EQUITY",
                "UNLISTED INFRASTRUCTURE",
                "UNLISTED PROPERTY",
            ],
            self.result.structural_metadata["observed_asset_classes"],
        )

    def test_maps_table_1_labels_to_existing_canonical_taxonomy(self) -> None:
        rows_by_label = {
            record.source_asset_class_raw: record.canonical_asset_class_code
            for record in self.result.holdings
            if not record.is_aggregate
        }
        self.assertEqual("cash", rows_by_label["CASH"])
        self.assertEqual("fixed_income", rows_by_label["FIXED INCOME"])
        self.assertEqual("listed_equity", rows_by_label["LISTED EQUITY"])
        self.assertEqual("listed_infrastructure", rows_by_label["LISTED INFRASTRUCTURE"])
        self.assertEqual("listed_property", rows_by_label["LISTED PROPERTY"])
        self.assertEqual("alternatives", rows_by_label["UNLISTED ALTERNATIVES"])
        self.assertEqual("unlisted_equity", rows_by_label["UNLISTED EQUITY"])
        self.assertEqual("unlisted_infrastructure", rows_by_label["UNLISTED INFRASTRUCTURE"])
        self.assertEqual("unlisted_property", rows_by_label["UNLISTED PROPERTY"])

    def test_tables_2_to_4_remain_skipped(self) -> None:
        self.assertEqual({"2": 7, "3": 8, "4": 5}, self.result.structural_metadata["table_rows_skipped_by_table"])
        self.assertEqual(26, self.result.structural_metadata["total_rows_emitted"])
        self.assertFalse(
            any(
                record.raw_name in {"FORWARDS", "FUTURES", "OPTIONS", "OTHERS", "SWAPS", "AUD", "USD", "TOTAL"}
                for record in self.result.holdings
            )
        )

    def test_aggregate_total_only_comes_from_table_1_subtotals_and_total(self) -> None:
        expected_aggregate_labels = {
            "SUB TOTAL CASH",
            "SUB TOTAL FIXED INCOME EXTERNALLY",
            "SUB TOTAL FIXED INCOME INTERNALLY",
            "SUB TOTAL LISTED ALTERNATIVES",
            "SUB TOTAL LISTED EQUITY",
            "SUB TOTAL LISTED INFRASTRUCTURE",
            "SUB TOTAL LISTED PROPERTY",
            "SUB TOTAL UNLISTED ALTERNATIVES EXTERNALLY",
            "SUB TOTAL UNLISTED ALTERNATIVES INTERNALLY",
            "SUB TOTAL UNLISTED EQUITY EXTERNALLY",
            "SUB TOTAL UNLISTED EQUITY INTERNALLY",
            "SUB TOTAL UNLISTED INFRASTRUCTURE EXTERNALLY",
            "SUB TOTAL UNLISTED INFRASTRUCTURE INTERNALLY",
            "SUB TOTAL UNLISTED PROPERTY EXTERNALLY",
            "SUB TOTAL UNLISTED PROPERTY INTERNALLY",
            "TOTAL INVESTMENT ITEMS",
        }
        aggregate_rows = [record for record in self.result.holdings if record.is_aggregate]
        self.assertEqual(16, len(aggregate_rows))
        self.assertEqual(
            expected_aggregate_labels,
            {record.source_asset_class_raw for record in aggregate_rows},
        )
        self.assertEqual({"aggregate_total"}, {record.disclosure_completeness for record in aggregate_rows})


class TestAwareInvestmentFundsLatestPeriodBatch(unittest.TestCase):
    def test_accepted_batch_parses_expected_table_1_counts_and_skips_tables_2_to_4(self) -> None:
        adapter = AwarePhdAdapter()
        total_holdings = 0
        total_aggregate = 0
        total_skipped_posture = 0

        for fixture_path, friendly_name, option_code, expected_rows in LATEST_PERIOD_BATCH_CASES:
            with self.subTest(file=fixture_path.name):
                result = adapter.parse(
                    make_real_shape_metadata(f"fixture-aware-{fixture_path.stem}", fixture_path),
                    fixture_path.read_bytes(),
                )

                self.assertEqual(REAL_SHAPE_FINGERPRINT, result.schema_fingerprint)
                self.assertEqual([option_code], result.structural_metadata["observed_options"])
                self.assertEqual(friendly_name, fixture_path.stem.split("-", 1)[1].replace("-", " "))
                self.assertEqual(["2025-12-31"], result.structural_metadata["observed_reporting_dates"])
                self.assertEqual(expected_rows, len(result.holdings))
                self.assertEqual(16, result.structural_metadata["total_rows_aggregate"])
                self.assertEqual({"2": 7, "3": 8, "4": 5}, result.structural_metadata["table_rows_skipped_by_table"])
                self.assertFalse(
                    any(
                        record.raw_name in {"FORWARDS", "FUTURES", "OPTIONS", "OTHERS", "SWAPS", "AUD", "USD", "TOTAL"}
                        for record in result.holdings
                    )
                )

                total_holdings += len(result.holdings)
                total_aggregate += result.structural_metadata["total_rows_aggregate"]
                total_skipped_posture += sum(result.structural_metadata["table_rows_skipped_by_table"].values())

        self.assertEqual(19132, total_holdings)
        self.assertEqual(224, total_aggregate)
        self.assertEqual(280, total_skipped_posture)

    def test_accepted_batch_disclosure_completeness_profile(self) -> None:
        adapter = AwarePhdAdapter()
        completeness = Counter()
        for fixture_path, _friendly_name, _option_code, _expected_rows in LATEST_PERIOD_BATCH_CASES:
            result = adapter.parse(
                make_real_shape_metadata(f"fixture-aware-{fixture_path.stem}", fixture_path),
                fixture_path.read_bytes(),
            )
            completeness.update(record.disclosure_completeness for record in result.holdings)

        self.assertEqual(
            Counter({"fully_disclosed": 18064, "value_only": 844, "aggregate_total": 224}),
            completeness,
        )
