from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import unittest

from adapters.art_sunsuper import ArtSunsuperPhdAdapter
from adapters.base import SourceFileMetadata


FIXTURE_PATH = Path("tests/fixtures/art_sunsuper_synthetic_stable_minimal.csv").resolve()


def make_metadata(source_file_id: str = "fixture-art-sunsuper") -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id=source_file_id,
        fund_id="art",
        suspected_adapter_key="ArtSunsuperPhdAdapter",
        reporting_period_id=1,
        source_url=str(FIXTURE_PATH),
        checksum="fixture-art-sunsuper",
        received_at=datetime(2026, 4, 19, 0, 0, 0),
        reporting_period_end_date=date(2025, 12, 31),
    )


class TestArtSunsuperAdapterSyntheticFixture(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = ArtSunsuperPhdAdapter()
        cls.result = cls.adapter.parse(make_metadata(), FIXTURE_PATH.read_bytes())
        cls.rows = {record.source_row_number: record for record in cls.result.holdings}

    def test_legacy_synthetic_fixture_reports_shape_lineage_without_source_domain_evidence(self) -> None:
        self.assertEqual(["ARST"], self.result.structural_metadata["observed_options"])
        self.assertEqual(["2025-12-31"], self.result.structural_metadata["observed_reporting_dates"])
        self.assertEqual(
            "Australian Retirement Trust / Sunsuper lineage",
            self.result.structural_metadata["known_option_family_owner"],
        )
        identity_assessment = self.result.structural_metadata["fund_identity_assessment"]
        self.assertIsNone(identity_assessment["source_domain"])
        self.assertIn(
            "source path contains explicit ART/Sunsuper branding",
            identity_assessment["reasons"],
        )
        self.assertNotIn(
            "source domain 'files.australianretirementtrust.com.au' matches Australian Retirement Trust branding",
            identity_assessment["reasons"],
        )

    def test_single_source_case_has_single_tagged_raw_payload_entry(self) -> None:
        row = self.rows[4]
        self.assertEqual("Transurban Finance Company", row.raw_name)
        self.assertEqual([], row.metadata_attached_from_row_numbers)
        self.assertEqual("fully_disclosed", row.disclosure_completeness)
        self.assertEqual(
            [
                {
                    "source_row_number": 4,
                    "payload": [
                        "ARST",
                        "ART Stable",
                        "All Assets",
                        "Listed Infrastructure",
                        "Asset",
                        "Transurban Finance Company",
                        "AU000000TCL6",
                        "AUD",
                        "100000",
                        "25000000",
                        "n/a",
                        "0.01",
                        "n/a",
                        "Toll Road",
                        "Tower 5, 727 Collins Street, Docklands VIC 3008",
                        "Australia",
                        "-37.8140",
                        "144.9465",
                        "Externally Managed",
                        "n/a",
                        "n/a",
                        "Australia",
                        "n/a",
                        "All Assets Slice",
                    ],
                }
            ],
            row.raw_payload_json,
        )

    def test_metadata_attachment_case_merges_precise_and_metadata_rows(self) -> None:
        row = self.rows[2]
        self.assertEqual("IFM Investors Pty Ltd", row.raw_name)
        self.assertEqual("fixed_income", row.canonical_asset_class_code)
        self.assertEqual("value_only", row.disclosure_completeness)
        self.assertEqual(Decimal("339726831"), row.value_aud)
        self.assertEqual("$100m to $300m", row.value_band_raw)
        self.assertEqual("Debt Manager", row.classification_raw)
        self.assertEqual("Level 15, 20 Bond Street, Sydney NSW 2000", row.address_raw)
        self.assertEqual("Australia", row.location_raw)
        self.assertEqual(Decimal("-33.8644"), row.geo_lat)
        self.assertEqual(Decimal("151.2088"), row.geo_lng)
        self.assertEqual([3], row.metadata_attached_from_row_numbers)
        self.assertEqual([2, 3], [entry["source_row_number"] for entry in row.raw_payload_json])

    def test_ambiguity_case_emits_separate_rows_and_one_review_event(self) -> None:
        ambiguous_bytes = FIXTURE_PATH.read_bytes() + (
            b"\nARST,ART Stable,Externally Managed,Listed Infrastructure,Manager,IFM Investors Pty Ltd,n/a,AUD,n/a,5000000,n/a,0.01,n/a,n/a,n/a,Australia,n/a,n/a,Externally Managed,n/a,IFM Investors Pty Ltd,Australia,n/a,Management Slice\n"
        )
        result = self.adapter.parse(make_metadata("fixture-art-sunsuper-ambiguous"), ambiguous_bytes)

        ifm_rows = [record for record in result.holdings if record.raw_name == "IFM Investors Pty Ltd"]
        self.assertEqual(2, len(ifm_rows))
        self.assertEqual(
            {"Fixed Income", "Listed Infrastructure"},
            {row.source_asset_class_raw for row in ifm_rows},
        )
        review_events = result.structural_metadata["review_queue_events"]
        self.assertEqual(1, len(review_events))
        self.assertEqual("ambiguous_duplicate_group", review_events[0]["review_reason"])
        self.assertEqual([2, 9], review_events[0]["details"]["source_row_numbers"])

    def test_posture_exclusion_case_skips_derivatives_and_reports_count(self) -> None:
        self.assertEqual(1, self.result.structural_metadata["skipped_portfolio_posture_rows"])
        self.assertNotIn("Equity Futures", [record.raw_name for record in self.result.holdings])

    def test_ownership_decimal_case_keeps_decimal_fraction_as_is(self) -> None:
        row = self.rows[5]
        self.assertEqual("Industry Super Holdings Pty Ltd", row.raw_name)
        self.assertEqual("ownership_only", row.disclosure_completeness)
        self.assertEqual(Decimal("0.18"), row.ownership_pct)

    def test_value_band_raw_case_stays_name_only_without_exposure(self) -> None:
        row = self.rows[6]
        self.assertEqual("Delphi Ventures VIII, L.P.", row.raw_name)
        self.assertEqual("$25m to $50m", row.value_band_raw)
        self.assertIsNone(row.value_aud)
        self.assertEqual("name_only", row.disclosure_completeness)

    def test_tracks_utf8_replacement_count_when_decode_replaces_bytes(self) -> None:
        raw_bytes = FIXTURE_PATH.read_bytes().replace(b"Delphi Ventures VIII, L.P.", b"Delphi Ventur\xC0s VIII, L.P.", 1)
        result = self.adapter.parse(make_metadata("fixture-art-sunsuper-replacement"), raw_bytes)
        self.assertEqual(1, result.structural_metadata["encoding_replacement_count"])
        self.assertEqual(["UTF-8 replacement characters: 1"], result.adapter_warnings[:1])
        mutated_row = next(record for record in result.holdings if record.source_row_number == 6)
        self.assertIn("\ufffd", mutated_row.raw_name)
