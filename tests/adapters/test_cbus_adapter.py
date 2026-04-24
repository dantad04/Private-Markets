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


if __name__ == "__main__":
    unittest.main()
