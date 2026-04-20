from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AdapterMappingVersion,
    Base,
    Fund,
    InvestmentOption,
    ReportingPeriod,
    SchemaReviewQueue,
    SourceFile,
    TaxonomyMapping,
)
from app.db.session import get_engine
from app.read_models import (
    approve_schema_review_mapping,
    get_schema_review_queue_detail,
    list_schema_review_queue_items,
    update_schema_review_queue_status,
)


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

    def test_approve_schema_review_mapping_persists_new_mapping_and_resolves_queue(self) -> None:
        with self.SessionLocal() as session:
            fund = Fund(code="art", name="ART")
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
                source_option_code="ARST",
                source_option_name="ART Stable",
            )
            session.add(option)
            session.flush()

            previous_mapping = AdapterMappingVersion(
                id="art-stage2-v1",
                adapter_key="ArtSunsuperPhdAdapter",
                schema_fingerprint="previous-fingerprint",
                structural_expectations_json={"observed_headers": ["Option", "Name"]},
                notes="Previous mapping",
                approved_by="repo-seed",
                approved_at=datetime(2026, 4, 20, tzinfo=UTC),
            )
            session.add(previous_mapping)
            session.flush()

            source_file = SourceFile(
                fund_id=fund.id,
                investment_option_id=option.id,
                adapter_key="ArtSunsuperPhdAdapter",
                source_url="https://example.test/art.csv",
                checksum="art-checksum",
                reporting_period_id=period.id,
                schema_fingerprint="observed-fingerprint",
                mapping_version_id=previous_mapping.id,
                ingest_status="review_required",
                publication_date=date(2026, 1, 15),
                received_at=datetime(2026, 4, 20, 10, 30, tzinfo=UTC),
            )
            session.add(source_file)
            session.flush()

            review_item = SchemaReviewQueue(
                adapter_key="ArtSunsuperPhdAdapter",
                source_file_id=source_file.id,
                source_url=source_file.source_url,
                checksum=source_file.checksum,
                observed_schema_fingerprint="observed-fingerprint",
                approved_mapping_version_id=previous_mapping.id,
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
                    ["ART Stable", "IFM Investors Pty Ltd"],
                ],
            )
            session.add(review_item)
            session.commit()
            review_item_id = review_item.id
            period_id = period.id
            source_file_id = source_file.id

        with self.SessionLocal() as session:
            detail = approve_schema_review_mapping(
                session,
                review_item_id=review_item_id,
                mapping_version_id="art-stage2-v2",
                approved_by="reviewer@example.com",
                notes="Approved from schema review queue.",
                structural_expectations_json={
                    "observed_headers": ["Option", "Entity Name"],
                    "observed_internal_external_values": ["Externally Managed", "All Assets"],
                },
                taxonomy_mappings_payload=[
                    {
                        "source_asset_class_raw": "Fixed Income",
                        "source_filter_raw": "Externally Managed",
                        "source_sub_filter_raw": None,
                        "source_section_raw": None,
                        "canonical_asset_class_code": "fixed_income",
                        "is_aggregate_default": False,
                        "disclosure_completeness_default": "value_only",
                        "notes": "Approved from review",
                    },
                    {
                        "source_asset_class_raw": "Private Equity",
                        "source_filter_raw": "All Assets",
                        "source_sub_filter_raw": None,
                        "source_section_raw": None,
                        "canonical_asset_class_code": "unlisted_equity",
                        "is_aggregate_default": False,
                        "disclosure_completeness_default": "name_only",
                        "notes": None,
                    },
                ],
            )
            session.commit()

            self.assertEqual("resolved", detail.review_item.status)
            self.assertEqual("art-stage2-v2", detail.review_item.approved_mapping_version_id)
            self.assertEqual("art-stage2-v2", detail.approved_mapping_version.id)

            mapping_version = session.get(AdapterMappingVersion, "art-stage2-v2")
            self.assertIsNotNone(mapping_version)
            self.assertEqual("ArtSunsuperPhdAdapter", mapping_version.adapter_key)
            self.assertEqual("observed-fingerprint", mapping_version.schema_fingerprint)
            self.assertEqual("reviewer@example.com", mapping_version.approved_by)
            self.assertEqual(
                {
                    "observed_headers": ["Option", "Entity Name"],
                    "observed_internal_external_values": ["Externally Managed", "All Assets"],
                },
                mapping_version.structural_expectations_json,
            )
            self.assertEqual(period_id, mapping_version.effective_from_period_id)
            self.assertIsNone(mapping_version.effective_to_period_id)

            taxonomy_rows = session.scalars(
                select(TaxonomyMapping).where(TaxonomyMapping.mapping_version == "art-stage2-v2")
            ).all()
            self.assertEqual(2, len(taxonomy_rows))
            self.assertEqual(
                {
                    ("Fixed Income", "Externally Managed", "fixed_income", "value_only"),
                    ("Private Equity", "All Assets", "unlisted_equity", "name_only"),
                },
                {
                    (
                        row.source_asset_class_raw,
                        row.source_filter_raw,
                        row.canonical_asset_class_code,
                        row.disclosure_completeness_default,
                    )
                    for row in taxonomy_rows
                },
            )

            refreshed_review_item = session.get(SchemaReviewQueue, review_item_id)
            self.assertEqual("resolved", refreshed_review_item.status)
            self.assertEqual("art-stage2-v2", refreshed_review_item.approved_mapping_version_id)

            refreshed_source_file = session.get(SourceFile, source_file_id)
            self.assertEqual("art-stage2-v2", refreshed_source_file.mapping_version_id)
            self.assertEqual("review_required", refreshed_source_file.ingest_status)
