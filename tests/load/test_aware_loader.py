from __future__ import annotations

from collections import Counter
from datetime import date, datetime
import hashlib
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AdapterMappingVersion,
    Base,
    Holding,
    InvestmentOption,
    ReportingPeriod,
    SchemaReviewQueue,
    SourceFile,
    TaxonomyMapping,
)
from app.db.session import get_engine
from app.ingest.loader import ingest_aware_local_file
from app.ingest.governance import (
    AWARE_INVESTMENT_FUNDS_2025_MAPPING_VERSION_ID,
    AWARE_MAPPING_VERSION_ID,
    SchemaDriftDetectedError,
)


FIXTURE_PATH = Path("tests/fixtures/aware_synthetic_table1_minimal.csv").resolve()
REAL_SHAPE_FIXTURE_PATH = Path("tests/fixtures/aware_investment_funds_real_shape_minimal.csv").resolve()
REAL_FIXTURE_DIR = Path("tests/fixtures/real/aware").resolve()
REAL_SHAPE_FINGERPRINT = "5f32c5b412bf04749982c45080dfec21e9e2e46911971d1a9d6e1f2277cb1e0a"
LATEST_PERIOD_BATCH_CASES = (
    (REAL_FIXTURE_DIR / "IFA-Australian-Equities.csv", "Australian Equities", "SS8K", 329),
    (REAL_FIXTURE_DIR / "IFA-Balanced.csv", "Balanced", "SS6K", 1968),
    (REAL_FIXTURE_DIR / "IFA-Capital-Stable.csv", "Capital Stable", "SS5K", 1966),
    (REAL_FIXTURE_DIR / "IFA-Cash.csv", "Cash", "SS3K", 25),
    (REAL_FIXTURE_DIR / "IFA-Growth.csv", "Growth", "SS9K", 1965),
    (REAL_FIXTURE_DIR / "IFA-International-Equities.csv", "International Equities", "SRCK", 1344),
    (REAL_FIXTURE_DIR / "IFA-Moderate.csv", "Moderate", "SS7K", 1969),
    (REAL_FIXTURE_DIR / "IFB-Australian-Equities.csv", "Australian Equities", "SR5K", 329),
    (REAL_FIXTURE_DIR / "IFB-Balanced.csv", "Balanced", "SR2K", 1968),
    (REAL_FIXTURE_DIR / "IFB-Capital-Stable.csv", "Capital Stable", "SRYK", 1966),
    (REAL_FIXTURE_DIR / "IFB-Cash.csv", "Cash", "SRSK", 25),
    (REAL_FIXTURE_DIR / "IFB-Growth.csv", "Growth", "SR6K", 1965),
    (REAL_FIXTURE_DIR / "IFB-International-Equities.csv", "International Equities", "SR7K", 1344),
    (REAL_FIXTURE_DIR / "IFB-Moderate.csv", "Moderate", "SR4K", 1969),
)


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
            self.assertEqual(AWARE_MAPPING_VERSION_ID, source_file.mapping_version_id)

            period = session.get(ReportingPeriod, first.reporting_period_id)
            self.assertEqual(date(2025, 12, 31), period.period_end_date)
            self.assertEqual(19, session.query(Holding).count())
            self.assertIsNotNone(session.get(AdapterMappingVersion, AWARE_MAPPING_VERSION_ID))
            self.assertGreater(session.query(TaxonomyMapping).count(), 0)
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

    def test_schema_drift_blocks_ingest_and_queues_review_item(self) -> None:
        drifted_path = Path(self.tempdir.name) / "aware_drifted.csv"
        drifted_text = FIXTURE_PATH.read_text(encoding="utf-8").replace(
            " - ASSETS - 2025-12-31",
            " - ASSETS UPDATED - 2025-12-31",
            1,
        )
        drifted_path.write_text(drifted_text, encoding="utf-8")

        with self.SessionLocal() as session:
            with self.assertRaises(SchemaDriftDetectedError):
                ingest_aware_local_file(
                    session,
                    fund_code="aware",
                    fund_name="Aware Super",
                    file_path=str(drifted_path),
                )

            review_item = session.query(SchemaReviewQueue).one()
            self.assertEqual("schema_drift", review_item.review_reason)
            self.assertEqual("AwarePhdAdapter", review_item.adapter_key)
            self.assertIn("schema_fingerprint", review_item.drift_summary_json)

            source_file = session.get(SourceFile, review_item.source_file_id)
            self.assertEqual("review_required", source_file.ingest_status)
            self.assertEqual(AWARE_MAPPING_VERSION_ID, source_file.mapping_version_id)

    def test_investment_funds_real_shape_uses_new_mapping_and_filename_option_name(self) -> None:
        file_path = Path(self.tempdir.name) / "IFA-Balanced.csv"
        file_path.write_text(REAL_SHAPE_FIXTURE_PATH.read_text(encoding="utf-8"), encoding="utf-8")

        with self.SessionLocal() as session:
            summary = ingest_aware_local_file(
                session,
                fund_code="aware",
                fund_name="Aware Super",
                file_path=str(file_path),
            )
            session.commit()

            self.assertEqual(26, summary.rows_staged)
            self.assertEqual(REAL_SHAPE_FINGERPRINT, summary.schema_fingerprint)

            source_file = session.get(SourceFile, summary.source_file_id)
            self.assertEqual(AWARE_INVESTMENT_FUNDS_2025_MAPPING_VERSION_ID, source_file.mapping_version_id)

            old_mapping = session.get(AdapterMappingVersion, AWARE_MAPPING_VERSION_ID)
            new_mapping = session.get(AdapterMappingVersion, AWARE_INVESTMENT_FUNDS_2025_MAPPING_VERSION_ID)
            self.assertIsNotNone(old_mapping)
            self.assertIsNotNone(new_mapping)
            self.assertEqual("0221ce01b8fb64d5b1ef06efaf5b70d8ffaf35cb2e0e163c5c0f4a54b4523139", old_mapping.schema_fingerprint)
            self.assertEqual(REAL_SHAPE_FINGERPRINT, new_mapping.schema_fingerprint)

            option = session.get(InvestmentOption, summary.investment_option_id)
            self.assertEqual("SS6K", option.source_option_code)
            self.assertEqual("Balanced", option.source_option_name)
            self.assertEqual("Balanced", option.canonical_option_name)

            self.assertEqual(16, session.query(Holding).filter(Holding.is_aggregate.is_(True)).count())
            self.assertEqual(
                0,
                session.query(Holding)
                .filter(Holding.raw_name.in_(["FORWARDS", "FUTURES", "OPTIONS", "OTHERS", "SWAPS", "AUD", "USD", "TOTAL"]))
                .count(),
            )
            self.assertEqual(
                {
                    "SUB TOTAL CASH",
                    "SUB TOTAL FIXED INCOME EXTERNALLY",
                    "SUB TOTAL FIXED INCOME INTERNALLY",
                    "SUB TOTAL LISTED ALTERNATIVES",
                    "SUB TOTAL LISTED EQUITY",
                    "SUB TOTAL LISTED INFRASTRUCTURE",
                    "SUB TOTAL LISTED PROPERTY",
                    "SUB TOTAL UNLISTED ALTERNATIVES EXTERNALLY",
                    "SUB TOTAL UNLISTED ALTERNATIVES INTERNALLY",
                    "SUB TOTAL UNLISTED EQUITY EXTERNALLY",
                    "SUB TOTAL UNLISTED EQUITY INTERNALLY",
                    "SUB TOTAL UNLISTED INFRASTRUCTURE EXTERNALLY",
                    "SUB TOTAL UNLISTED INFRASTRUCTURE INTERNALLY",
                    "SUB TOTAL UNLISTED PROPERTY EXTERNALLY",
                    "SUB TOTAL UNLISTED PROPERTY INTERNALLY",
                    "TOTAL INVESTMENT ITEMS",
                },
                {
                    row.source_asset_class_raw
                    for row in session.scalars(select(Holding).where(Holding.is_aggregate.is_(True))).all()
                },
            )

    def test_ifa_and_ifb_friendly_names_remain_separate_by_option_code(self) -> None:
        ifa_path = Path(self.tempdir.name) / "IFA-Balanced.csv"
        ifb_path = Path(self.tempdir.name) / "IFB-Balanced.csv"
        fixture_text = REAL_SHAPE_FIXTURE_PATH.read_text(encoding="utf-8")
        ifa_path.write_text(fixture_text, encoding="utf-8")
        ifb_path.write_text(fixture_text.replace("[SS6K]", "[SR2K]"), encoding="utf-8")

        with self.SessionLocal() as session:
            first = ingest_aware_local_file(
                session,
                fund_code="aware",
                fund_name="Aware Super",
                file_path=str(ifa_path),
            )
            second = ingest_aware_local_file(
                session,
                fund_code="aware",
                fund_name="Aware Super",
                file_path=str(ifb_path),
            )
            session.commit()

            self.assertNotEqual(first.investment_option_id, second.investment_option_id)
            options = {
                option.source_option_code: option
                for option in session.scalars(select(InvestmentOption)).all()
            }
            self.assertEqual({"SS6K", "SR2K"}, set(options))
            self.assertEqual("Balanced", options["SS6K"].source_option_name)
            self.assertEqual("Balanced", options["SR2K"].source_option_name)
            self.assertEqual("Balanced", options["SS6K"].canonical_option_name)
            self.assertEqual("Balanced", options["SR2K"].canonical_option_name)
            self.assertEqual(52, session.query(Holding).count())

    def test_latest_period_investment_funds_batch_loads_expected_files_only(self) -> None:
        source_file_ids: list[int] = []
        with self.SessionLocal() as session:
            for fixture_path, option_name, option_code, expected_rows in LATEST_PERIOD_BATCH_CASES:
                summary = ingest_aware_local_file(
                    session,
                    fund_code="aware",
                    fund_name="Aware Super",
                    file_path=str(fixture_path),
                )

                self.assertEqual(expected_rows, summary.rows_staged)
                self.assertEqual(expected_rows, summary.rows_inserted)
                self.assertEqual(0, summary.rows_skipped_existing)
                self.assertEqual(REAL_SHAPE_FINGERPRINT, summary.schema_fingerprint)

                source_file = session.get(SourceFile, summary.source_file_id)
                option = session.get(InvestmentOption, summary.investment_option_id)
                period = session.get(ReportingPeriod, summary.reporting_period_id)

                self.assertEqual(str(fixture_path), source_file.source_url)
                self.assertEqual(hashlib.sha256(fixture_path.read_bytes()).hexdigest(), source_file.checksum)
                self.assertEqual(AWARE_INVESTMENT_FUNDS_2025_MAPPING_VERSION_ID, source_file.mapping_version_id)
                self.assertEqual(0, source_file.encoding_replacement_count)
                self.assertEqual(date(2025, 12, 31), period.period_end_date)
                self.assertEqual(option_code, option.source_option_code)
                self.assertEqual(option_name, option.source_option_name)
                self.assertEqual(option_name, option.canonical_option_name)
                source_file_ids.append(summary.source_file_id)

                first_holding = session.scalar(
                    select(Holding)
                    .where(Holding.source_file_id == summary.source_file_id)
                    .order_by(Holding.source_row_number.asc())
                )
                self.assertIsNotNone(first_holding)
                self.assertGreater(first_holding.source_row_number, 0)
                self.assertEqual(64, len(first_holding.source_row_hash))
                self.assertIsInstance(first_holding.raw_payload_json, list)

            session.commit()

        with self.SessionLocal() as session:
            self.assertEqual(19132, session.query(Holding).count())
            self.assertEqual(224, session.query(Holding).filter(Holding.is_aggregate.is_(True)).count())
            self.assertEqual(14, session.query(SourceFile).count())
            self.assertEqual(14, session.query(InvestmentOption).count())
            self.assertEqual(0, session.query(SchemaReviewQueue).count())

            options = {
                (option.source_option_code, option.source_option_name)
                for option in session.scalars(select(InvestmentOption)).all()
            }
            self.assertEqual(
                {(option_code, option_name) for _path, option_name, option_code, _rows in LATEST_PERIOD_BATCH_CASES},
                options,
            )
            self.assertEqual(7, len({name for _code, name in options}))

            disclosure_counts = Counter(
                row[0]
                for row in session.execute(select(Holding.disclosure_completeness)).all()
            )
            self.assertEqual(
                Counter({"fully_disclosed": 18064, "value_only": 844, "aggregate_total": 224}),
                disclosure_counts,
            )
            self.assertFalse(
                session.query(Holding)
                .filter(
                    Holding.source_file_id.in_(source_file_ids),
                    Holding.raw_name.in_(["FORWARDS", "FUTURES", "OPTIONS", "OTHERS", "SWAPS", "AUD", "USD", "TOTAL"]),
                )
                .first()
            )
            self.assertEqual(
                {
                    "SUB TOTAL CASH",
                    "SUB TOTAL FIXED INCOME EXTERNALLY",
                    "SUB TOTAL FIXED INCOME INTERNALLY",
                    "SUB TOTAL LISTED ALTERNATIVES",
                    "SUB TOTAL LISTED EQUITY",
                    "SUB TOTAL LISTED INFRASTRUCTURE",
                    "SUB TOTAL LISTED PROPERTY",
                    "SUB TOTAL UNLISTED ALTERNATIVES EXTERNALLY",
                    "SUB TOTAL UNLISTED ALTERNATIVES INTERNALLY",
                    "SUB TOTAL UNLISTED EQUITY EXTERNALLY",
                    "SUB TOTAL UNLISTED EQUITY INTERNALLY",
                    "SUB TOTAL UNLISTED INFRASTRUCTURE EXTERNALLY",
                    "SUB TOTAL UNLISTED INFRASTRUCTURE INTERNALLY",
                    "SUB TOTAL UNLISTED PROPERTY EXTERNALLY",
                    "SUB TOTAL UNLISTED PROPERTY INTERNALLY",
                    "TOTAL INVESTMENT ITEMS",
                },
                {
                    row[0]
                    for row in session.execute(
                        select(Holding.source_asset_class_raw).where(Holding.is_aggregate.is_(True))
                    ).all()
                },
            )
            source_filenames = {Path(source_file.source_url).name for source_file in session.query(SourceFile).all()}
            self.assertEqual({path.name for path, _option, _code, _rows in LATEST_PERIOD_BATCH_CASES}, source_filenames)
            self.assertFalse(
                any(
                    forbidden in filename.casefold()
                    for filename in source_filenames
                    for forbidden in ("retirement", "pension", "income stream", "ttr")
                )
            )
