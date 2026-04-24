from __future__ import annotations

from datetime import date, datetime
from pathlib import Path
import tempfile
import unittest

from sqlalchemy.orm import sessionmaker

from adapters.base import SourceFileMetadata
from adapters.hesta import HestaPhdAdapter
from app.db.models import Base, Holding, InvestmentOption, ReportingPeriod, SourceFile
from app.db.session import get_engine
from app.ingest.loader import (
    ReportingPeriodMismatchError,
    ingest_hesta_local_file,
    load_adapter_parse_result,
    register_source_file,
)
from tests.hesta_fixture import EXPECTED_TOTAL_ROWS, FIXTURE_PATH


REAL_FIXTURE_DIR = Path("tests/fixtures/real/hesta").resolve()
AUSTRALIAN_SHARES_PATH = REAL_FIXTURE_DIR / "Australian-Shares-super-assets.csv"
HIGH_GROWTH_PATH = REAL_FIXTURE_DIR / "High-Growth-super-assets (1).csv"
INDEXED_BALANCED_GROWTH_PATH = REAL_FIXTURE_DIR / "Indexed-Balanced-Growth-super-assets.csv"
INTERNATIONAL_SHARES_PATH = REAL_FIXTURE_DIR / "International-Shares-super-assets.csv"
PROPERTY_AND_INFRASTRUCTURE_PATH = REAL_FIXTURE_DIR / "Property-and-Infrastructure-super-assets.csv"

LATEST_PERIOD_BATCH_CASES = (
    (AUSTRALIAN_SHARES_PATH, "Australian Shares", 346),
    (HIGH_GROWTH_PATH, "High Growth", 2835),
    (INDEXED_BALANCED_GROWTH_PATH, "Indexed Balanced Growth", 1991),
    (INTERNATIONAL_SHARES_PATH, "International Shares", 2456),
    (PROPERTY_AND_INFRASTRUCTURE_PATH, "Property and Infrastructure", 72),
)
HELD_BACK_FILENAMES = {
    "Balanced-Growth-super-assets.csv",
    "Conservative-super-assets.csv",
    "Diversified-Bonds-super-assets.csv",
    "Sustainable-Growth-super-assets.csv",
}


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

    def test_restated_file_supersedes_prior_current_version(self) -> None:
        restated_path = Path(self.tempdir.name) / "hesta_restated.csv"
        restated_path.write_bytes(FIXTURE_PATH.read_bytes() + b"\n")

        with self.SessionLocal() as session:
            first = ingest_hesta_local_file(
                session,
                fund_code="hesta",
                fund_name="HESTA",
                file_path=str(FIXTURE_PATH),
            )
            session.commit()

        with self.SessionLocal() as session:
            second = ingest_hesta_local_file(
                session,
                fund_code="hesta",
                fund_name="HESTA",
                file_path=str(restated_path),
            )
            session.commit()

            first_source_file = session.get(SourceFile, first.source_file_id)
            second_source_file = session.get(SourceFile, second.source_file_id)

            self.assertFalse(first_source_file.is_current_version)
            self.assertIsNone(first_source_file.supersedes_source_file_id)
            self.assertTrue(second_source_file.is_current_version)
            self.assertEqual(first_source_file.id, second_source_file.supersedes_source_file_id)
            self.assertEqual(1, first_source_file.version_number)
            self.assertEqual(2, second_source_file.version_number)
            self.assertEqual(EXPECTED_TOTAL_ROWS * 2, session.query(Holding).count())

    def test_latest_period_parser_compatible_real_files_load_only_accepted_batch(self) -> None:
        with self.SessionLocal() as session:
            for fixture_path, expected_option, expected_rows in LATEST_PERIOD_BATCH_CASES:
                summary = ingest_hesta_local_file(
                    session,
                    fund_code="hesta",
                    fund_name="HESTA",
                    file_path=str(fixture_path),
                )

                source_file = session.get(SourceFile, summary.source_file_id)
                option = session.get(InvestmentOption, summary.investment_option_id)
                period = session.get(ReportingPeriod, summary.reporting_period_id)

                self.assertEqual(expected_rows, summary.rows_staged)
                self.assertEqual(expected_rows, summary.rows_inserted)
                self.assertEqual(0, summary.rows_skipped_existing)
                self.assertEqual(str(fixture_path), source_file.source_url)
                self.assertEqual(64, len(source_file.checksum))
                self.assertEqual(expected_option, option.source_option_name)
                self.assertEqual(date(2025, 12, 31), period.period_end_date)

            session.commit()

        expected_total_rows = sum(expected_rows for _fixture_path, _expected_option, expected_rows in LATEST_PERIOD_BATCH_CASES)
        with self.SessionLocal() as session:
            self.assertEqual(expected_total_rows, session.query(Holding).count())
            self.assertEqual(len(LATEST_PERIOD_BATCH_CASES), session.query(SourceFile).count())
            self.assertEqual(
                {expected_option for _fixture_path, expected_option, _expected_rows in LATEST_PERIOD_BATCH_CASES},
                {option.source_option_name for option in session.query(InvestmentOption).all()},
            )
            source_urls = {source_file.source_url for source_file in session.query(SourceFile).all()}
            self.assertFalse(any("derivatives" in source_url for source_url in source_urls))
            source_filenames = {Path(source_url).name for source_url in source_urls}
            self.assertTrue(source_filenames.isdisjoint(HELD_BACK_FILENAMES))
