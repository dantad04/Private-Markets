from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
import unittest

from adapters.art_qsuper import ArtQsuperPhdAdapter
from adapters.base import SourceFileMetadata


FIXTURE_PATH = Path("tests/fixtures/art_qsuper_synthetic_balanced_minimal.csv").resolve()


def make_metadata(source_file_id: str = "fixture-art-qsuper") -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id=source_file_id,
        fund_id="art",
        suspected_adapter_key="ArtQsuperPhdAdapter",
        reporting_period_id=None,
        source_url=str(FIXTURE_PATH),
        checksum="fixture-art-qsuper",
        received_at=datetime(2026, 4, 19, 0, 0, 0),
    )


class TestArtQsuperAdapterSyntheticFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = ArtQsuperPhdAdapter()
        cls.result = cls.adapter.parse(make_metadata(), FIXTURE_PATH.read_bytes())
        cls.rows = {record.source_row_number: record for record in cls.result.holdings}

    def test_extracts_single_option_and_textual_reporting_date(self) -> None:
        self.assertEqual(["ART Balanced"], self.result.structural_metadata["observed_options"])
        self.assertEqual(["31 December 2025"], self.result.structural_metadata["observed_reporting_dates"])
        self.assertEqual(["Externally Managed", "Internally Managed"], self.result.structural_metadata["observed_internal_external_values"])
        self.assertEqual(0, self.result.structural_metadata["encoding_replacement_count"])

    def test_skips_portfolio_posture_rows_but_keeps_them_in_structural_observations(self) -> None:
        self.assertEqual(8, self.result.structural_metadata["total_rows_emitted"])
        self.assertEqual(3, self.result.structural_metadata["skipped_portfolio_posture_rows"])
        self.assertEqual(
            {
                "aggregate_total": 2,
                "fully_disclosed": 1,
                "name_only": 1,
                "ownership_only": 2,
                "value_only": 2,
            },
            self.result.parse_statistics["disclosure_completeness_counts"],
        )
        self.assertIn("Derivatives By Kind", self.result.structural_metadata["observed_asset_classes"])
        self.assertIn("Derivatives By AssetClass", self.result.structural_metadata["observed_asset_classes"])
        self.assertIn("Derivatives By Currency", self.result.structural_metadata["observed_asset_classes"])

    def test_parses_fully_disclosed_listed_infrastructure_row(self) -> None:
        row = self.rows[4]
        self.assertEqual("ATLAS ARTERIA GROUP", row.raw_name)
        self.assertEqual("listed_infrastructure", row.canonical_asset_class_code)
        self.assertEqual("fully_disclosed", row.disclosure_completeness)
        self.assertEqual(Decimal("4250000"), row.value_aud)
        self.assertEqual(Decimal("1000000"), row.units)
        self.assertEqual("ISIN", row.security_identifier_type)

    def test_preserves_ownership_only_private_rows(self) -> None:
        equity_row = self.rows[5]
        property_row = self.rows[6]
        self.assertEqual("Industry Super Holdings Pty Ltd", equity_row.raw_name)
        self.assertEqual(Decimal("0.1432"), equity_row.ownership_pct)
        self.assertEqual("ownership_only", equity_row.disclosure_completeness)
        self.assertEqual("Queen Street Logistics Trust", property_row.raw_name)
        self.assertEqual("\"Queen Street Estate\", 1 Wharf Road, Brisbane QLD 4000", property_row.address_raw)
        self.assertEqual("Industrial", property_row.classification_raw)
        self.assertEqual("ownership_only", property_row.disclosure_completeness)

    def test_classifies_value_band_rows_as_name_only(self) -> None:
        row = self.rows[7]
        self.assertEqual("Blackbird Ventures Growth I", row.raw_name)
        self.assertEqual("$100m-$500m", row.value_band_raw)
        self.assertEqual("name_only", row.disclosure_completeness)
        self.assertEqual("Externally Managed", row.source_subclass_raw)

    def test_emits_aggregate_rows(self) -> None:
        cash_total = self.rows[8]
        file_total = self.rows[9]
        self.assertTrue(cash_total.is_aggregate)
        self.assertEqual("aggregate_total", cash_total.disclosure_completeness)
        self.assertEqual("cash", cash_total.canonical_asset_class_code)
        self.assertTrue(file_total.is_aggregate)
        self.assertEqual("multi_asset_other", file_total.canonical_asset_class_code)

    def test_tracks_utf8_replacement_count_when_decode_replaces_bytes(self) -> None:
        raw_bytes = FIXTURE_PATH.read_bytes().replace(b"Blackbird Ventures Growth I", b"Blackbird Ventur\xC0s Growth I", 1)
        result = self.adapter.parse(make_metadata("fixture-art-qsuper-replacement"), raw_bytes)
        self.assertEqual(1, result.structural_metadata["encoding_replacement_count"])
        self.assertEqual(["UTF-8 replacement characters: 1"], result.adapter_warnings)
        mutated_row = next(record for record in result.holdings if record.source_row_number == 7)
        self.assertIn("\ufffd", mutated_row.raw_name)
