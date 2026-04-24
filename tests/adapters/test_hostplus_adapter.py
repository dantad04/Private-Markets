from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import csv
import io
import unittest

from adapters.base import SourceFileMetadata
from adapters.hostplus import HostPlusPhdStateMachineAdapter
from adapters.hostplus_errors import HostPlusFileIdentityError, HostPlusUnknownSectionError


REAL_FIXTURE_PATH = Path("tests/fixtures/real/Host-PlusHigh Growth.csv").resolve()
EXTRACT_FIXTURE_PATH = Path("tests/fixtures/hostplus_real_extract.csv").resolve()
HOSTPLUS_FIXTURE_DIR = Path("tests/fixtures/real/hostplus").resolve()
AUSTRALIAN_SHARES_PATH = HOSTPLUS_FIXTURE_DIR / "australian-shares.csv"
AUSTRALIAN_SHARES_INDEXED_PATH = HOSTPLUS_FIXTURE_DIR / "australian-shares-indexed.csv"
CASH_PATH = HOSTPLUS_FIXTURE_DIR / "cash.csv"
INDEXED_HIGH_GROWTH_PATH = HOSTPLUS_FIXTURE_DIR / "indexed-high-growth.csv"
INTERNATIONAL_SHARES_PATH = HOSTPLUS_FIXTURE_DIR / "international-shares.csv"
SRI_HIGH_GROWTH_PATH = HOSTPLUS_FIXTURE_DIR / "sri-high-growth.csv"
BALANCED_PATH = HOSTPLUS_FIXTURE_DIR / "balanced.csv"
CONSERVATIVE_PATH = HOSTPLUS_FIXTURE_DIR / "conservative.csv"
DEFENSIVE_PATH = HOSTPLUS_FIXTURE_DIR / "defensive.csv"
GROWTH_PATH = HOSTPLUS_FIXTURE_DIR / "growth.csv"
STABLE_PATH = HOSTPLUS_FIXTURE_DIR / "stable.csv"
SRI_BALANCED_PATH = HOSTPLUS_FIXTURE_DIR / "sri-balanced.csv"
SRI_DEFENSIVE_PATH = HOSTPLUS_FIXTURE_DIR / "sri-defensive.csv"

LATEST_PERIOD_BATCH_CASES = (
    (AUSTRALIAN_SHARES_PATH, "HC Australian Shares - Class A Option", 343, Counter({"value_only": 339, "aggregate_total": 4})),
    (
        AUSTRALIAN_SHARES_INDEXED_PATH,
        "HC Australian Shares - Indexed - Class A Option",
        215,
        Counter({"value_only": 212, "aggregate_total": 3}),
    ),
    (CASH_PATH, "HC Cash - Class A Option", 5, Counter({"value_only": 3, "aggregate_total": 2})),
    (
        INDEXED_HIGH_GROWTH_PATH,
        "HC Indexed High Growth - Class A Option",
        2531,
        Counter({"value_only": 2525, "aggregate_total": 4, "name_only": 2}),
    ),
    (
        INTERNATIONAL_SHARES_PATH,
        "HC International Shares - Class A Option",
        2856,
        Counter({"value_only": 2823, "name_only": 29, "aggregate_total": 4}),
    ),
    (
        SRI_HIGH_GROWTH_PATH,
        "HC SRI High Growth - Class A Option",
        565,
        Counter({"value_only": 560, "aggregate_total": 4, "name_only": 1}),
    ),
)

