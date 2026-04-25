from __future__ import annotations

from collections import Counter
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import csv
import io
import unittest

from adapters.base import SourceFileMetadata
from adapters.unisuper import UniSuperPhdStateMachineAdapter
from adapters.unisuper_errors import UniSuperFileIdentityError


REAL_FIXTURE_PATH = Path("tests/fixtures/real/UniSuper.csv").resolve()
EXTRACT_FIXTURE_PATH = Path("tests/fixtures/unisuper_real_extract.csv").resolve()
REAL_SHAPE_FINGERPRINT = "7dc5e32ce188c76fae55f3f4a1c0f09d79eb55ceb9c27a378cb905f222b31cb5"
FULL_SOURCE_OPTIONS = [
    "Conservative",
    "Conservative Balanced",
    "Balanced",
    "Sustainable Balanced",
    "Growth",
    "High Growth",
    "Sustainable High Growth",
    "Cash",
    "Australian Bond",
    "Australian Income",
    "Listed Property",
    "Australian Shares",
    "International Shares",
    "Global Environmental Opportunities",
    "Australian Dividend Income",
    "Global Companies in Asia",
]
FULL_SOURCE_OPTION_CODES = [
    "UNISUPER_CONSERVATIVE",
    "UNISUPER_CONSERVATIVE_BALANCED",
    "UNISUPER_BALANCED",
    "UNISUPER_SUSTAINABLE_BALANCED",
    "UNISUPER_GROWTH",
    "UNISUPER_HIGH_GROWTH",
    "UNISUPER_SUSTAINABLE_HIGH_GROWTH",
    "UNISUPER_CASH",
    "UNISUPER_AUSTRALIAN_BOND",
    "UNISUPER_AUSTRALIAN_INCOME",
    "UNISUPER_LISTED_PROPERTY",
    "UNISUPER_AUSTRALIAN_SHARES",
    "UNISUPER_INTERNATIONAL_SHARES",
    "UNISUPER_GLOBAL_ENVIRONMENTAL_OPPORTUNITIES",
    "UNISUPER_AUSTRALIAN_DIVIDEND_INCOME",
    "UNISUPER_GLOBAL_COMPANIES_IN_ASIA",
]
FULL_SOURCE_ROWS_BY_OPTION = {
    "Australian Bond": 29,
    "Australian Dividend Income": 54,
    "Australian Income": 144,
    "Australian Shares": 320,
    "Balanced": 3813,
    "Cash": 18,
    "Conservative": 3792,
    "Conservative Balanced": 3799,
    "Global Companies in Asia": 100,
    "Global Environmental Opportunities": 162,
    "Growth": 3799,
    "High Growth": 3606,
    "International Shares": 3313,
    "Listed Property": 373,
    "Sustainable Balanced": 1115,
    "Sustainable High Growth": 967,
}


def make_metadata(source_file_id: str = "fixture-unisuper") -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id=source_file_id,
        fund_id="unisuper",
        suspected_adapter_key="UniSuperPhdStateMachineAdapter",
        reporting_period_id=1,
        source_url=str(EXTRACT_FIXTURE_PATH),
        checksum="fixture-unisuper",
        received_at=datetime(2026, 4, 19, 0, 0, 0),
        reporting_period_end_date=date(2025, 12, 31),
    )


def make_real_file_metadata(source_file_id: str = "fixture-unisuper-full") -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id=source_file_id,
        fund_id="unisuper",
        suspected_adapter_key="UniSuperPhdStateMachineAdapter",
        reporting_period_id=1,
        source_url=str(REAL_FIXTURE_PATH),
        checksum="fixture-unisuper-full",
        received_at=datetime(2026, 4, 25, 0, 0, 0),
        reporting_period_end_date=date(2025, 12, 31),
    )


def mutate_extract(mutator) -> bytes:
    with EXTRACT_FIXTURE_PATH.open("r", encoding="cp1252", newline="") as handle:
        rows = list(csv.reader(handle))
    mutator(rows)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    return output.getvalue().encode("cp1252")


