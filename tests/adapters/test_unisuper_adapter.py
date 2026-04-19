from __future__ import annotations

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
