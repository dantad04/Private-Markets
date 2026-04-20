from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from adapters.sunsuper_schema_normalisation import normalise_name
from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import (
    Base,
    CanonicalAssetClass,
    Entity,
    EntityAlias,
    EntityMatchOverride,
    EntityResolutionQueue,
    Fund,
    Holding,
    InvestmentOption,
    ReportingPeriod,
    SourceFile,
)
from app.db.session import get_engine
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.ingest.loader import seed_canonical_asset_classes


class TestEntityResolutionQueueApi(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage3_entity_resolution_queue.db'}"
        self.engine = get_engine(self.database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self.app = create_app()

        def override_get_db_session():
            session = self.SessionLocal()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        self.app.dependency_overrides[get_db_session] = override_get_db_session
        self.client = TestClient(self.app)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.engine.dispose()
        self.tempdir.cleanup()

    def _seed_ambiguous_abn_case(self) -> tuple[int, int, int, int]:
        with self.SessionLocal() as session:
            seed_canonical_asset_classes(session)
            period = ReportingPeriod(
                period_end_date=date(2025, 12, 31),
                disclosure_due_date=date(2026, 3, 31),
                label="2025-12-31",
                source_cycle="semi_annual",
            )
            fund = Fund(code="queue-fund", name="Queue Fund")
            session.add_all([period, fund])
            session.flush()

            option = InvestmentOption(
                fund_id=fund.id,
                source_option_code="QUEUE",
                source_option_name="Queue Option",
                canonical_option_name="Queue Option",
                active_from_period=period.period_end_date,
                active_to_period=None,
            )
            session.add(option)
            session.flush()

            source_file = SourceFile(
                fund_id=fund.id,
                investment_option_id=option.id,
                adapter_key="QueueFixtureAdapter",
                source_url="tests://entity-resolution-queue",
                checksum="queue-fixture-checksum",
                reporting_period_id=period.id,
                schema_fingerprint="queue-fixture",
                mapping_version_id=None,
                ingest_status="loaded",
                publication_date=period.period_end_date,
                version_number=1,
                is_current_version=True,
                encoding_replacement_count=0,
                received_at=datetime(2026, 4, 20, tzinfo=UTC),
            )
            session.add(source_file)
            session.flush()

            asset_class_id = session.scalar(
                select(CanonicalAssetClass.id).where(CanonicalAssetClass.code == "unlisted_equity")
            )

            first_entity = Entity(entity_type="company", canonical_name="Candidate One Pty Ltd", abn="12 345 678 901")
            second_entity = Entity(entity_type="company", canonical_name="Candidate Two Pty Ltd", abn="12345678901")
            session.add_all([first_entity, second_entity])
            session.flush()

            session.add_all(
                [
                    EntityAlias(
                        entity_id=first_entity.id,
                        alias="Candidate One Holdings",
                        alias_normalized=normalise_name("Candidate One Holdings"),
                        source_system="test",
                        source_file_id=source_file.id,
                        is_preferred=True,
                        match_confidence=None,
                    ),
                    EntityAlias(
                        entity_id=second_entity.id,
                        alias="Candidate Two Holdings",
                        alias_normalized=normalise_name("Candidate Two Holdings"),
                        source_system="test",
                        source_file_id=source_file.id,
                        is_preferred=True,
                        match_confidence=None,
                    ),
                ]
            )

            holding = Holding(
                source_file_id=source_file.id,
                source_fund_id=fund.id,
                source_option_id=option.id,
                reporting_period_id=period.id,
                entity_id=None,
                raw_name="Ambiguous Holdings Pty Ltd",
                value_aud=None,
                ownership_pct=None,
                units=None,
                is_aggregate=False,
                disclosure_completeness="name_only",
                canonical_asset_class_id=asset_class_id,
                source_asset_class_raw="Unlisted Equity",
                source_subclass_raw=None,
                address=None,
                geo_lat=None,
                geo_lng=None,
                security_identifier_value="12-345-678-901",
                security_identifier_type="ABN",
                value_band_raw=None,
                source_row_hash="ambiguous-abn-hash",
                source_row_number=1,
                raw_payload_json=[],
                manager_entity_id=None,
                issuer_entity_id=None,
                currency_raw=None,
                classification_raw=None,
                location_raw=None,
                parse_warning_flags=[],
                metadata_attached_from_row_numbers=[],
            )
            session.add(holding)
            session.flush()

            summary = resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

            self.assertEqual(1, summary.ambiguous_abn)
            queue_item = session.query(EntityResolutionQueue).one()
            return queue_item.id, holding.id, first_entity.id, second_entity.id

    def _add_follow_on_holding(self, session, *, like_holding_id: int, source_row_number: int) -> Holding:
        original_holding = session.get(Holding, like_holding_id)
        self.assertIsNotNone(original_holding)
        follow_on_holding = Holding(
            source_file_id=original_holding.source_file_id,
            source_fund_id=original_holding.source_fund_id,
            source_option_id=original_holding.source_option_id,
            reporting_period_id=original_holding.reporting_period_id,
            entity_id=None,
            raw_name=original_holding.raw_name,
            value_aud=original_holding.value_aud,
            ownership_pct=original_holding.ownership_pct,
            units=original_holding.units,
            is_aggregate=original_holding.is_aggregate,
            disclosure_completeness=original_holding.disclosure_completeness,
            canonical_asset_class_id=original_holding.canonical_asset_class_id,
            source_asset_class_raw=original_holding.source_asset_class_raw,
            source_subclass_raw=original_holding.source_subclass_raw,
            address=original_holding.address,
            geo_lat=original_holding.geo_lat,
            geo_lng=original_holding.geo_lng,
            security_identifier_value=original_holding.security_identifier_value,
            security_identifier_type=original_holding.security_identifier_type,
            value_band_raw=original_holding.value_band_raw,
            source_row_hash=f"follow-on-hash-{source_row_number}",
            source_row_number=source_row_number,
            raw_payload_json=[],
            manager_entity_id=original_holding.manager_entity_id,
            issuer_entity_id=original_holding.issuer_entity_id,
            currency_raw=original_holding.currency_raw,
            classification_raw=original_holding.classification_raw,
            location_raw=original_holding.location_raw,
            parse_warning_flags=[],
            metadata_attached_from_row_numbers=[],
        )
        session.add(follow_on_holding)
        session.flush()
        return follow_on_holding

    def test_queue_list_and_detail_expose_candidate_aliases_and_evidence(self) -> None:
        queue_item_id, _holding_id, first_entity_id, second_entity_id = self._seed_ambiguous_abn_case()

        listing = self.client.get("/admin/entity-resolution-queue")
        self.assertEqual(200, listing.status_code)
        listing_payload = listing.json()
        self.assertEqual(1, len(listing_payload))
        self.assertEqual(queue_item_id, listing_payload[0]["queue_item_id"])
        self.assertEqual("Ambiguous Holdings Pty Ltd", listing_payload[0]["raw_name"])
        self.assertEqual("open", listing_payload[0]["status"])

        detail = self.client.get(f"/admin/entity-resolution-queue/{queue_item_id}")
        self.assertEqual(200, detail.status_code)
        detail_payload = detail.json()
        self.assertEqual("Ambiguous Holdings Pty Ltd", detail_payload["holding"]["raw_name"])
        self.assertEqual("ABN", detail_payload["holding"]["security_identifier_type"])
        self.assertEqual("abn", detail_payload["evidence_json"]["ambiguity_kind"])
        self.assertEqual(sorted([first_entity_id, second_entity_id]), detail_payload["candidate_entity_ids"])
        self.assertEqual(
            ["Candidate One Holdings"],
            detail_payload["candidates"][0]["aliases"],
        )

        ui_listing = self.client.get("/admin/ui/entity-resolution-queue")
        self.assertEqual(200, ui_listing.status_code)
        self.assertIn("Ambiguous Holdings Pty Ltd", ui_listing.text)

        ui_detail = self.client.get(f"/admin/ui/entity-resolution-queue/{queue_item_id}")
        self.assertEqual(200, ui_detail.status_code)
        self.assertIn("Candidate One Holdings", ui_detail.text)
        self.assertIn("Candidate Two Holdings", ui_detail.text)
        self.assertIn("Ambiguous Holdings Pty Ltd", ui_detail.text)

    def test_accept_action_links_holding_and_records_resolution(self) -> None:
        queue_item_id, holding_id, first_entity_id, _second_entity_id = self._seed_ambiguous_abn_case()

        response = self.client.post(
            f"/admin/entity-resolution-queue/{queue_item_id}/action",
            json={
                "action": "accept",
                "entity_id": first_entity_id,
                "resolved_by": "reviewer@example.com",
                "notes": "ABN confirmed against registry extract",
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("accepted", payload["queue_item"]["status"])
        self.assertEqual("reviewer@example.com", payload["resolved_by"])

        with self.SessionLocal() as session:
            holding = session.get(Holding, holding_id)
            queue_item = session.get(EntityResolutionQueue, queue_item_id)
            self.assertEqual(first_entity_id, holding.entity_id)
            self.assertEqual("accepted", queue_item.status)
            self.assertEqual("reviewer@example.com", queue_item.resolved_by)
            self.assertIsNotNone(queue_item.resolved_at)

    def test_accept_action_persists_force_match_override_for_future_reruns(self) -> None:
        queue_item_id, holding_id, first_entity_id, _second_entity_id = self._seed_ambiguous_abn_case()

        response = self.client.post(
            f"/admin/entity-resolution-queue/{queue_item_id}/action",
            json={
                "action": "accept",
                "entity_id": first_entity_id,
                "resolved_by": "reviewer@example.com",
                "notes": "Accept scoped match for this queue item",
            },
        )
        self.assertEqual(200, response.status_code)

        with self.SessionLocal() as session:
            follow_on_holding = self._add_follow_on_holding(session, like_holding_id=holding_id, source_row_number=2)
            session.commit()

            summary = resolve_entities_deterministically(session, reporting_period_id=follow_on_holding.reporting_period_id)
            session.commit()

            refreshed_follow_on = session.get(Holding, follow_on_holding.id)
            override = session.scalar(
                select(EntityMatchOverride).where(
                    EntityMatchOverride.raw_name_normalized == normalise_name("Ambiguous Holdings Pty Ltd"),
                    EntityMatchOverride.source_asset_class_scope == "Unlisted Equity",
                    EntityMatchOverride.action == "force_match",
                )
            )
            open_queue_count = session.scalar(
                select(func.count(EntityResolutionQueue.id)).where(EntityResolutionQueue.status == "open")
            )

            self.assertEqual(first_entity_id, refreshed_follow_on.entity_id)
            self.assertIsNotNone(override)
            self.assertEqual(first_entity_id, override.matched_entity_id)
            self.assertEqual(1, summary.force_match_applications)
            self.assertEqual(0, open_queue_count)

    def test_reject_action_marks_queue_item_without_linking_holding(self) -> None:
        queue_item_id, holding_id, _first_entity_id, _second_entity_id = self._seed_ambiguous_abn_case()

        response = self.client.post(
            f"/admin/entity-resolution-queue/{queue_item_id}/action",
            json={
                "action": "reject",
                "resolved_by": "reviewer@example.com",
                "notes": "Leave unresolved for later curation",
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("rejected", payload["queue_item"]["status"])

        with self.SessionLocal() as session:
            holding = session.get(Holding, holding_id)
            queue_item = session.get(EntityResolutionQueue, queue_item_id)
            self.assertIsNone(holding.entity_id)
            self.assertEqual("rejected", queue_item.status)
            self.assertEqual("reviewer@example.com", queue_item.resolved_by)

    def test_reject_action_persists_force_no_match_override_for_future_reruns(self) -> None:
        queue_item_id, holding_id, _first_entity_id, _second_entity_id = self._seed_ambiguous_abn_case()

        response = self.client.post(
            f"/admin/entity-resolution-queue/{queue_item_id}/action",
            json={
                "action": "reject",
                "resolved_by": "reviewer@example.com",
                "notes": "Keep this raw name unresolved in this slice",
            },
        )
        self.assertEqual(200, response.status_code)

        with self.SessionLocal() as session:
            follow_on_holding = self._add_follow_on_holding(session, like_holding_id=holding_id, source_row_number=3)
            session.commit()

            summary = resolve_entities_deterministically(session, reporting_period_id=follow_on_holding.reporting_period_id)
            session.commit()

            refreshed_follow_on = session.get(Holding, follow_on_holding.id)
            override = session.scalar(
                select(EntityMatchOverride).where(
                    EntityMatchOverride.raw_name_normalized == normalise_name("Ambiguous Holdings Pty Ltd"),
                    EntityMatchOverride.source_asset_class_scope == "Unlisted Equity",
                    EntityMatchOverride.action == "force_no_match",
                )
            )
            open_queue_count = session.scalar(
                select(func.count(EntityResolutionQueue.id)).where(EntityResolutionQueue.status == "open")
            )

            self.assertIsNone(refreshed_follow_on.entity_id)
            self.assertIsNotNone(override)
            self.assertEqual(2, summary.force_no_match_suppressions)
            self.assertEqual(0, open_queue_count)

    def test_create_new_action_creates_entity_alias_and_links_holding(self) -> None:
        queue_item_id, holding_id, _first_entity_id, _second_entity_id = self._seed_ambiguous_abn_case()

        response = self.client.post(
            f"/admin/entity-resolution-queue/{queue_item_id}/action",
            json={
                "action": "create_new",
                "resolved_by": "reviewer@example.com",
                "notes": "Create a fresh canonical entity",
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("created_new", payload["queue_item"]["status"])

        with self.SessionLocal() as session:
            holding = session.get(Holding, holding_id)
            queue_item = session.get(EntityResolutionQueue, queue_item_id)
            created_entity = session.get(Entity, holding.entity_id)
            alias = session.scalar(select(EntityAlias).where(EntityAlias.entity_id == created_entity.id))

            self.assertIsNotNone(created_entity)
            self.assertEqual("Ambiguous Holdings Pty Ltd", created_entity.canonical_name)
            self.assertEqual("company", created_entity.entity_type)
            self.assertEqual("Ambiguous Holdings Pty Ltd", alias.alias)
            self.assertEqual(normalise_name("Ambiguous Holdings Pty Ltd"), alias.alias_normalized)
            self.assertEqual("created_new", queue_item.status)
            self.assertEqual("reviewer@example.com", queue_item.resolved_by)

    def test_create_new_action_persists_override_and_reuses_same_entity_on_rerun(self) -> None:
        queue_item_id, holding_id, _first_entity_id, _second_entity_id = self._seed_ambiguous_abn_case()

        response = self.client.post(
            f"/admin/entity-resolution-queue/{queue_item_id}/action",
            json={
                "action": "create_new",
                "resolved_by": "reviewer@example.com",
                "notes": "Create and persist a fresh canonical entity for this scoped raw name",
            },
        )
        self.assertEqual(200, response.status_code)

        with self.SessionLocal() as session:
            original_holding = session.get(Holding, holding_id)
            created_entity_id = original_holding.entity_id
            follow_on_holding = self._add_follow_on_holding(session, like_holding_id=holding_id, source_row_number=4)
            session.commit()

            summary = resolve_entities_deterministically(session, reporting_period_id=follow_on_holding.reporting_period_id)
            session.commit()

            refreshed_follow_on = session.get(Holding, follow_on_holding.id)
            override = session.scalar(
                select(EntityMatchOverride).where(
                    EntityMatchOverride.raw_name_normalized == normalise_name("Ambiguous Holdings Pty Ltd"),
                    EntityMatchOverride.source_asset_class_scope == "Unlisted Equity",
                    EntityMatchOverride.action == "force_new_entity",
                )
            )
            created_entity_count = session.scalar(
                select(func.count(Entity.id)).where(Entity.canonical_name == "Ambiguous Holdings Pty Ltd")
            )

            self.assertEqual(created_entity_id, refreshed_follow_on.entity_id)
            self.assertIsNotNone(override)
            self.assertEqual(created_entity_id, override.matched_entity_id)
            self.assertEqual(0, summary.force_new_entity_creations)
            self.assertEqual(1, created_entity_count)
