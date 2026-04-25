from __future__ import annotations

from datetime import datetime
from decimal import Decimal
from pathlib import Path
import unittest

from adapters.australian_retirement_trust_real_16col import (
    AustralianRetirementTrustReal16ColumnPhdAdapter,
)
from adapters.australian_retirement_trust_real_16col_errors import (
    FundIdentityMismatchError,
    SchemaFingerprintMismatchError,
    SourceDomainMismatchError,
    UnapprovedReportingPeriodError,
)
from adapters.australian_retirement_trust_real_16col_mapping import (
    ADAPTER_KEY,
    APPROVED_SCHEMA_FINGERPRINT,
    APPROVED_TYPE_VALUES,
)
from adapters.base import SourceFileMetadata


FIXTURE_PATH = Path("tests/fixtures/australian_retirement_trust_real_16col_minimal.csv").resolve()
OFFICIAL_SOURCE_URL = (
    "https://files.australianretirementtrust.com.au/phd/super/diversified/"
    "Diversified_High_Growth_Superannuation.csv?v="
)


def make_metadata(
    *,
    source_file_id: str = "fixture-art-real-16col",
    fund_code: str | None = "art",
    source_url: str = OFFICIAL_SOURCE_URL,
) -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id=source_file_id,
        fund_id="art",
        suspected_adapter_key=ADAPTER_KEY,
        reporting_period_id=None,
        source_url=source_url,
        checksum="fixture-art-real-16col",
        received_at=datetime(2026, 4, 25, 0, 0, 0),
        fund_code=fund_code,
    )


