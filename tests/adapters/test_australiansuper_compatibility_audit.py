from __future__ import annotations

import csv
from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import unittest

from adapters.base import SourceFileMetadata
from adapters.sunsuper_schema import SunsuperSchemaPhdAdapter
from adapters.sunsuper_schema_errors import HeaderMismatchError
from adapters.sunsuper_schema_identity import (
    AUSTRALIANSUPER_REAL_HEADER,
    assess_shared_schema_fund_identity,
    validate_declared_fund_identity,
)
from adapters.sunsuper_schema_mapping import EXPECTED_HEADER


AUSTRALIANSUPER_FIXTURE_DIR = Path("tests/fixtures/real/australiansuper").resolve()
STABLE_PATH = AUSTRALIANSUPER_FIXTURE_DIR / "Stable PHD (1).csv"
SOCIALLY_AWARE_PATH = AUSTRALIANSUPER_FIXTURE_DIR / "Socially Aware PHD.csv"
MEMBER_DIRECT_PATH = AUSTRALIANSUPER_FIXTURE_DIR / "Member Direct PHD (1).csv"
CONSERVATIVE_PATH = AUSTRALIANSUPER_FIXTURE_DIR / "Conservative PHD (1).csv"
ART_SYNTHETIC_PATH = Path("tests/fixtures/art_sunsuper_synthetic_stable_minimal.csv").resolve()


def make_metadata(file_path: Path, *, fund_id: str = "australiansuper") -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id=file_path.name,
        fund_id=fund_id,
        suspected_adapter_key="SunsuperSchemaPhdAdapter",
        reporting_period_id=1,
        source_url=str(file_path),
        checksum=file_path.name,
        received_at=datetime(2026, 4, 19, 0, 0, 0),
        reporting_period_end_date=date(2025, 12, 31),
    )


def read_rows(file_path: Path) -> list[dict[str, str]]:
    return list(csv.DictReader(file_path.read_text(encoding="utf-8", errors="replace").splitlines()))


class TestAustralianSuperCompatibilityAudit(unittest.TestCase):
    def test_real_files_use_a_different_24_column_header_variant(self) -> None:
        with STABLE_PATH.open("r", encoding="utf-8", errors="replace", newline="") as handle:
            header = next(csv.reader(handle))

        self.assertEqual(24, len(header))
        self.assertEqual(AUSTRALIANSUPER_REAL_HEADER, header)
        self.assertEqual(24, len(EXPECTED_HEADER))
        self.assertNotEqual(EXPECTED_HEADER, header)

    def test_current_shared_adapter_rejects_real_australiansuper_file_as_is(self) -> None:
        with self.assertRaises(HeaderMismatchError):
            SunsuperSchemaPhdAdapter().parse(make_metadata(STABLE_PATH), STABLE_PATH.read_bytes())

    def test_real_files_prove_thin_wrapper_is_needed_not_just_fund_config(self) -> None:
        rows = read_rows(STABLE_PATH)
        ownership_values = [
            Decimal(row["% Ownership"])
            for row in rows
            if row["% Ownership"].strip() not in {"", " ", "nan"}
        ]

        self.assertTrue(any(row["Sub-Filter"].strip() == "Externally Managed" for row in rows))
        self.assertTrue(any(row["Name Type"].strip() == "Total" for row in rows))
        self.assertTrue(
            any(
                row["Asset Class"].strip() == "Derivatives" and row["Filter"].strip() == "By Asset Class"
                for row in rows
            )
        )
        self.assertGreater(max(ownership_values), Decimal("1"))
        self.assertTrue(any(row["Weighting (%)"].strip() == "1.41" for row in rows))

    def test_stable_file_shares_the_duplicate_view_pattern_with_art_merge_logic(self) -> None:
        rows_by_number = {index: row for index, row in enumerate(read_rows(STABLE_PATH), start=2)}

        precise_row = rows_by_number[3420]
        metadata_row = rows_by_number[3999]

        self.assertEqual("IFM Investors", precise_row["Name"])
        self.assertEqual("Infrastructure", precise_row["Asset Class"])
        self.assertEqual("Unlisted", precise_row["Filter"])
        self.assertEqual("Externally Managed", precise_row["Sub-Filter"])
        self.assertEqual("216358991.0", precise_row["$ Value"])

        self.assertEqual("IFM Investors", metadata_row["Name"])
        self.assertEqual("Infrastructure", metadata_row["Asset Class"])
        self.assertEqual("Unlisted", metadata_row["Filter"])
        self.assertEqual("All Assets", metadata_row["Sub-Filter"])
        self.assertEqual("", metadata_row["$ Value"])
        self.assertEqual("$100m to $300m", metadata_row["Value Range"])

    def test_identity_assessment_uses_source_and_content_signals_not_ar_prefixes(self) -> None:
        australian_super_assessment = assess_shared_schema_fund_identity(
            source_url=str(STABLE_PATH),
            option_names={"Stable"},
            header=AUSTRALIANSUPER_REAL_HEADER,
        )
        ambiguous_assessment = assess_shared_schema_fund_identity(
            source_url="/tmp/Stable PHD.csv",
            option_names={"Stable"},
            header=AUSTRALIANSUPER_REAL_HEADER,
        )
        art_assessment = assess_shared_schema_fund_identity(
            source_url=str(ART_SYNTHETIC_PATH),
            option_names={"ART Stable"},
            header=EXPECTED_HEADER,
        )

        self.assertEqual("australiansuper", australian_super_assessment.probable_fund_code)
        self.assertEqual("high", australian_super_assessment.confidence)
        self.assertIn(
            "source path contains explicit AustralianSuper branding",
            australian_super_assessment.reasons,
        )
        self.assertEqual([], validate_declared_fund_identity(declared_fund_code="australiansuper", assessment=australian_super_assessment))

        self.assertIsNone(ambiguous_assessment.probable_fund_code)
        self.assertEqual("unknown", ambiguous_assessment.confidence)
        self.assertEqual(
            [
                "Unable to verify declared fund 'australiansuper' from non-option-code signals for the shared 24-column schema"
            ],
            validate_declared_fund_identity(declared_fund_code="australiansuper", assessment=ambiguous_assessment),
        )

        self.assertEqual("art", art_assessment.probable_fund_code)
        self.assertEqual([], validate_declared_fund_identity(declared_fund_code="art", assessment=art_assessment))

    def test_real_fixture_set_covers_multiple_australiansuper_option_shapes(self) -> None:
        stable_rows = read_rows(STABLE_PATH)
        socially_aware_rows = read_rows(SOCIALLY_AWARE_PATH)
        member_direct_rows = read_rows(MEMBER_DIRECT_PATH)
        conservative_rows = read_rows(CONSERVATIVE_PATH)

        self.assertEqual({"ARST"}, {row["Option Code"] for row in stable_rows})
        self.assertEqual({"ARSB"}, {row["Option Code"] for row in socially_aware_rows})
        self.assertEqual({"AR2O"}, {row["Option Code"] for row in member_direct_rows})
        self.assertEqual({"ARYO"}, {row["Option Code"] for row in conservative_rows})

        self.assertTrue(any(row["Classification"].strip() for row in stable_rows if row["Classification"].strip().lower() != "nan"))
        self.assertTrue(any(row["Geo Latitude"].strip().lower() not in {"", "nan"} for row in stable_rows))
        self.assertFalse(any(row["Classification"].strip() and row["Classification"].strip().lower() != "nan" for row in member_direct_rows))

