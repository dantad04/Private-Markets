from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AdapterMappingVersion,
    Base,
    CanonicalAssetClass,
    Holding,
    ReportingPeriod,
    SchemaReviewQueue,
    SourceFile,
    TaxonomyMapping,
)
from app.db.session import get_engine
from app.ingest.governance import (
    AUSTRALIANSUPER_CONSERVATIVE_MAPPING_VERSION_ID,
    AUSTRALIANSUPER_MAPPING_VERSION_ID,
    AUSTRALIANSUPER_STABLE_MAPPING_VERSION_ID,
    SchemaDriftDetectedError,
)
from app.ingest.loader import ingest_australiansuper_local_file


FIXTURE_DIR = Path("tests/fixtures/real/australiansuper").resolve()
MEMBER_DIRECT_PATH = FIXTURE_DIR / "Member Direct PHD (1).csv"
STABLE_PATH = FIXTURE_DIR / "Stable PHD (1).csv"
CONSERVATIVE_PATH = FIXTURE_DIR / "Conservative PHD (1).csv"
SOCIALLY_AWARE_PATH = FIXTURE_DIR / "Socially Aware PHD.csv"


class TestAustralianSuperLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_australiansuper.db'}"
        self.engine = get_engine(self.database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tempdir.cleanup()

    def _create_reporting_period(self) -> int:
        with self.SessionLocal() as session:
            period = ReportingPeriod(
                period_end_date=date(2025, 12, 31),
                disclosure_due_date=date(2026, 3, 31),
                label="2025-12-31",
                source_cycle="semi_annual",
            )
            session.add(period)
            session.commit()
            return period.id

    def test_ingest_member_direct_official_file(self) -> None:
        reporting_period_id = self._create_reporting_period()

        with self.SessionLocal() as session:
            summary = ingest_australiansuper_local_file(
                session,
                fund_code="australiansuper",
                fund_name="AustralianSuper",
                file_path=str(MEMBER_DIRECT_PATH),
                reporting_period_id=reporting_period_id,
            )
            session.commit()

            self.assertEqual(564, summary.rows_staged)
            self.assertEqual(564, summary.rows_inserted)
            self.assertEqual(0, summary.rows_skipped_existing)

            source_file = session.get(SourceFile, summary.source_file_id)
            self.assertEqual("AustralianSuperPhdAdapter", source_file.adapter_key)
            self.assertEqual(AUSTRALIANSUPER_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(564, session.query(Holding).count())
            self.assertIsNotNone(session.get(AdapterMappingVersion, AUSTRALIANSUPER_MAPPING_VERSION_ID))
            self.assertGreater(session.query(TaxonomyMapping).count(), 0)
            self.assertEqual(0, session.query(SchemaReviewQueue).count())

            morella_row = session.scalar(
                select(Holding).where(
                    Holding.raw_name == "Morella Corporation Ltd",
                    Holding.source_file_id == summary.source_file_id,
                )
            )
            morella_asset_code = session.scalar(
                select(CanonicalAssetClass.code).where(CanonicalAssetClass.id == morella_row.canonical_asset_class_id)
            )
            self.assertEqual("listed_equity", morella_asset_code)
            self.assertEqual("BNSMZ47", morella_row.security_identifier_value)
            self.assertEqual("fully_disclosed", morella_row.disclosure_completeness)
            self.assertEqual(1, len(morella_row.raw_payload_json))
            self.assertEqual(2, morella_row.raw_payload_json[0]["source_row_number"])
            self.assertEqual(
                ["AR2O", "Member Direct", "Equity", "Listed"],
                morella_row.raw_payload_json[0]["payload"][:4],
            )
            self.assertEqual("Morella Corporation Ltd", morella_row.raw_payload_json[0]["payload"][5])
            self.assertEqual("BNSMZ47", morella_row.raw_payload_json[0]["payload"][9])
            self.assertEqual("27255.189", morella_row.raw_payload_json[0]["payload"][14])

            total_row = session.scalar(
                select(Holding).where(Holding.source_row_number == 551, Holding.source_file_id == summary.source_file_id)
            )
            self.assertTrue(total_row.is_aggregate)
            self.assertEqual("aggregate_total", total_row.disclosure_completeness)
            self.assertEqual(Decimal("2844353758"), total_row.value_aud)
            self.assertEqual("Listed Equity", total_row.source_asset_class_raw)
            self.assertEqual("Listed", total_row.source_subclass_raw)

    def test_ingest_stable_official_file_with_real_duplicate_view_merge(self) -> None:
        reporting_period_id = self._create_reporting_period()

        with self.SessionLocal() as session:
            summary = ingest_australiansuper_local_file(
                session,
                fund_code="australiansuper",
                fund_name="AustralianSuper",
                file_path=str(STABLE_PATH),
                reporting_period_id=reporting_period_id,
            )
            session.commit()

            self.assertEqual(4023, summary.rows_staged)
            self.assertEqual(4023, summary.rows_inserted)
            self.assertEqual(0, summary.rows_skipped_existing)

            source_file = session.get(SourceFile, summary.source_file_id)
            self.assertEqual("loaded", source_file.ingest_status)
            self.assertEqual(AUSTRALIANSUPER_STABLE_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(4023, session.query(Holding).count())
            self.assertIsNotNone(session.get(AdapterMappingVersion, AUSTRALIANSUPER_STABLE_MAPPING_VERSION_ID))
            self.assertEqual(194, session.query(SchemaReviewQueue).count())

            ifm_row = session.scalar(
                select(Holding).where(Holding.source_row_number == 3420, Holding.source_file_id == summary.source_file_id)
            )
            self.assertEqual("IFM Investors", ifm_row.raw_name)
            self.assertEqual("$100m to $300m", ifm_row.value_band_raw)
            self.assertEqual([3999], ifm_row.metadata_attached_from_row_numbers)
            self.assertEqual([3420, 3999], [entry["source_row_number"] for entry in ifm_row.raw_payload_json])

            ausgrid_row = session.scalar(
                select(Holding).where(Holding.source_row_number == 3386, Holding.source_file_id == summary.source_file_id)
            )
            self.assertEqual("ownership_only", ausgrid_row.disclosure_completeness)
            self.assertEqual("Electricity", ausgrid_row.classification_raw)
            self.assertEqual([3988], ausgrid_row.metadata_attached_from_row_numbers)

            self.assertEqual(0, session.query(Holding).filter(Holding.source_asset_class_raw == "Derivatives").count())

            first_review_item = session.query(SchemaReviewQueue).order_by(SchemaReviewQueue.id.asc()).first()
            self.assertEqual("ambiguous_duplicate_group", first_review_item.review_reason)

    def test_ingest_conservative_official_file_uses_the_same_approved_shape_as_stable(self) -> None:
        reporting_period_id = self._create_reporting_period()

        with self.SessionLocal() as session:
            summary = ingest_australiansuper_local_file(
                session,
                fund_code="australiansuper",
                fund_name="AustralianSuper",
                file_path=str(CONSERVATIVE_PATH),
                reporting_period_id=reporting_period_id,
            )
            session.commit()

            self.assertEqual(4023, summary.rows_staged)
            self.assertEqual(4023, summary.rows_inserted)
            self.assertEqual(0, summary.rows_skipped_existing)

            source_file = session.get(SourceFile, summary.source_file_id)
            self.assertEqual("loaded", source_file.ingest_status)
            self.assertEqual(AUSTRALIANSUPER_CONSERVATIVE_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(4023, session.query(Holding).count())
            self.assertIsNotNone(session.get(AdapterMappingVersion, AUSTRALIANSUPER_CONSERVATIVE_MAPPING_VERSION_ID))
            self.assertEqual(194, session.query(SchemaReviewQueue).count())

            merged_row = session.scalar(
                select(Holding).where(Holding.source_row_number == 3368, Holding.source_file_id == summary.source_file_id)
            )
            self.assertEqual("1200 W Carroll", merged_row.raw_name)
            self.assertEqual("Office", merged_row.classification_raw)
            self.assertEqual("< $2m", merged_row.value_band_raw)
            self.assertEqual([3877], merged_row.metadata_attached_from_row_numbers)
            self.assertEqual([3368, 3877], [entry["source_row_number"] for entry in merged_row.raw_payload_json])

            self.assertEqual(0, session.query(Holding).filter(Holding.source_asset_class_raw == "Derivatives").count())

    def test_socially_aware_official_file_remains_review_gated_until_separately_approved(self) -> None:
        reporting_period_id = self._create_reporting_period()

        with self.SessionLocal() as session:
            with self.assertRaises(SchemaDriftDetectedError):
                ingest_australiansuper_local_file(
                    session,
                    fund_code="australiansuper",
                    fund_name="AustralianSuper",
                    file_path=str(SOCIALLY_AWARE_PATH),
                    reporting_period_id=reporting_period_id,
                )
            session.commit()

            source_file = session.query(SourceFile).one()
            self.assertEqual("review_required", source_file.ingest_status)
            self.assertEqual(0, session.query(Holding).count())
            self.assertEqual(1, session.query(SchemaReviewQueue).count())
            review_item = session.query(SchemaReviewQueue).one()
            self.assertEqual("schema_drift", review_item.review_reason)
