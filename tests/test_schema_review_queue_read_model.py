from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
import tempfile
import unittest

from sqlalchemy.orm import sessionmaker

from app.db.models import AdapterMappingVersion, Base, Fund, InvestmentOption, ReportingPeriod, SchemaReviewQueue, SourceFile
from app.db.session import get_engine
from app.read_models import get_schema_review_queue_detail, list_schema_review_queue_items, update_schema_review_queue_status


class TestSchemaReviewQueueReadModel(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'schema_review_read_model.db'}"
        self.engine = get_engine(self.database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_list_detail_and_status_transition_cover_review_queue(self) -> None:
        with self.SessionLocal() as session:
            fund = Fund(code="aware", name="Aware Super")
            period = ReportingPeriod(
                period_end_date=date(2025, 12, 31),
                disclosure_due_date=date(2026, 3, 31),
                label="2025-12-31",
                source_cycle="semi_annual",
            )
            session.add_all([fund, period])
            session.flush()

            option = InvestmentOption(
                fund_id=fund.id,
                source_option_code="BA",
                source_option_name="Balanced",
            )
            mapping_version = AdapterMappingVersion(
                id="aware-stage2-v1",
                adapter_key="AwarePhdAdapter",
                schema_fingerprint="approved-fingerprint",
                structural_expectations_json={"observed_headers": ["Option", "Name"]},
                notes="Approved Stage 2 Aware synthetic vertical-slice mapping.",
                approved_by="repo-seed",
                approved_at=datetime(2026, 4, 20, tzinfo=UTC),
            )
            session.add_all([option, mapping_version])
            session.flush()

            source_file = SourceFile(
                fund_id=fund.id,
                investment_option_id=option.id,
                adapter_key="AwarePhdAdapter",
                source_url="https://example.test/aware.csv",
                checksum="abc123",
                reporting_period_id=period.id,
                schema_fingerprint="observed-fingerprint",
                mapping_version_id=mapping_version.id,
                ingest_status="review_required",
                publication_date=date(2026, 1, 15),
                received_at=datetime(2026, 4, 20, 10, 30, tzinfo=UTC),
            )
            session.add(source_file)
            session.flush()

            review_item = SchemaReviewQueue(
                adapter_key="AwarePhdAdapter",
                source_file_id=source_file.id,
                source_url=source_file.source_url,
                checksum=source_file.checksum,
                observed_schema_fingerprint="observed-fingerprint",
                approved_mapping_version_id=mapping_version.id,
                review_reason="schema_drift",
                status="open",
                drift_summary_json={
                    "observed_headers": {
                        "expected": ["Option", "Name"],
                        "actual": ["Option", "Entity Name"],
                    }
                },
                sample_rows_json=[
                    ["Option", "Entity Name"],
                    ["Balanced", "Aware Holdings Pty Ltd"],
                ],
            )
            session.add(review_item)
            session.commit()
            review_item_id = review_item.id

        with self.SessionLocal() as session:
            open_items = list_schema_review_queue_items(session)
            self.assertEqual(1, len(open_items))
            self.assertEqual(review_item_id, open_items[0].id)
            self.assertEqual("schema_drift", open_items[0].review_reason)
            self.assertEqual("open", open_items[0].status)

            detail = get_schema_review_queue_detail(session, review_item_id=review_item_id)
            self.assertIsNotNone(detail)
            self.assertEqual("AwarePhdAdapter", detail.review_item.adapter_key)
            self.assertEqual("Aware Super", detail.source_file.fund_name)
            self.assertEqual("Balanced", detail.source_file.investment_option_name)
            self.assertEqual("aware-stage2-v1", detail.approved_mapping_version.id)
            self.assertEqual(
                ["Option", "Entity Name"],
                detail.drift_summary_json["observed_headers"]["actual"],
            )
            self.assertEqual(["Balanced", "Aware Holdings Pty Ltd"], detail.sample_rows_json[1])

            updated = update_schema_review_queue_status(session, review_item_id=review_item_id, new_status="resolved")
            self.assertEqual("resolved", updated.review_item.status)
            session.commit()

        with self.SessionLocal() as session:
            self.assertEqual([], list_schema_review_queue_items(session))
            all_items = list_schema_review_queue_items(session, status_filter="all")
            self.assertEqual(1, len(all_items))
            self.assertEqual("resolved", all_items[0].status)