class TestAustralianRetirementTrustReal16ColumnAdapter(unittest.TestCase):
    maxDiff = None

    @classmethod
    def setUpClass(cls) -> None:
        cls.adapter = AustralianRetirementTrustReal16ColumnPhdAdapter()
        cls.result = cls.adapter.parse(make_metadata(), FIXTURE_PATH.read_bytes())
        cls.rows = {record.source_row_number: record for record in cls.result.holdings}

    def test_uses_distinct_adapter_key_and_approved_schema_fingerprint(self) -> None:
        self.assertEqual(ADAPTER_KEY, self.adapter.adapter_key)
        self.assertEqual(APPROVED_SCHEMA_FINGERPRINT, self.result.schema_fingerprint)
        self.assertEqual(
            list(APPROVED_TYPE_VALUES),
            self.result.structural_metadata["observed_asset_classes"],
        )
        self.assertEqual(
            ["Diversified_High_Growth_Superannuation"],
            self.result.structural_metadata["observed_options"],
        )
        self.assertEqual(
            ["Diversified High Growth Superannuation"],
            self.result.structural_metadata["observed_option_names"],
        )
        self.assertEqual(["31 December 2025"], self.result.structural_metadata["observed_reporting_dates"])
        self.assertEqual(
            "official_art_phd_super_source_url",
            self.result.structural_metadata["source_domain_verification"],
        )

    def test_emits_option_name_without_synthesising_source_option_code(self) -> None:
        first = self.rows[2]
        self.assertIsNone(first.source_option_code)
        self.assertEqual("Diversified High Growth Superannuation", first.source_option_name_raw)

    def test_maps_all_approved_type_values_to_canonical_asset_classes(self) -> None:
        self.assertEqual(
            {
                "alternatives": 2,
                "cash": 2,
                "fixed_income": 4,
                "listed_equity": 2,
                "listed_infrastructure": 2,
                "listed_property": 2,
                "multi_asset_other": 2,
                "unlisted_equity": 5,
                "unlisted_infrastructure": 4,
                "unlisted_property": 2,
            },
            self.result.parse_statistics["canonical_asset_class_counts"],
        )

    def test_skips_derivative_posture_sections_and_counts_expected_rows(self) -> None:
        self.assertEqual(17, self.result.structural_metadata["skipped_portfolio_posture_rows"])
        self.assertEqual(
            {"Derivatives By AssetClass": 7, "Derivatives By Currency": 4, "Derivatives By Kind": 6},
            self.result.structural_metadata["skipped_portfolio_posture_rows_by_type"],
        )
        emitted_names = {record.raw_name for record in self.result.holdings}
        self.assertNotIn("SWAPS", emitted_names)
        self.assertNotIn("AUD", emitted_names)
        self.assertNotIn("EQUITIES", emitted_names)

    def test_emits_approved_aggregate_total_rows_only_for_non_derivative_totals(self) -> None:
        aggregate_rows = [record for record in self.result.holdings if record.is_aggregate]
        self.assertEqual(14, len(aggregate_rows))
        self.assertEqual({"aggregate_total": 14, "fully_disclosed": 3, "name_only": 1, "ownership_only": 2, "value_only": 7}, self.result.parse_statistics["disclosure_completeness_counts"])
        self.assertEqual(Decimal("120460561"), self.rows[3].value_aud)
        self.assertEqual("cash", self.rows[3].canonical_asset_class_code)
        self.assertEqual("aggregate_total", self.rows[3].disclosure_completeness)
        self.assertEqual("multi_asset_other", self.rows[27].canonical_asset_class_code)
        self.assertEqual("multi_asset_other", self.rows[45].canonical_asset_class_code)
        self.assertTrue(all(record.raw_name is None for record in aggregate_rows))

    def test_disclosure_completeness_and_normalisation_rules(self) -> None:
        listed_equity = self.rows[8]
        negative_value = self.rows[4]
        zero_ownership = self.rows[12]
        name_only = self.rows[13]

        self.assertEqual("fully_disclosed", listed_equity.disclosure_completeness)
        self.assertEqual("ASX_CODE", listed_equity.security_identifier_type)
        self.assertEqual(Decimal("5091038"), listed_equity.units)

        self.assertEqual("value_only", negative_value.disclosure_completeness)
        self.assertEqual(Decimal("-99270.00"), negative_value.value_aud)
        self.assertEqual(Decimal("-0.0001"), negative_value.weighting_pct)

        self.assertEqual("ownership_only", zero_ownership.disclosure_completeness)
        self.assertEqual(Decimal("0"), zero_ownership.ownership_pct)

        self.assertEqual("name_only", name_only.disclosure_completeness)
        self.assertEqual("FUTURE VEHICLE", name_only.raw_name)

    def test_preserves_source_row_provenance(self) -> None:
        row = self.rows[2]
        self.assertEqual(2, row.source_row_number)
        self.assertEqual(64, len(row.source_row_hash))
        self.assertEqual(
            [
                "31 December 2025",
                "Diversified_High_Growth_Superannuation",
                "Cash",
                "COMMONWEALTH BANK OF AUSTRALIA",
                "AUD",
                "n/a",
                "n/a",
                "n/a",
                "n/a",
                "$107,144,524",
                "1.27%",
                "",
                "",
                "",
                "",
                "",
            ],
            row.raw_payload_json,
        )

    def test_rejects_header_fingerprint_drift_even_when_decoded_header_matches(self) -> None:
        with self.assertRaises(SchemaFingerprintMismatchError):
            self.adapter.parse(make_metadata(source_file_id="bom-drift"), b"\xef\xbb\xbf" + FIXTURE_PATH.read_bytes())

    def test_rejects_unapproved_reporting_period(self) -> None:
        drifted = FIXTURE_PATH.read_text(encoding="utf-8").replace("31 December 2025", "30 June 2026")
        with self.assertRaises(UnapprovedReportingPeriodError):
            self.adapter.parse(make_metadata(source_file_id="period-drift"), drifted.encode("utf-8"))

    def test_rejects_non_art_http_source_domain_when_available(self) -> None:
        with self.assertRaises(SourceDomainMismatchError):
            self.adapter.parse(
                make_metadata(source_url="https://example.com/phd/super/Diversified_High_Growth_Superannuation.csv"),
                FIXTURE_PATH.read_bytes(),
            )

    def test_rejects_non_art_declared_fund_code(self) -> None:
        with self.assertRaises(FundIdentityMismatchError):
            self.adapter.parse(make_metadata(fund_code="australiansuper"), FIXTURE_PATH.read_bytes())
