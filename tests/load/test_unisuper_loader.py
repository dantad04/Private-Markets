from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
import csv
import hashlib
import io
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
from app.ingest.governance import SchemaDriftDetectedError, UNISUPER_MAPPING_VERSION_ID
from app.ingest.loader import ingest_unisuper_local_file


FIXTURE_PATH = Path("tests/fixtures/unisuper_real_extract.csv").resolve()
REAL_FIXTURE_PATH = Path("tests/fixtures/real/UniSuper.csv").resolve()
REAL_SHAPE_FINGERPRINT = "7dc5e32ce188c76fae55f3f4a1c0f09d79eb55ceb9c27a378cb905f222b31cb5"
FULL_SOURCE_OPTIONS = {
    ("UNISUPER_AUSTRALIAN_BOND", "Australian Bond"),
    ("UNISUPER_AUSTRALIAN_DIVIDEND_INCOME", "Australian Dividend Income"),
    ("UNISUPER_AUSTRALIAN_INCOME", "Australian Income"),
    ("UNISUPER_AUSTRALIAN_SHARES", "Australian Shares"),
    ("UNISUPER_BALANCED", "Balanced"),
    ("UNISUPER_CASH", "Cash"),
    ("UNISUPER_CONSERVATIVE", "Conservative"),
    ("UNISUPER_CONSERVATIVE_BALANCED", "Conservative Balanced"),
    ("UNISUPER_GLOBAL_COMPANIES_IN_ASIA", "Global Companies in Asia"),
    ("UNISUPER_GLOBAL_ENVIRONMENTAL_OPPORTUNITIES", "Global Environmental Opportunities"),
    ("UNISUPER_GROWTH", "Growth"),
    ("UNISUPER_HIGH_GROWTH", "High Growth"),
    ("UNISUPER_INTERNATIONAL_SHARES", "International Shares"),
    ("UNISUPER_LISTED_PROPERTY", "Listed Property"),
    ("UNISUPER_SUSTAINABLE_BALANCED", "Sustainable Balanced"),
    ("UNISUPER_SUSTAINABLE_HIGH_GROWTH", "Sustainable High Growth"),
}


def mutate_fixture(mutator, output_path: Path) -> Path:
    with FIXTURE_PATH.open("r", encoding="cp1252", newline="") as handle:
        rows = list(csv.reader(handle))
    mutator(rows)
    with output_path.open("w", encoding="cp1252", newline="") as handle:
        writer = csv.writer(handle, lineterminator="\n")
        writer.writerows(rows)
    return output_path


class TestUniSuperLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_unisuper.db'}"
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

    def test_ingest_unisuper_local_file_loads_multi_option_source_file(self) -> None:
        reporting_period_id = self._create_reporting_period()

        with self.SessionLocal() as session:
            summary = ingest_unisuper_local_file(
                session,
                fund_code="unisuper",
                fund_name="UniSuper",
                file_path=str(FIXTURE_PATH),
                reporting_period_id=reporting_period_id,
            )
            session.commit()

            self.assertEqual(3810, summary.rows_staged)
            self.assertEqual(3810, summary.rows_inserted)
            self.assertEqual(0, summary.rows_skipped_existing)
            self.assertIsNone(summary.investment_option_id)

            source_file = session.get(SourceFile, summary.source_file_id)
            self.assertEqual("UniSuperPhdStateMachineAdapter", source_file.adapter_key)
            self.assertEqual(UNISUPER_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertIsNone(source_file.investment_option_id)
            self.assertEqual(3810, session.query(Holding).count())
            self.assertEqual(2, session.query(InvestmentOption).count())
            self.assertIsNotNone(session.get(AdapterMappingVersion, UNISUPER_MAPPING_VERSION_ID))
            self.assertGreater(session.query(TaxonomyMapping).count(), 0)
            self.assertEqual(0, session.query(SchemaReviewQueue).count())

            ifm_row = session.scalar(
                select(Holding).where(
                    Holding.raw_name == "IFM INVESTORS PTY LIMITED",
                    Holding.source_row_number == 3163,
                )
            )
            self.assertEqual(0.309, float(ifm_row.ownership_pct))
            self.assertIsNone(ifm_row.value_aud)
            self.assertEqual("ownership_only", ifm_row.disclosure_completeness)

            apax_row = session.scalar(
                select(Holding).where(
                    Holding.raw_name == "APAX EUROPE VI LP",
                    Holding.source_row_number == 3143,
                )
            )
            self.assertEqual("name_only", apax_row.disclosure_completeness)

    def test_latest_period_full_source_loads_expected_16_option_batch(self) -> None:
        reporting_period_id = self._create_reporting_period()

        with self.SessionLocal() as session:
            summary = ingest_unisuper_local_file(
                session,
                fund_code="unisuper",
                fund_name="UniSuper",
                file_path=str(REAL_FIXTURE_PATH),
                reporting_period_id=reporting_period_id,
            )
            session.commit()

            self.assertEqual(25404, summary.rows_staged)
            self.assertEqual(25404, summary.rows_inserted)
            self.assertEqual(0, summary.rows_skipped_existing)
            self.assertIsNone(summary.investment_option_id)
            self.assertEqual(REAL_SHAPE_FINGERPRINT, summary.schema_fingerprint)
            self.assertEqual(
                ["Decoded UniSuper source using cp1252 fallback after UTF-8 decode failed"],
                summary.warnings,
            )

            source_file = session.get(SourceFile, summary.source_file_id)
            self.assertEqual(str(REAL_FIXTURE_PATH), source_file.source_url)
            self.assertEqual(hashlib.sha256(REAL_FIXTURE_PATH.read_bytes()).hexdigest(), source_file.checksum)
            self.assertEqual("UniSuperPhdStateMachineAdapter", source_file.adapter_key)
            self.assertEqual(UNISUPER_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(0, source_file.encoding_replacement_count)
            self.assertIsNone(source_file.investment_option_id)
            self.assertEqual(25404, session.query(Holding).count())
            self.assertEqual(256, session.query(Holding).filter(Holding.is_aggregate.is_(True)).count())
            self.assertEqual(16, session.query(InvestmentOption).count())
            self.assertEqual(0, session.query(SchemaReviewQueue).count())

            options = {
                (option.source_option_code, option.source_option_name)
                for option in session.scalars(select(InvestmentOption)).all()
            }
            self.assertEqual(FULL_SOURCE_OPTIONS, options)

            disclosure_counts = Counter(
                row[0]
                for row in session.execute(select(Holding.disclosure_completeness)).all()
            )
            self.assertEqual(
                Counter({"value_only": 24914, "aggregate_total": 256, "ownership_only": 149, "name_only": 85}),
                disclosure_counts,
            )

            first_holding = session.scalar(
                select(Holding)
                .where(Holding.source_file_id == summary.source_file_id)
                .order_by(Holding.source_row_number.asc())
            )
            self.assertIsNotNone(first_holding)
            self.assertEqual(10, first_holding.source_row_number)
            self.assertEqual(64, len(first_holding.source_row_hash))
            self.assertIsInstance(first_holding.raw_payload_json, list)
            self.assertEqual(10, first_holding.raw_payload_json[0]["source_row_number"])

            self.assertFalse(
                session.query(Holding)
                .filter(
                    Holding.raw_name.in_(
                        [
                            "Swaps",
                            "Forwards",
                            "Futures",
                            "Options",
                            "Other",
                            "AUD",
                            "USD",
                            "Currencies of other developed markets",
                            "Currencies of emerging markets",
                        ]
                    )
                )
                .first()
            )

    def test_unknown_scope_variant_queues_review_but_file_still_loads(self) -> None:
        reporting_period_id = self._create_reporting_period()
        mutated_path = mutate_fixture(
            lambda rows: rows.__setitem__(43, ["Held directly or by associated entities or by Trusts", "", "", "", ""]),
            Path(self.tempdir.name) / "unisuper_unknown_scope.csv",
        )

        with self.SessionLocal() as session:
            summary = ingest_unisuper_local_file(
                session,
                fund_code="unisuper",
                fund_name="UniSuper",
                file_path=str(mutated_path),
                reporting_period_id=reporting_period_id,
            )
            session.commit()

            self.assertEqual(3810, summary.rows_inserted)
            self.assertIn("unapproved scope modifier", " ".join(summary.warnings))
            self.assertEqual("loaded", session.get(SourceFile, summary.source_file_id).ingest_status)
            self.assertEqual(1, session.query(SchemaReviewQueue).count())
            review_item = session.query(SchemaReviewQueue).one()
            self.assertEqual("unapproved_scope_modifier", review_item.review_reason)

    def test_header_drift_blocks_ingest_and_queues_schema_review(self) -> None:
        reporting_period_id = self._create_reporting_period()
        mutated_path = mutate_fixture(
            lambda rows: rows.__setitem__(8, ["NAME OF INSTITUTION", "", "CURRENCY", "VALUE (AUD)", "WEIGHTING (BPS)"]),
            Path(self.tempdir.name) / "unisuper_header_drift.csv",
        )

        with self.SessionLocal() as session:
            with self.assertRaises(SchemaDriftDetectedError) as ctx:
                ingest_unisuper_local_file(
                    session,
                    fund_code="unisuper",
                    fund_name="UniSuper",
                    file_path=str(mutated_path),
                    reporting_period_id=reporting_period_id,
                )
            session.commit()

            self.assertIn("drift detected", str(ctx.exception))
            self.assertEqual(1, session.query(SchemaReviewQueue).count())
            review_item = session.query(SchemaReviewQueue).one()
            self.assertEqual("schema_drift", review_item.review_reason)
