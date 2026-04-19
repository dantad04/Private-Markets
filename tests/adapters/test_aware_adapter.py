from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
import unittest

from adapters.aware import AwarePhdAdapter
from adapters.base import SourceFileMetadata


FIXTURE_PATH = Path("tests/fixtures/aware_synthetic_table1_minimal.csv").resolve()


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