class TestUniSuperAdapterRealExtract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = UniSuperPhdStateMachineAdapter()
        cls.result = cls.adapter.parse(make_metadata(), EXTRACT_FIXTURE_PATH.read_bytes())
        cls.rows = {record.source_row_number: record for record in cls.result.holdings}

    def test_content_signal_verification_requires_schedule_marker(self) -> None:
        mutated = mutate_extract(lambda rows: rows.__setitem__(3, ["Schedule 8X", "", "", "", ""]))
        with self.assertRaises(UniSuperFileIdentityError) as ctx:
            self.adapter.parse(make_metadata("fixture-unisuper-missing-schedule"), mutated)
        self.assertIn("Schedule 8D", str(ctx.exception))

    def test_multi_option_recognition_matches_extract_readme(self) -> None:
        self.assertEqual(["Conservative", "Cash"], self.result.structural_metadata["observed_option_names"])
        self.assertEqual(2, self.result.structural_metadata["options_processed"])
        self.assertEqual(
            ["UNISUPER_CONSERVATIVE", "UNISUPER_CASH"],
            self.result.structural_metadata["observed_options"],
        )

    def test_table_2_3_4_rows_are_excluded_and_counted(self) -> None:
        self.assertEqual({"2": 12, "3": 14, "4": 8}, self.result.structural_metadata["table_rows_excluded"])
        self.assertNotIn("Swaps", [record.raw_name for record in self.result.holdings])
        self.assertNotIn("AUD", [record.raw_name for record in self.result.holdings if record.source_asset_class_raw == "DERIVATIVES"])

    def test_scope_modifier_normalisation_collapses_all_three_observed_variants(self) -> None:
        examples = self.result.structural_metadata["scope_variant_examples"]
        self.assertEqual(
            {
                "Held directly or by associated entities or by PSTs",
                "Held directly or by associated entity or by PSTs",
                "Held directly or by associated entities or PSTs",
            },
            set(examples.keys()),
        )
        canonical_values = {self.rows[row_number].classification_raw for row_number in examples.values()}
        self.assertEqual({"held_direct_or_associated_or_psts"}, canonical_values)

    def test_column_header_re_emission_interprets_cash_and_ownership_rows_differently(self) -> None:
        cash_row = self.rows[11]
        ownership_row = self.rows[3163]

        self.assertEqual("BNP PARIBAS SA (AUSTRALIA)", cash_row.raw_name)
        self.assertEqual("AUD", cash_row.currency_raw)
        self.assertIsNone(cash_row.ownership_pct)
        self.assertEqual("value_only", cash_row.disclosure_completeness)

        self.assertEqual("IFM INVESTORS PTY LIMITED", ownership_row.raw_name)
        self.assertIsNone(ownership_row.currency_raw)
        self.assertEqual(Decimal("0.309"), ownership_row.ownership_pct)
        self.assertEqual("ownership_only", ownership_row.disclosure_completeness)

    def test_us_date_parsing_uses_registered_reporting_period(self) -> None:
        self.assertEqual(["2025-12-31"], self.result.structural_metadata["observed_reporting_dates"])
        self.assertEqual(date(2025, 12, 31), self.rows[11].reporting_period_date)

    def test_ifm_investors_gold_seam_case(self) -> None:
        row = self.rows[3163]
        self.assertEqual("IFM INVESTORS PTY LIMITED", row.raw_name)
        self.assertEqual("UNLISTED EQUITY", row.source_asset_class_raw)
        self.assertEqual("Internally Managed", row.source_subclass_raw)
        self.assertEqual(Decimal("0.309"), row.ownership_pct)
        self.assertIsNone(row.value_aud)
        self.assertEqual("ownership_only", row.disclosure_completeness)

    def test_apax_europe_vi_lp_is_name_only(self) -> None:
        row = self.rows[3143]
        self.assertEqual("APAX EUROPE VI LP", row.raw_name)
        self.assertIsNone(row.ownership_pct)
        self.assertIsNone(row.value_aud)
        self.assertEqual("name_only", row.disclosure_completeness)

    def test_name_embedded_percentage_is_not_parsed_as_ownership(self) -> None:
        row = self.rows[3154]
        self.assertEqual("INDUSTRY SUPER HOLDINGS PTY LTD 7.5% MINORITY DISCOUNT", row.raw_name)
        self.assertIsNone(row.ownership_pct)
        self.assertIsNone(row.value_aud)
        self.assertEqual("name_only", row.disclosure_completeness)

    def test_cash_multi_currency_emits_one_row_per_currency(self) -> None:
        conservative_rows = [
            row
            for row in self.result.holdings
            if row.raw_name == "BNP PARIBAS SA (AUSTRALIA)" and row.source_option_name_raw == "Conservative"
        ]
        self.assertEqual(27, len(conservative_rows))
        self.assertEqual(27, len({row.currency_raw for row in conservative_rows}))
        self.assertEqual({"AUD", "EUR", "GBP", "USD"}, {row.currency_raw for row in conservative_rows if row.currency_raw in {"AUD", "EUR", "GBP", "USD"}})

    def test_total_rows_emit_as_aggregate_totals(self) -> None:
        row = self.rows[42]
        self.assertTrue(row.is_aggregate)
        self.assertEqual("aggregate_total", row.disclosure_completeness)
        self.assertEqual("TOTAL", row.raw_name)

    def test_quoted_name_with_embedded_comma_parses_as_one_field(self) -> None:
        row = self.rows[64]
        self.assertEqual("AUSTRALIA, COMMONWEALTH OF (GOVERNMENT)", row.raw_name)
        self.assertEqual(Decimal("98844707"), row.value_aud)
        self.assertEqual("value_only", row.disclosure_completeness)

    def test_additional_gold_seam_rows(self) -> None:
        amberside = self.rows[3142]
        partners_group = self.rows[3160]
        commonwealth_cash = self.rows[38]

        self.assertEqual(Decimal("0.29"), amberside.ownership_pct)
        self.assertEqual("ownership_only", amberside.disclosure_completeness)
        self.assertEqual(Decimal("0.99"), partners_group.ownership_pct)
        self.assertEqual("ownership_only", partners_group.disclosure_completeness)
        self.assertEqual(Decimal("472410359"), commonwealth_cash.value_aud)
        self.assertEqual("AUD", commonwealth_cash.currency_raw)
        self.assertEqual("value_only", commonwealth_cash.disclosure_completeness)

    def test_real_file_scope_modifier_scan_finds_exactly_three_variants(self) -> None:
        variants: dict[str, int] = {}
        with REAL_FIXTURE_PATH.open("r", encoding="cp1252", newline="") as handle:
            for row in csv.reader(handle):
                first = row[0].strip().replace("\xa0", " ")
                if first.startswith("Held directly"):
                    variants[first] = variants.get(first, 0) + 1
        self.assertEqual(
            {
                "Held directly or by associated entities or by PSTs": 112,
                "Held directly or by associated entity or by PSTs": 32,
                "Held directly or by associated entities or PSTs": 16,
            },
            variants,
        )


