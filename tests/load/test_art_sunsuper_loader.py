from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AdapterMappingVersion,
    Base,
    Holding,
    ReportingPeriod,
    SchemaReviewQueue,
    SourceFile,
    TaxonomyMapping,
)
from app.db.session import get_engine
from app.ingest.governance import ART_SUNSUPER_MAPPING_VERSION_ID
from app.ingest.loader import ingest_art_sunsuper_local_file


FIXTURE_PATH = Path("tests/fixtures/art_sunsuper_synthetic_stable_minimal.csv").resolve()


class TestArtSunsuperLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_art_sunsuper.db'}"
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

    def test_ingest_art_sunsuper_local_file_merges_duplicate_views(self) -> None:
        reporting_period_id = self._create_reporting_period()

        with self.SessionLocal() as session:
            summary = ingest_art_sunsuper_local_file(
                session,
                fund_code="art",
                fund_name="ART",
                file_path=str(FIXTURE_PATH),
                reporting_period_id=reporting_period_id,
            )
            session.commit()

            self.assertEqual(4, summary.rows_staged)
            self.assertEqual(4, summary.rows_inserted)
            self.assertEqual(0, summary.rows_skipped_existing)

            source_file = session.get(SourceFile, summary.source_file_id)
            self.assertEqual("ArtSunsuperPhdAdapter", source_file.adapter_key)
            self.assertEqual(ART_SUNSUPER_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(4, session.query(Holding).count())
            self.assertIsNotNone(session.get(AdapterMappingVersion, ART_SUNSUPER_MAPPING_VERSION_ID))
            self.assertGreater(session.query(TaxonomyMapping).count(), 0)
            self.assertEqual(0, session.query(SchemaReviewQueue).count())

            ifm_row = session.scalar(
                select(Holding).where(Holding.raw_name == "IFM Investors Pty Ltd", Holding.source_file_id == summary.source_file_id)
            )
            self.assertEqual("$100m to $300m", ifm_row.value_band_raw)
            self.assertEqual("Debt Manager", ifm_row.classification_raw)
            self.assertEqual([3], ifm_row.metadata_attached_from_row_numbers)
            self.assertEqual(
                [
                    {
                        "source_row_number": 2,
                        "payload": [
                            "ARST",
                            "ART Stable",
                            "Externally Managed",
                            "Fixed Income",
                            "Manager",
                            "IFM Investors Pty Ltd",
                            "n/a",
                            "AUD",
                            "n/a",
                            "339726831",
                            "n/a",
                            "0.07",
                            "n/a",
                            "n/a",
                            "n/a",
                            "n/a",
                            "n/a",
                            "n/a",
                            "Externally Managed",
                            "n/a",
                            "IFM Investors Pty Ltd",
                            "Australia",
                            "n/a",
                            "Management Slice",
                        ],
                    },
                    {
                        "source_row_number": 3,
                        "payload": [
                            "ARST",
                            "ART Stable",
                            "All Assets",
                            "Fixed Income",
                            "Manager",
                            "IFM Investors Pty Ltd",
                            "n/a",
                            "AUD",
                            "n/a",
                            "n/a",
                            "n/a",
                            "n/a",
                            "$100m to $300m",
                            "Debt Manager",
                            "Level 15, 20 Bond Street, Sydney NSW 2000",
                            "Australia",
                            "-33.8644",
                            "151.2088",
                            "Externally Managed",
                            "n/a",
                            "IFM Investors Pty Ltd",
                            "Australia",
                            "n/a",
                            "All Assets Slice",
                        ],
                    },
                ],
                ifm_row.raw_payload_json,
            )

            ish_row = session.scalar(
                select(Holding).where(
                    Holding.raw_name == "Industry Super Holdings Pty Ltd",
                    Holding.source_file_id == summary.source_file_id,
                )
            )
            self.assertEqual(0.18, float(ish_row.ownership_pct))

            self.assertEqual(
                0,
                session.query(Holding).filter(Holding.raw_name == "Equity Futures").count(),
            )

    def test_ambiguous_duplicate_group_is_queued_but_rows_still_load(self) -> None:
        reporting_period_id = self._create_reporting_period()
        ambiguous_path = Path(self.tempdir.name) / "art_sunsuper_ambiguous.csv"
        ambiguous_text = FIXTURE_PATH.read_text(encoding="utf-8") + (
            "\nARST,ART Stable,Externally Managed,Listed Infrastructure,Manager,IFM Investors Pty Ltd,n/a,AUD,n/a,5000000,n/a,0.01,n/a,n/a,n/a,Australia,n/a,n/a,Externally Managed,n/a,IFM Investors Pty Ltd,Australia,n/a,Management Slice\n"
        )
        ambiguous_path.write_text(ambiguous_text, encoding="utf-8")

        with self.SessionLocal() as session:
            summary = ingest_art_sunsuper_local_file(
                session,
                fund_code="art",
                fund_name="ART",
                file_path=str(ambiguous_path),
                reporting_period_id=reporting_period_id,
            )
            session.commit()

            self.assertEqual(5, summary.rows_inserted)
            self.assertEqual("loaded", session.get(SourceFile, summary.source_file_id).ingest_status)
            self.assertEqual(1, session.query(SchemaReviewQueue).count())

            review_item = session.query(SchemaReviewQueue).one()
            self.assertEqual("ambiguous_duplicate_group", review_item.review_reason)

            ifm_rows = session.execute(
                select(Holding).where(Holding.raw_name == "IFM Investors Pty Ltd", Holding.source_file_id == summary.source_file_id)
            ).scalars().all()
            self.assertEqual(2, len(ifm_rows))
            self.assertEqual(
                {"Fixed Income", "Listed Infrastructure"},
                {row.source_asset_class_raw for row in ifm_rows},
            )
