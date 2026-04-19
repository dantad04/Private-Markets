from __future__ import annotations

from datetime import date
from pathlib import Path
import csv
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
from app.ingest.governance import HOSTPLUS_MAPPING_VERSION_ID, SchemaDriftDetectedError
from app.ingest.loader import ingest_hostplus_local_file


FIXTURE_PATH = Path("tests/fixtures/hostplus_real_extract.csv").resolve()


def mutate_fixture(mutator, output_path: Path) -> Path:
    with FIXTURE_PATH.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        rows = list(csv.reader(handle))
    mutator(rows)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    output_path.write_text(output.getvalue(), encoding="utf-8")
    return output_path


class TestHostPlusLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_hostplus.db'}"
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

    def test_ingest_hostplus_local_file_loads_single_option_source_file(self) -> None:
        reporting_period_id = self._create_reporting_period()

        with self.SessionLocal() as session:
            summary = ingest_hostplus_local_file(
                session,
                fund_code="hostplus",
                fund_name="Hostplus",
                file_path=str(FIXTURE_PATH),
                reporting_period_id=reporting_period_id,
            )
            session.commit()

            self.assertEqual(3215, summary.rows_staged)
            self.assertEqual(3215, summary.rows_inserted)
            self.assertEqual(0, summary.rows_skipped_existing)
            self.assertIsNotNone(summary.investment_option_id)
            self.assertEqual(
                ["Decoded Host-Plus source using UTF-8 errors='replace'; replacement_count=3"],
                summary.warnings,
            )

            source_file = session.get(SourceFile, summary.source_file_id)
            self.assertEqual("HostPlusPhdStateMachineAdapter", source_file.adapter_key)
            self.assertEqual(HOSTPLUS_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(summary.investment_option_id, source_file.investment_option_id)
            self.assertEqual(3215, session.query(Holding).count())
            self.assertEqual(1, session.query(InvestmentOption).count())
            self.assertIsNotNone(session.get(AdapterMappingVersion, HOSTPLUS_MAPPING_VERSION_ID))
            self.assertGreater(session.query(TaxonomyMapping).count(), 0)
            self.assertEqual(0, session.query(SchemaReviewQueue).count())

            industry_super_holdings = session.scalar(
                select(Holding).where(
                    Holding.raw_name == "Industry Super Holdings",
                    Holding.source_row_number == 3184,
                )
            )
            self.assertEqual(0.1317, float(industry_super_holdings.ownership_pct))
            self.assertIsNone(industry_super_holdings.value_aud)
            self.assertEqual("ownership_only", industry_super_holdings.disclosure_completeness)

            ifm_row = session.scalar(
                select(Holding).where(
                    Holding.raw_name == "IFM Investors Pty Ltd",
                    Holding.source_row_number == 3209,
                )
            )
            self.assertEqual(4642022, float(ifm_row.value_aud))
            self.assertEqual("value_only", ifm_row.disclosure_completeness)

    def test_unknown_scope_variant_queues_review_but_file_still_loads(self) -> None:
        reporting_period_id = self._create_reporting_period()
        mutated_path = mutate_fixture(
            lambda rows: rows.__setitem__(3179, ["Held directly or by associated entities or by Trusts", "", "", "", ""]),
            Path(self.tempdir.name) / "hostplus_unknown_scope.csv",
        )

        with self.SessionLocal() as session:
            summary = ingest_hostplus_local_file(
                session,
                fund_code="hostplus",
                fund_name="Hostplus",
                file_path=str(mutated_path),
                reporting_period_id=reporting_period_id,
            )
            session.commit()

            self.assertEqual(3215, summary.rows_inserted)
            self.assertIn("unapproved scope modifier", " ".join(summary.warnings))
            self.assertEqual("loaded", session.get(SourceFile, summary.source_file_id).ingest_status)
            self.assertEqual(1, session.query(SchemaReviewQueue).count())
            review_item = session.query(SchemaReviewQueue).one()
            self.assertEqual("unapproved_scope_modifier", review_item.review_reason)

    def test_header_drift_blocks_ingest_and_queues_schema_review(self) -> None:
        reporting_period_id = self._create_reporting_period()
        mutated_path = mutate_fixture(
            lambda rows: rows.__setitem__(6, ["Name of Institution", "Currency", "", "Value (AUD)", "Weighting (BPS)"]),
            Path(self.tempdir.name) / "hostplus_header_drift.csv",
        )

        with self.SessionLocal() as session:
            with self.assertRaises(SchemaDriftDetectedError) as ctx:
                ingest_hostplus_local_file(
                    session,
                    fund_code="hostplus",
                    fund_name="Hostplus",
                    file_path=str(mutated_path),
                    reporting_period_id=reporting_period_id,
                )
            session.commit()

            self.assertIn("drift detected", str(ctx.exception))
            self.assertEqual(1, session.query(SchemaReviewQueue).count())
            review_item = session.query(SchemaReviewQueue).one()
            self.assertEqual("schema_drift", review_item.review_reason)