CORE_DIVERSIFIED_BATCH_CASES = (
    (
        BALANCED_PATH,
        "HC Balanced - Class A Option",
        3308,
        Counter({"value_only": 3253, "name_only": 30, "ownership_only": 14, "aggregate_total": 11}),
        Counter(
            {
                "Listed Equity": 3118,
                "Cash": 75,
                "Unlisted Equity": 46,
                "Unlisted Property": 24,
                "Unlisted Infrastructure": 20,
                "Fixed Income": 17,
                "Unlisted Alternatives": 7,
                "TOTAL INVESTMENT ITEMS": 1,
            }
        ),
        5,
    ),
    (
        CONSERVATIVE_PATH,
        "HC Conservative - Class A Option",
        3308,
        Counter({"value_only": 3249, "name_only": 34, "ownership_only": 14, "aggregate_total": 11}),
        Counter(
            {
                "Listed Equity": 3118,
                "Cash": 75,
                "Unlisted Equity": 46,
                "Unlisted Property": 24,
                "Unlisted Infrastructure": 20,
                "Fixed Income": 17,
                "Unlisted Alternatives": 7,
                "TOTAL INVESTMENT ITEMS": 1,
            }
        ),
        5,
    ),
    (
        DEFENSIVE_PATH,
        "HC Defensive - Class A Option",
        3274,
        Counter({"value_only": 3120, "name_only": 132, "ownership_only": 12, "aggregate_total": 10}),
        Counter(
            {
                "Listed Equity": 3118,
                "Cash": 75,
                "Unlisted Property": 24,
                "Unlisted Infrastructure": 20,
                "Fixed Income": 17,
                "Unlisted Equity": 12,
                "Unlisted Alternatives": 7,
                "TOTAL INVESTMENT ITEMS": 1,
            }
        ),
        5,
    ),
    (
        GROWTH_PATH,
        "HC Growth - Class A Option",
        3285,
        Counter({"value_only": 3230, "name_only": 30, "ownership_only": 14, "aggregate_total": 11}),
        Counter(
            {
                "Listed Equity": 3118,
                "Cash": 57,
                "Unlisted Equity": 46,
                "Unlisted Property": 24,
                "Unlisted Infrastructure": 20,
                "Fixed Income": 12,
                "Unlisted Alternatives": 7,
                "TOTAL INVESTMENT ITEMS": 1,
            }
        ),
        5,
    ),
    (
        STABLE_PATH,
        "HC Stable - Class A Option",
        3308,
        Counter({"value_only": 3246, "name_only": 37, "ownership_only": 14, "aggregate_total": 11}),
        Counter(
            {
                "Listed Equity": 3118,
                "Cash": 75,
                "Unlisted Equity": 46,
                "Unlisted Property": 24,
                "Unlisted Infrastructure": 20,
                "Fixed Income": 17,
                "Unlisted Alternatives": 7,
                "TOTAL INVESTMENT ITEMS": 1,
            }
        ),
        5,
    ),
    (
        SRI_BALANCED_PATH,
        "HC SRI - Class A Option",
        597,
        Counter({"value_only": 584, "aggregate_total": 9, "ownership_only": 4}),
        Counter(
            {
                "Listed Equity": 536,
                "Cash": 36,
                "Unlisted Equity": 9,
                "Unlisted Infrastructure": 9,
                "Fixed Income": 2,
                "Unlisted Property": 2,
                "Unlisted Alternatives": 2,
                "TOTAL INVESTMENT ITEMS": 1,
            }
        ),
        0,
    ),
    (
        SRI_DEFENSIVE_PATH,
        "HC SRI Defensive - Class A Option",
        588,
        Counter({"value_only": 574, "aggregate_total": 8, "ownership_only": 4, "name_only": 2}),
        Counter(
            {
                "Listed Equity": 536,
                "Cash": 36,
                "Unlisted Infrastructure": 9,
                "Fixed Income": 2,
                "Unlisted Property": 2,
                "Unlisted Alternatives": 2,
                "TOTAL INVESTMENT ITEMS": 1,
            }
        ),
        0,
    ),
)


def make_metadata(source_file_id: str = "fixture-hostplus") -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id=source_file_id,
        fund_id="hostplus",
        suspected_adapter_key="HostPlusPhdStateMachineAdapter",
        reporting_period_id=1,
        source_url=str(EXTRACT_FIXTURE_PATH),
        checksum="fixture-hostplus",
        received_at=datetime(2026, 4, 19, 0, 0, 0),
        reporting_period_end_date=date(2025, 12, 31),
    )


def mutate_extract(mutator) -> bytes:
    with EXTRACT_FIXTURE_PATH.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        rows = list(csv.reader(handle))
    mutator(rows)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    return output.getvalue().encode("utf-8")