class TestUniSuperAdapterLatestPeriodFullSource(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = UniSuperPhdStateMachineAdapter()
        cls.result = cls.adapter.parse(make_real_file_metadata(), REAL_FIXTURE_PATH.read_bytes())

    def test_full_source_matches_approved_shape_and_reporting_period(self) -> None:
        self.assertEqual(REAL_SHAPE_FINGERPRINT, self.result.schema_fingerprint)
        self.assertEqual(["2025-12-31"], self.result.structural_metadata["observed_reporting_dates"])
        self.assertEqual(FULL_SOURCE_OPTIONS, self.result.structural_metadata["observed_option_names"])
        self.assertEqual(FULL_SOURCE_OPTION_CODES, self.result.structural_metadata["observed_options"])
        self.assertEqual(16, self.result.structural_metadata["options_processed"])
        self.assertEqual(
            ["Decoded UniSuper source using cp1252 fallback after UTF-8 decode failed"],
            self.result.adapter_warnings,
        )

    def test_full_source_table_1_counts_and_aggregates_match_preflight(self) -> None:
        self.assertEqual(25404, len(self.result.holdings))
        self.assertEqual(256, self.result.structural_metadata["aggregate_rows_emitted"])
        self.assertEqual(
            FULL_SOURCE_ROWS_BY_OPTION,
            self.result.structural_metadata["rows_emitted_by_option"],
        )
        self.assertEqual(
            Counter({"value_only": 24914, "aggregate_total": 256, "ownership_only": 149, "name_only": 85}),
            Counter(record.disclosure_completeness for record in self.result.holdings),
        )

    def test_full_source_tables_2_to_4_are_skipped(self) -> None:
        self.assertEqual({"2": 96, "3": 112, "4": 64}, self.result.structural_metadata["table_rows_excluded"])
        posture_names = {
            "Swaps",
            "Forwards",
            "Futures",
            "Options",
            "Other",
            "AUD",
            "USD",
            "Currencies of other developed markets",
            "Currencies of emerging markets",
        }
        self.assertFalse(any(record.raw_name in posture_names for record in self.result.holdings))
