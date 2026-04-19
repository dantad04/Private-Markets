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
from app.ingest.governance import AUSTRALIANSUPER_MAPPING_VERSION_ID, SchemaDriftDetectedError
from app.ingest.loader import ingest_australiansuper_local_file


FIXTURE_DIR = Path("tests/fixtures/real/australiansuper").resolve()
MEMBER_DIRECT_PATH = FIXTURE_DIR / "Member Direct PHD (1).csv"
STABLE_PATH = FIXTURE_DIR / "Stable PHD (1).csv"


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

    def test_stable_official_file_is_queued_for_review_until_broader_mapping_is_approved(self) -> None:
        reporting_period_id = self._create_reporting_period()

        with self.SessionLocal() as session:
            with self.assertRaises(SchemaDriftDetectedError):
                ingest_australiansuper_local_file(
                    session,
                    fund_code="australiansuper",
                    fund_name="AustralianSuper",
                    file_path=str(STABLE_PATH),
                    reporting_period_id=reporting_period_id,
                )
            session.commit()

            source_file = session.query(SourceFile).one()
            self.assertEqual("review_required", source_file.ingest_status)
            self.assertEqual(AUSTRALIANSUPER_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(0, session.query(Holding).count())
            self.assertEqual(1, session.query(SchemaReviewQueue).count())
            review_item = session.query(SchemaReviewQueue).one()
            self.assertEqual("schema_drift", review_item.review_reason)
            self.assertIn("schema_fingerprint", review_item.drift_summary_json)
