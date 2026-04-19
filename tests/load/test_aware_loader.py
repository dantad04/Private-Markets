from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Holding, ReportingPeriod, SourceFile
from app.db.session import get_engine
from app.ingest.loader import ingest_aware_local_file


FIXTURE_PATH = Path("tests/fixtures/aware_synthetic_table1_minimal.csv").resolve()


class TestAwareLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_aware.db'}"
        self.engine = get_engine(self.database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_ingest_aware_local_file_loads_idempotently_and_backfills_period(self) -> None:
        with self.SessionLocal() as session:
            first = ingest_aware_local_file(
                session,
                fund_code="aware",
                fund_name="Aware Super",
                file_path=str(FIXTURE_PATH),
                terms_snapshot_url="https://example.com/aware/terms",
                downloaded_at=datetime(2026, 4, 20, 10, 30, 0),
            )
            session.commit()
            self.assertEqual(19, first.rows_staged)
            self.assertEqual(19, first.rows_inserted)
            self.assertEqual(0, first.rows_skipped_existing)

            source_file = session.get(SourceFile, first.source_file_id)
            self.assertEqual("AwarePhdAdapter", source_file.adapter_key)
            self.assertEqual(0, source_file.encoding_replacement_count)
            self.assertEqual("https://example.com/aware/terms", source_file.terms_snapshot_url)
            self.assertEqual(datetime(2026, 4, 20, 10, 30, 0), source_file.downloaded_at)

            period = session.get(ReportingPeriod, first.reporting_period_id)
            self.assertEqual(date(2025, 12, 31), period.period_end_date)
            self.assertEqual(19, session.query(Holding).count())
            self.assertEqual(
                10,
                session.query(Holding).filter(Holding.is_aggregate.is_(True)).count(),
            )
            self.assertEqual(
                0,
                session.query(Holding)
                .filter(Holding.raw_name.in_(["FORWARDS", "AUD", "USD", "TOTAL"]))
                .count(),
            )

        with self.SessionLocal() as session:
            second = ingest_aware_local_file(
                session,
                fund_code="aware",
                fund_name="Aware Super",
                file_path=str(FIXTURE_PATH),
            )
            session.commit()
            self.assertEqual(19, second.rows_staged)
            self.assertEqual(0, second.rows_inserted)
            self.assertEqual(19, second.rows_skipped_existing)
            self.assertEqual(19, session.query(Holding).count())

    def test_ingest_aware_persists_encoding_replacement_count(self) -> None:
        broken_bytes = FIXTURE_PATH.read_bytes().replace(b"SYNTH PROPERTY TRUST", b"SYNTH PROP\xC0RTY TRUST", 1)
        broken_path = Path(self.tempdir.name) / "aware_replacement.csv"
        broken_path.write_bytes(broken_bytes)

        with self.SessionLocal() as session:
            summary = ingest_aware_local_file(
                session,
                fund_code="aware",
                fund_name="Aware Super",
                file_path=str(broken_path),
            )
            session.commit()
            source_file = session.get(SourceFile, summary.source_file_id)
            self.assertEqual(1, source_file.encoding_replacement_count)
            property_row = session.scalar(
                select(Holding).where(Holding.source_row_number == 10, Holding.source_file_id == summary.source_file_id)
            )
            self.assertIn("\ufffd", property_row.raw_name)
