from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import tempfile
import unittest

from sqlalchemy.orm import sessionmaker

from adapters.base import SourceFileMetadata
from adapters.hesta import HestaPhdAdapter
from app.db.models import Base, Holding, ReportingPeriod, SourceFile
from app.db.session import get_engine
from app.ingest.loader import (
    ReportingPeriodMismatchError,
    ingest_hesta_local_file,
    load_adapter_parse_result,
    register_source_file,
)
from tests.hesta_fixture import EXPECTED_TOTAL_ROWS, FIXTURE_PATH


class TestHestaLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage1.db'}"
        self.engine = get_engine(self.database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_ingest_hesta_local_file_loads_idempotently(self) -> None:
        with self.SessionLocal() as session:
            first = ingest_hesta_local_file(
                session,
                fund_code="hesta",
                fund_name="HESTA",
                file_path=str(FIXTURE_PATH),
            )
            session.commit()
            self.assertEqual(EXPECTED_TOTAL_ROWS, first.rows_staged)
            self.assertEqual(EXPECTED_TOTAL_ROWS, first.rows_inserted)
            self.assertEqual(0, first.rows_skipped_existing)

        with self.SessionLocal() as session:
            second = ingest_hesta_local_file(
                session,
                fund_code="hesta",
                fund_name="HESTA",
                file_path=str(FIXTURE_PATH),
            )
            session.commit()
            self.assertEqual(EXPECTED_TOTAL_ROWS, second.rows_staged)
            self.assertEqual(0, second.rows_inserted)
            self.assertEqual(EXPECTED_TOTAL_ROWS, second.rows_skipped_existing)
            self.assertEqual(EXPECTED_TOTAL_ROWS, session.query(Holding).count())

    def test_registered_period_must_match_parsed_period(self) -> None:
        with self.SessionLocal() as session:
            period = ReportingPeriod(
                period_end_date=date(2025, 6, 30),
                disclosure_due_date=date(2025, 9, 28),
                label="2025-06-30",
                source_cycle="semi_annual",
            )
            session.add(period)
            session.flush()

            metadata = register_source_file(
                session,
                fund_code="hesta",
                fund_name="HESTA",
                adapter_key="HestaPhdAdapter",
                source_url=str(FIXTURE_PATH),
                checksum="fixture-mismatch",
                received_at=datetime(2026, 4, 19, 0, 0, 0),
                reporting_period_id=period.id,
            )
            parse_result = HestaPhdAdapter().parse(metadata, FIXTURE_PATH.read_bytes())
            with self.assertRaises(ReportingPeriodMismatchError):
                load_adapter_parse_result(session, metadata, parse_result)

    def test_source_file_row_date_populates_reporting_period_when_missing(self) -> None:
        with self.SessionLocal() as session:
            metadata = register_source_file(
                session,
                fund_code="hesta",
                fund_name="HESTA",
                adapter_key="HestaPhdAdapter",
                source_url=str(FIXTURE_PATH),
                checksum="fixture-auto-period",
                received_at=datetime(2026, 4, 19, 0, 0, 0),
                reporting_period_id=None,
            )
            parse_result = HestaPhdAdapter().parse(metadata, FIXTURE_PATH.read_bytes())
            summary = load_adapter_parse_result(session, metadata, parse_result)
            session.commit()

            source_file = session.get(SourceFile, summary.source_file_id)
            self.assertIsNotNone(source_file.reporting_period_id)
            period = session.get(ReportingPeriod, source_file.reporting_period_id)
            self.assertEqual(date(2025, 12, 31), period.period_end_date)
