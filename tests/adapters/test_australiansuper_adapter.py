from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import unittest

from adapters.australiansuper import AustralianSuperPhdAdapter
from adapters.base import SourceFileMetadata


AUSTRALIANSUPER_FIXTURE_DIR = Path("tests/fixtures/real/australiansuper").resolve()
STABLE_PATH = AUSTRALIANSUPER_FIXTURE_DIR / "Stable PHD (1).csv"
MEMBER_DIRECT_PATH = AUSTRALIANSUPER_FIXTURE_DIR / "Member Direct PHD (1).csv"


def make_metadata(
    file_path: Path,
    *,
    source_url: str | None = None,
    fund_code: str = "australiansuper",
) -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id=file_path.name,
        fund_id=fund_code,
        fund_code=fund_code,
        suspected_adapter_key="AustralianSuperPhdAdapter",
        reporting_period_id=1,
        source_url=source_url or str(file_path),
        checksum=file_path.name,
        received_at=datetime(2026, 4, 19, 0, 0, 0),
        reporting_period_end_date=date(2025, 12, 31),
    )


class TestAustralianSuperAdapter(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = AustralianSuperPhdAdapter()

    def test_member_direct_file_parses_as_verified_clean_slice(self) -> None:
        result = self.adapter.parse(make_metadata(MEMBER_DIRECT_PATH), MEMBER_DIRECT_PATH.read_bytes())

        self.assertEqual([], result.adapter_warnings)
        self.assertEqual([], result.structural_metadata["review_queue_events"])
        self.assertEqual("australiansuper", result.structural_metadata["fund_identity_assessment"]["probable_fund_code"])
        self.assertEqual("high", result.structural_metadata["fund_identity_assessment"]["confidence"])
        self.assertEqual(564, len(result.holdings))
        self.assertEqual(7, sum(1 for record in result.holdings if record.is_aggregate))

    def test_member_direct_option_name_can_verify_identity_without_path_signal(self) -> None:
        result = self.adapter.parse(
            make_metadata(MEMBER_DIRECT_PATH, source_url="/tmp/member-direct-local-copy.csv"),
            MEMBER_DIRECT_PATH.read_bytes(),
        )

        self.assertEqual([], result.adapter_warnings)
        self.assertEqual("australiansuper", result.structural_metadata["fund_identity_assessment"]["probable_fund_code"])
        self.assertEqual("medium", result.structural_metadata["fund_identity_assessment"]["confidence"])
        self.assertIn(
            "option names include AustralianSuper-specific products: 'member direct'",
            result.structural_metadata["fund_identity_assessment"]["reasons"],
        )

    def test_stable_file_merges_precise_value_row_with_metadata_row(self) -> None:
        result = self.adapter.parse(make_metadata(STABLE_PATH), STABLE_PATH.read_bytes())

        row = next(record for record in result.holdings if record.source_row_number == 3420)
        self.assertEqual("IFM Investors", row.raw_name)
        self.assertEqual("Unlisted Infrastructure", row.source_asset_class_raw)
        self.assertEqual("Externally Managed", row.source_subclass_raw)
        self.assertEqual(Decimal("216358991.0"), row.value_aud)
        self.assertEqual("$100m to $300m", row.value_band_raw)
        self.assertEqual([3999], row.metadata_attached_from_row_numbers)
        self.assertEqual([3420, 3999], [entry["source_row_number"] for entry in row.raw_payload_json])

    def test_stable_file_attaches_metadata_to_ownership_only_row(self) -> None:
        result = self.adapter.parse(make_metadata(STABLE_PATH), STABLE_PATH.read_bytes())

        row = next(record for record in result.holdings if record.source_row_number == 3386)
        self.assertEqual("Ausgrid", row.raw_name)
        self.assertEqual("ownership_only", row.disclosure_completeness)
        self.assertEqual(Decimal("0.001"), row.ownership_pct)
        self.assertEqual("Electricity", row.classification_raw)
        self.assertEqual("$10m to $50m", row.value_band_raw)
        self.assertEqual([3988], row.metadata_attached_from_row_numbers)
        self.assertEqual([3386, 3988], [entry["source_row_number"] for entry in row.raw_payload_json])

    def test_stable_file_skips_derivative_posture_rows_and_emits_totals(self) -> None:
        result = self.adapter.parse(make_metadata(STABLE_PATH), STABLE_PATH.read_bytes())

        self.assertEqual(17, result.parse_statistics["skipped_portfolio_posture_rows"])
        self.assertFalse(any(record.source_asset_class_raw == "Derivatives" for record in result.holdings))

        aggregate_row = next(record for record in result.holdings if record.source_row_number == 1128)
        self.assertTrue(aggregate_row.is_aggregate)
        self.assertEqual("aggregate_total", aggregate_row.disclosure_completeness)
        self.assertEqual("Fixed Income", aggregate_row.source_asset_class_raw)
        self.assertEqual("Externally Managed", aggregate_row.source_subclass_raw)
        self.assertEqual(Decimal("1257501675.0"), aggregate_row.value_aud)
        self.assertEqual(Decimal("0.2644"), aggregate_row.weighting_pct)

    def test_stable_file_preserves_ambiguous_value_rows_for_review(self) -> None:
        result = self.adapter.parse(make_metadata(STABLE_PATH), STABLE_PATH.read_bytes())

        nbn_rows = [record for record in result.holdings if record.raw_name == "NBN Co Ltd"]
        self.assertEqual(4, len(nbn_rows))
        self.assertEqual({764, 968, 1076, 1077}, {record.source_row_number for record in nbn_rows})

        review_event = next(
            event
            for event in result.structural_metadata["review_queue_events"]
            if event["review_reason"] == "ambiguous_duplicate_group"
            and event["details"].get("group_key", {}).get("raw_name") == "NBN Co Ltd"
        )
        self.assertEqual("multiple_precise_rows_within_group", review_event["details"]["reason"])
        self.assertEqual([764, 968, 1076, 1077], review_event["details"]["source_row_numbers"])