class TestHostPlusAdapterRealExtract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = HostPlusPhdStateMachineAdapter()
        cls.result = cls.adapter.parse(make_metadata(), EXTRACT_FIXTURE_PATH.read_bytes())
        cls.rows = {record.source_row_number: record for record in cls.result.holdings}

    def test_content_signal_verification_requires_hostplus_marker(self) -> None:
        mutated = mutate_extract(lambda rows: rows.__setitem__(1, ["NOTHOSTPLUS", "", "", "", ""]))
        with self.assertRaises(HostPlusFileIdentityError) as ctx:
            self.adapter.parse(make_metadata("fixture-hostplus-missing-marker"), mutated)
        self.assertIn("HOSTPLUS", str(ctx.exception))

    def test_unknown_blank_table_1_section_does_not_emit_under_prior_section(self) -> None:
        mutated = mutate_extract(lambda rows: rows.insert(7, ["Mystery Private Bucket", "", "", "", ""]))
        with self.assertRaises(HostPlusUnknownSectionError):
            self.adapter.parse(make_metadata("fixture-hostplus-unknown-table1-section"), mutated)

    def test_single_option_recognition_matches_extract_readme(self) -> None:
        self.assertEqual(["HC High Growth - Class A Option"], self.result.structural_metadata["observed_option_names"])
        self.assertEqual(["HOSTPLUS_HC_HIGH_GROWTH_CLASS_A_OPTION"], self.result.structural_metadata["observed_options"])
        self.assertEqual(1, self.result.structural_metadata["options_processed"])

    def test_table_2_3_4_rows_are_excluded_and_counted(self) -> None:
        self.assertEqual({"2": 5, "3": 7, "4": 4}, self.result.structural_metadata["table_rows_excluded"])
        self.assertNotIn("Swaps", [record.raw_name for record in self.result.holdings])
        self.assertNotIn("AUD", [record.raw_name for record in self.result.holdings if record.source_asset_class_raw == "DERIVATIVES"])

    def test_replacement_count_is_logged_from_real_file(self) -> None:
        self.assertEqual(3, self.result.structural_metadata["encoding_replacement_count"])
        self.assertEqual(
            ["Decoded Host-Plus source using UTF-8 errors='replace'; replacement_count=3"],
            self.result.adapter_warnings,
        )

    def test_column_header_re_emission_interprets_cash_listed_equity_and_ownership_rows_differently(self) -> None:
        cash_row = self.rows[9]
        listed_equity_row = self.rows[60]
        ownership_row = self.rows[3183]

        self.assertEqual("Citigroup Inc", cash_row.raw_name)
        self.assertEqual("AUD", cash_row.currency_raw)
        self.assertIsNone(cash_row.security_identifier_value)
        self.assertEqual(Decimal("28837447"), cash_row.value_aud)

        self.assertEqual("360 SECURITY TECHNOLOGY IN-A", listed_equity_row.raw_name)
        self.assertEqual("CNE100002RZ2", listed_equity_row.security_identifier_value)
        self.assertEqual("ISIN", listed_equity_row.security_identifier_type)
        self.assertEqual(Decimal("-37.42"), listed_equity_row.units)
        self.assertEqual(Decimal("-90"), listed_equity_row.value_aud)

        self.assertEqual("Myriota Pty Ltd", ownership_row.raw_name)
        self.assertIsNone(ownership_row.currency_raw)
        self.assertIsNone(ownership_row.security_identifier_value)
        self.assertEqual(Decimal("0.0526"), ownership_row.ownership_pct)
        self.assertEqual("ownership_only", ownership_row.disclosure_completeness)

    def test_registered_reporting_period_is_used_for_emitted_rows(self) -> None:
        self.assertEqual(date(2025, 12, 31), self.rows[9].reporting_period_date)

    def test_hostplus_gold_seam_rows(self) -> None:
        myriota = self.rows[3183]
        industry_super_holdings = self.rows[3184]
        ifm = self.rows[3209]

        self.assertEqual(Decimal("0.0526"), myriota.ownership_pct)
        self.assertIsNone(myriota.value_aud)
        self.assertEqual("ownership_only", myriota.disclosure_completeness)

        self.assertEqual(Decimal("0.1317"), industry_super_holdings.ownership_pct)
        self.assertIsNone(industry_super_holdings.value_aud)
        self.assertEqual("ownership_only", industry_super_holdings.disclosure_completeness)

        self.assertIsNone(ifm.ownership_pct)
        self.assertEqual(Decimal("4642022"), ifm.value_aud)
        self.assertEqual("value_only", ifm.disclosure_completeness)

    def test_listed_equity_units_without_value_stays_name_only(self) -> None:
        row = self.rows[73]
        self.assertEqual("ABIOMED INC-CVR", row.raw_name)
        self.assertEqual(Decimal("-0.48"), row.units)
        self.assertIsNone(row.value_aud)
        self.assertEqual("name_only", row.disclosure_completeness)

    def test_cash_multi_currency_emits_one_row_per_currency(self) -> None:
        rows = [row for row in self.result.holdings if row.raw_name == "Citigroup Inc"]
        self.assertEqual(38, len(rows))
        self.assertEqual(38, len({row.currency_raw for row in rows}))
        self.assertEqual({"AUD", "USD", "EUR"}, {row.currency_raw for row in rows if row.currency_raw in {"AUD", "USD", "EUR"}})

    def test_total_rows_emit_as_aggregate_totals(self) -> None:
        section_total = self.rows[57]
        investment_total = self.rows[3234]

        self.assertTrue(section_total.is_aggregate)
        self.assertEqual("aggregate_total", section_total.disclosure_completeness)
        self.assertEqual("TOTAL", section_total.raw_name)

        self.assertTrue(investment_total.is_aggregate)
        self.assertEqual("aggregate_total", investment_total.disclosure_completeness)
        self.assertEqual("TOTAL INVESTMENT ITEMS", investment_total.raw_name)

    def test_real_file_scope_modifier_scan_finds_single_variant(self) -> None:
        variants: dict[str, int] = {}
        with REAL_FIXTURE_PATH.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            for row in csv.reader(handle):
                first = row[0].strip().replace("\xa0", " ")
                if first.startswith("Held directly"):
                    variants[first] = variants.get(first, 0) + 1
        self.assertEqual({"Held directly or by associated entities or by PSTs": 2}, variants)

    def test_latest_period_mapping_only_batch_parses_without_parser_changes(self) -> None:
        for fixture_path, option_name, expected_rows, expected_completeness in LATEST_PERIOD_BATCH_CASES:
            with self.subTest(option=option_name):
                result = self.adapter.parse(make_metadata(fixture_path.name), fixture_path.read_bytes())

                self.assertEqual([option_name], result.structural_metadata["observed_option_names"])
                self.assertEqual(expected_rows, len(result.holdings))
                self.assertEqual({"2": 5, "3": 7, "4": 4}, result.structural_metadata["table_rows_excluded"])
                self.assertEqual(16, sum(result.structural_metadata["table_rows_excluded"].values()))
                self.assertEqual(3, result.structural_metadata["encoding_replacement_count"])
                self.assertEqual(expected_completeness, Counter(record.disclosure_completeness for record in result.holdings))
                self.assertNotIn("Fixed Income", result.structural_metadata["observed_asset_classes"])
                self.assertNotIn("Unlisted Property", result.structural_metadata["observed_asset_classes"])
                self.assertNotIn("Unlisted Infrastructure", result.structural_metadata["observed_asset_classes"])
                self.assertFalse(
                    any(
                        record.source_asset_class_raw in {"Fixed Income", "Unlisted Property", "Unlisted Infrastructure"}
                        for record in result.holdings
                    )
                )
                self.assertFalse(
                    any(record.raw_name in {"Forwards", "Futures", "Swaps", "AUD"} for record in result.holdings)
                )

    def test_core_diversified_batch_recognises_private_market_sections_explicitly(self) -> None:
        expected_private_sections = {"Fixed Income", "Unlisted Property", "Unlisted Infrastructure"}
        section_label_names = {
            "Fixed Income",
            "Unlisted Property",
            "Unlisted Infrastructure",
            "Unlisted Alternatives",
        }
        for (
            fixture_path,
            option_name,
            expected_rows,
            expected_completeness,
            expected_asset_counts,
            expected_address_rows,
        ) in CORE_DIVERSIFIED_BATCH_CASES:
            with self.subTest(option=option_name):
                result = self.adapter.parse(make_metadata(fixture_path.name), fixture_path.read_bytes())

                self.assertEqual([option_name], result.structural_metadata["observed_option_names"])
                self.assertEqual(expected_rows, len(result.holdings))
                self.assertEqual({"2": 5, "3": 7, "4": 4}, result.structural_metadata["table_rows_excluded"])
                self.assertEqual(16, sum(result.structural_metadata["table_rows_excluded"].values()))
                self.assertEqual(3, result.structural_metadata["encoding_replacement_count"])
                self.assertTrue(expected_private_sections.issubset(result.structural_metadata["observed_asset_classes"]))
                self.assertEqual(expected_completeness, Counter(record.disclosure_completeness for record in result.holdings))
                self.assertEqual(expected_asset_counts, Counter(record.source_asset_class_raw for record in result.holdings))
                self.assertEqual(expected_address_rows, sum(1 for record in result.holdings if record.address_raw))
                self.assertFalse(any(record.raw_name in section_label_names for record in result.holdings))
                self.assertFalse(
                    any(record.raw_name in {"Forwards", "Futures", "Swaps", "AUD"} for record in result.holdings)
                )
                for record in result.holdings:
                    if record.address_raw:
                        self.assertEqual("Unlisted Property", record.source_asset_class_raw)
                        self.assertIsNone(record.geo_lat)
                        self.assertIsNone(record.geo_lng)
