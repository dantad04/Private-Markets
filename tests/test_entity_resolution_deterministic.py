from __future__ import annotations

from datetime import UTC, date, datetime, timedelta
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import (
    Base,
    CanonicalAssetClass,
    Entity,
    EntityAlias,
    EntityMatchOverride,
    EntityResolutionQueue,
    EntitySecurityIdentifier,
    Fund,
    Holding,
    InvestmentOption,
    ReportingPeriod,
    SourceFile,
)
from app.db.session import get_engine
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.ingest.loader import seed_canonical_asset_classes


class TestDeterministicEntityResolution(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage3_entity_resolution.db'}"
        self.engine = get_engine(self.database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

        with self.SessionLocal() as session:
            seed_canonical_asset_classes(session)
            period = ReportingPeriod(
                period_end_date=date(2025, 12, 31),
                disclosure_due_date=date(2026, 3, 31),
                label="2025-12-31",
                source_cycle="semi_annual",
            )
            fund = Fund(code="resolver-fund", name="Resolver Fund")
            session.add_all([period, fund])
            session.flush()

            option = InvestmentOption(
                fund_id=fund.id,
                source_option_code="RSLV",
                source_option_name="Resolver Option",
                canonical_option_name="Resolver Option",
                active_from_period=period.period_end_date,
                active_to_period=None,
            )
            session.add(option)
            session.flush()

            source_file = SourceFile(
                fund_id=fund.id,
                investment_option_id=option.id,
                adapter_key="ResolverFixtureAdapter",
                source_url="tests://entity-resolution",
                checksum="resolver-fixture-checksum",
                reporting_period_id=period.id,
                schema_fingerprint="resolver-fixture",
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

            self.period_id = period.id
            self.period_end_date = period.period_end_date
            self.fund_id = fund.id
            self.option_id = option.id
            self.source_file_id = source_file.id
            self.asset_class_id = session.scalar(
                select(CanonicalAssetClass.id).where(CanonicalAssetClass.code == "unlisted_equity")
            )
            session.commit()

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tempdir.cleanup()

    def _add_entity(
        self,
        session,
        *,
        canonical_name: str,
        abn: str | None = None,
        entity_type: str = "company",
    ) -> Entity:
        entity = Entity(entity_type=entity_type, canonical_name=canonical_name, abn=abn)
        session.add(entity)
        session.flush()
        return entity

    def _add_entity_alias(
        self,
        session,
        *,
        entity_id: int,
        alias: str,
        source_system: str = "tests",
    ) -> EntityAlias:
        entity_alias = EntityAlias(
            entity_id=entity_id,
            alias=alias,
            alias_normalized=normalise_name(alias),
            source_system=source_system,
            source_file_id=self.source_file_id,
            is_preferred=False,
            match_confidence=None,
        )
        session.add(entity_alias)
        session.flush()
        return entity_alias

    def _add_override(
        self,
        session,
        *,
        raw_name: str,
        action: str,
        matched_entity_id: int | None = None,
        entity_type_scope: str | None = None,
        source_fund_id: int | None = None,
        source_asset_class_scope: str | None = None,
        expires_at: datetime | None = None,
    ) -> EntityMatchOverride:
        override = EntityMatchOverride(
            raw_name_normalized=normalise_name(raw_name),
            entity_type_scope=entity_type_scope,
            source_fund_id=source_fund_id,
            source_asset_class_scope=source_asset_class_scope,
            matched_entity_id=matched_entity_id,
            action=action,
            reason="Synthetic override for deterministic resolver tests",
            created_by="tests",
            expires_at=expires_at,
        )
        session.add(override)
        session.flush()
        return override

    def _add_entity_security_identifier(
        self,
        session,
        *,
        entity_id: int,
        identifier_type: str,
        identifier_value: str,
    ) -> EntitySecurityIdentifier:
        identifier = EntitySecurityIdentifier(
            entity_id=entity_id,
            identifier_type=identifier_type,
            identifier_value=identifier_value,
            is_preferred=True,
            source="test-seed",
        )
        session.add(identifier)
        session.flush()
        return identifier

    def _add_holding(
        self,
        session,
        *,
        raw_name: str,
        source_row_number: int,
        security_identifier_type: str | None,
        security_identifier_value: str | None,
        entity_id: int | None = None,
        source_asset_class_raw: str = "Unlisted Equity",
    ) -> Holding:
        holding = Holding(
            source_file_id=self.source_file_id,
            source_fund_id=self.fund_id,
            source_option_id=self.option_id,
            reporting_period_id=self.period_id,
            entity_id=entity_id,
            raw_name=raw_name,
            value_aud=None,
            ownership_pct=None,
            units=None,
            is_aggregate=False,
            disclosure_completeness="name_only",
            canonical_asset_class_id=self.asset_class_id,
            source_asset_class_raw=source_asset_class_raw,
            source_subclass_raw=None,
            address=None,
            geo_lat=None,
            geo_lng=None,
            security_identifier_value=security_identifier_value,
            security_identifier_type=security_identifier_type,
            value_band_raw=None,
            source_row_hash=f"resolver-hash-{source_row_number}",
            source_row_number=source_row_number,
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
        return holding

    def test_abn_match_uses_digit_only_normalisation(self) -> None:
        with self.SessionLocal() as session:
            entity = self._add_entity(session, canonical_name="ABN Match Pty Ltd", abn="12 345 678 901")
            holding = self._add_holding(
                session,
                raw_name="ABN Match Pty Ltd",
                source_row_number=1,
                security_identifier_type="ABN",
                security_identifier_value="12-345-678-901",
            )

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertEqual(entity.id, refreshed_holding.entity_id)
            self.assertEqual(1, summary.abn_matches)
            self.assertEqual(0, summary.security_identifier_matches)
            self.assertEqual(1, summary.total_matches)

    def test_security_identifier_match_uses_exact_normalised_identifier_key(self) -> None:
        with self.SessionLocal() as session:
            entity = self._add_entity(session, canonical_name="ISIN Match Pty Ltd")
            self._add_entity_security_identifier(
                session,
                entity_id=entity.id,
                identifier_type="ISIN",
                identifier_value="au0000000001",
            )
            holding = self._add_holding(
                session,
                raw_name="ISIN Match Pty Ltd",
                source_row_number=2,
                security_identifier_type="ISIN",
                security_identifier_value="AU0000000001",
            )

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertEqual(entity.id, refreshed_holding.entity_id)
            self.assertEqual(0, summary.abn_matches)
            self.assertEqual(1, summary.security_identifier_matches)
            self.assertEqual(1, summary.total_matches)

    def test_no_match_path_leaves_holding_unresolved_without_error(self) -> None:
        with self.SessionLocal() as session:
            holding = self._add_holding(
                session,
                raw_name="No Match Pty Ltd",
                source_row_number=3,
                security_identifier_type="ABN",
                security_identifier_value="99 999 999 999",
            )

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertIsNone(refreshed_holding.entity_id)
            self.assertEqual(0, summary.total_matches)
            self.assertEqual(1, summary.unresolved_abn)

    def test_idempotent_rerun_skips_prelinked_rows_without_force_rerun(self) -> None:
        with self.SessionLocal() as session:
            entity = self._add_entity(session, canonical_name="Idempotent Pty Ltd", abn="12345678901")
            holding = self._add_holding(
                session,
                raw_name="Idempotent Pty Ltd",
                source_row_number=4,
                security_identifier_type="ABN",
                security_identifier_value="12345678901",
            )

            first_summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()
            self.assertEqual(1, first_summary.abn_matches)

            second_summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertEqual(entity.id, refreshed_holding.entity_id)
            self.assertEqual(0, second_summary.total_matches)
            self.assertEqual(1, second_summary.holdings_skipped_prelinked)

    def test_force_rerun_can_relink_existing_entity_assignment(self) -> None:
        with self.SessionLocal() as session:
            wrong_entity = self._add_entity(session, canonical_name="Wrong Entity Pty Ltd")
            correct_entity = self._add_entity(session, canonical_name="Correct Entity Pty Ltd", abn="12 345 678 901")
            holding = self._add_holding(
                session,
                raw_name="Correct Entity Pty Ltd",
                source_row_number=5,
                security_identifier_type="ABN",
                security_identifier_value="12345678901",
                entity_id=wrong_entity.id,
            )

            without_force_summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()
            self.assertEqual(0, without_force_summary.total_matches)
            self.assertEqual(1, without_force_summary.holdings_skipped_prelinked)

            with_force_summary = resolve_entities_deterministically(
                session,
                reporting_period_id=self.period_id,
                force_rerun=True,
            )
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertEqual(correct_entity.id, refreshed_holding.entity_id)
            self.assertEqual(1, with_force_summary.abn_matches)
            self.assertEqual(0, with_force_summary.holdings_skipped_prelinked)

    def test_force_match_override_links_matching_raw_name(self) -> None:
        with self.SessionLocal() as session:
            entity = self._add_entity(session, canonical_name="Override Match Pty Ltd")
            holding = self._add_holding(
                session,
                raw_name="Override Match Pty Ltd",
                source_row_number=6,
                security_identifier_type=None,
                security_identifier_value=None,
            )
            self._add_override(
                session,
                raw_name=holding.raw_name,
                action="force_match",
                matched_entity_id=entity.id,
            )

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertEqual(entity.id, refreshed_holding.entity_id)
            self.assertEqual(1, summary.force_match_applications)
            self.assertEqual(0, summary.unresolved_rows_remaining)

    def test_identifier_match_takes_priority_over_manual_override(self) -> None:
        with self.SessionLocal() as session:
            override_entity = self._add_entity(session, canonical_name="Override Target Pty Ltd")
            identifier_entity = self._add_entity(session, canonical_name="Identifier Target Pty Ltd", abn="12 345 678 901")
            holding = self._add_holding(
                session,
                raw_name="Override Target Pty Ltd",
                source_row_number=7,
                security_identifier_type="ABN",
                security_identifier_value="12345678901",
            )
            self._add_override(
                session,
                raw_name=holding.raw_name,
                action="force_match",
                matched_entity_id=override_entity.id,
            )

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertEqual(identifier_entity.id, refreshed_holding.entity_id)
            self.assertEqual(1, summary.abn_matches)
            self.assertEqual(0, summary.force_match_applications)

    def test_force_no_match_override_suppresses_linking(self) -> None:
        with self.SessionLocal() as session:
            holding = self._add_holding(
                session,
                raw_name="No Match Override Pty Ltd",
                source_row_number=8,
                security_identifier_type=None,
                security_identifier_value=None,
            )
            self._add_override(
                session,
                raw_name=holding.raw_name,
                action="force_no_match",
            )

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertIsNone(refreshed_holding.entity_id)
            self.assertEqual(1, summary.force_no_match_suppressions)
            self.assertEqual(1, summary.unresolved_rows_remaining)

    def test_force_new_entity_override_creates_one_entity_and_alias_idempotently(self) -> None:
        with self.SessionLocal() as session:
            holding = self._add_holding(
                session,
                raw_name="Create New Entity Pty Ltd",
                source_row_number=9,
                security_identifier_type=None,
                security_identifier_value=None,
            )
            override = self._add_override(
                session,
                raw_name=holding.raw_name,
                action="force_new_entity",
                entity_type_scope="company",
            )

            first_summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            refreshed_override = session.get(EntityMatchOverride, override.id)
            alias_count = session.scalar(
                select(func.count(EntityAlias.id)).where(EntityAlias.entity_id == refreshed_holding.entity_id)
            )
            entity_count = session.scalar(
                select(func.count(Entity.id)).where(Entity.canonical_name == "Create New Entity Pty Ltd")
            )

            self.assertEqual(1, first_summary.force_new_entity_creations)
            self.assertIsNotNone(refreshed_holding.entity_id)
            self.assertEqual(refreshed_holding.entity_id, refreshed_override.matched_entity_id)
            self.assertEqual(1, alias_count)
            self.assertEqual(1, entity_count)

            second_summary = resolve_entities_deterministically(
                session,
                reporting_period_id=self.period_id,
                force_rerun=True,
            )
            session.commit()

            rerun_alias_count = session.scalar(
                select(func.count(EntityAlias.id)).where(EntityAlias.entity_id == refreshed_holding.entity_id)
            )
            rerun_entity_count = session.scalar(
                select(func.count(Entity.id)).where(Entity.canonical_name == "Create New Entity Pty Ltd")
            )

            self.assertEqual(0, second_summary.force_new_entity_creations)
            self.assertEqual(1, rerun_alias_count)
            self.assertEqual(1, rerun_entity_count)

    def test_redirect_to_parent_override_links_to_target_entity(self) -> None:
        with self.SessionLocal() as session:
            parent_entity = self._add_entity(session, canonical_name="Parent Entity Pty Ltd")
            holding = self._add_holding(
                session,
                raw_name="Child Entity Pty Ltd",
                source_row_number=10,
                security_identifier_type=None,
                security_identifier_value=None,
            )
            self._add_override(
                session,
                raw_name=holding.raw_name,
                action="redirect_to_parent",
                matched_entity_id=parent_entity.id,
            )

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertEqual(parent_entity.id, refreshed_holding.entity_id)
            self.assertEqual(1, summary.redirect_to_parent_applications)
            self.assertEqual(0, summary.unresolved_rows_remaining)

    def test_fund_scoped_override_beats_global_override(self) -> None:
        with self.SessionLocal() as session:
            global_entity = self._add_entity(session, canonical_name="Global Match Pty Ltd")
            scoped_entity = self._add_entity(session, canonical_name="Fund Scoped Match Pty Ltd")
            holding = self._add_holding(
                session,
                raw_name="Scoped Match Pty Ltd",
                source_row_number=11,
                security_identifier_type=None,
                security_identifier_value=None,
            )
            self._add_override(
                session,
                raw_name=holding.raw_name,
                action="force_match",
                matched_entity_id=global_entity.id,
            )
            self._add_override(
                session,
                raw_name=holding.raw_name,
                action="force_match",
                matched_entity_id=scoped_entity.id,
                source_fund_id=self.fund_id,
            )

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertEqual(scoped_entity.id, refreshed_holding.entity_id)
            self.assertEqual(1, summary.force_match_applications)

    def test_asset_class_scoped_override_is_respected(self) -> None:
        with self.SessionLocal() as session:
            global_entity = self._add_entity(session, canonical_name="Global Asset Class Pty Ltd")
            mismatched_entity = self._add_entity(session, canonical_name="Listed Equity Only Pty Ltd")
            holding = self._add_holding(
                session,
                raw_name="Asset Class Scoped Pty Ltd",
                source_row_number=12,
                security_identifier_type=None,
                security_identifier_value=None,
                source_asset_class_raw="Unlisted Equity",
            )
            self._add_override(
                session,
                raw_name=holding.raw_name,
                action="force_match",
                matched_entity_id=global_entity.id,
            )
            self._add_override(
                session,
                raw_name=holding.raw_name,
                action="force_match",
                matched_entity_id=mismatched_entity.id,
                source_asset_class_scope="Listed Equity",
            )

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertEqual(global_entity.id, refreshed_holding.entity_id)
            self.assertEqual(1, summary.force_match_applications)

    def test_expired_override_does_not_apply(self) -> None:
        with self.SessionLocal() as session:
            entity = self._add_entity(session, canonical_name="Expired Override Target Pty Ltd")
            holding = self._add_holding(
                session,
                raw_name="Expired Override Pty Ltd",
                source_row_number=13,
                security_identifier_type=None,
                security_identifier_value=None,
            )
            self._add_override(
                session,
                raw_name=holding.raw_name,
                action="force_match",
                matched_entity_id=entity.id,
                expires_at=datetime.now(UTC) - timedelta(days=1),
            )

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertIsNone(refreshed_holding.entity_id)
            self.assertEqual(0, summary.force_match_applications)
            self.assertEqual(1, summary.unresolved_rows_remaining)

    def test_prelinked_holding_is_unchanged_on_normal_rerun_even_with_override(self) -> None:
        with self.SessionLocal() as session:
            wrong_entity = self._add_entity(session, canonical_name="Persist Existing Link Pty Ltd")
            override_entity = self._add_entity(session, canonical_name="Override Existing Link Pty Ltd")
            holding = self._add_holding(
                session,
                raw_name="Already Linked Override Pty Ltd",
                source_row_number=14,
                security_identifier_type=None,
                security_identifier_value=None,
                entity_id=wrong_entity.id,
            )
            self._add_override(
                session,
                raw_name=holding.raw_name,
                action="force_match",
                matched_entity_id=override_entity.id,
            )

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertEqual(wrong_entity.id, refreshed_holding.entity_id)
            self.assertEqual(1, summary.holdings_skipped_prelinked)
            self.assertEqual(0, summary.force_match_applications)

    def test_force_rerun_applies_override_to_prelinked_holding(self) -> None:
        with self.SessionLocal() as session:
            wrong_entity = self._add_entity(session, canonical_name="Wrong Override Target Pty Ltd")
            override_entity = self._add_entity(session, canonical_name="Correct Override Target Pty Ltd")
            holding = self._add_holding(
                session,
                raw_name="Force Rerun Override Pty Ltd",
                source_row_number=15,
                security_identifier_type=None,
                security_identifier_value=None,
                entity_id=wrong_entity.id,
            )
            self._add_override(
                session,
                raw_name=holding.raw_name,
                action="force_match",
                matched_entity_id=override_entity.id,
            )

            summary = resolve_entities_deterministically(
                session,
                reporting_period_id=self.period_id,
                force_rerun=True,
            )
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertEqual(override_entity.id, refreshed_holding.entity_id)
            self.assertEqual(0, summary.holdings_skipped_prelinked)
            self.assertEqual(1, summary.force_match_applications)

    def test_exact_name_match_auto_links_single_unambiguous_candidate(self) -> None:
        with self.SessionLocal() as session:
            entity = self._add_entity(session, canonical_name="Canonical Holdings Pty Ltd")
            self._add_entity_alias(session, entity_id=entity.id, alias="Exact Match Holdings Pty Ltd")
            holding = self._add_holding(
                session,
                raw_name="  EXACT MATCH HOLDINGS PTY LTD  ",
                source_row_number=16,
                security_identifier_type=None,
                security_identifier_value=None,
            )

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertEqual(entity.id, refreshed_holding.entity_id)
            self.assertEqual(1, summary.exact_name_auto_links)
            self.assertEqual(0, summary.exact_name_ambiguities_queued)
            self.assertEqual(0, summary.unresolved_rows_remaining)

    def test_exact_name_ambiguity_routes_to_review_queue(self) -> None:
        with self.SessionLocal() as session:
            first_entity = self._add_entity(session, canonical_name="Candidate One Pty Ltd")
            second_entity = self._add_entity(session, canonical_name="Candidate Two Pty Ltd")
            self._add_entity_alias(session, entity_id=first_entity.id, alias="Ambiguous Entity Pty Ltd")
            self._add_entity_alias(session, entity_id=second_entity.id, alias="Ambiguous Entity Pty Ltd")
            holding = self._add_holding(
                session,
                raw_name="Ambiguous Entity Pty Ltd",
                source_row_number=17,
                security_identifier_type=None,
                security_identifier_value=None,
            )

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            queue_item = session.scalar(select(EntityResolutionQueue).where(EntityResolutionQueue.holding_id == holding.id))

            self.assertIsNone(refreshed_holding.entity_id)
            self.assertIsNotNone(queue_item)
            self.assertEqual("exact_name", queue_item.evidence_json["ambiguity_kind"])
            self.assertEqual(sorted([first_entity.id, second_entity.id]), queue_item.candidate_entity_ids)
            self.assertEqual(1, summary.exact_name_ambiguities_queued)
            self.assertEqual(1, summary.unresolved_rows_remaining)

    def test_exact_name_scope_conflict_does_not_merge_company_like_row_to_manager_entity(self) -> None:
        with self.SessionLocal() as session:
            manager_entity = self._add_entity(
                session,
                canonical_name="Manager Only Holdings Pty Ltd",
                entity_type="manager",
            )
            self._add_entity_alias(session, entity_id=manager_entity.id, alias="Manager Only Holdings Pty Ltd")
            holding = self._add_holding(
                session,
                raw_name="Manager Only Holdings Pty Ltd",
                source_row_number=18,
                security_identifier_type=None,
                security_identifier_value=None,
                source_asset_class_raw="Unlisted Equity",
            )
            holding.source_subclass_raw = "Internally Managed"

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            queue_count = session.scalar(select(func.count(EntityResolutionQueue.id)))
            self.assertIsNone(refreshed_holding.entity_id)
            self.assertEqual(1, summary.exact_name_candidates_rejected_due_to_scope_conflict)
            self.assertEqual(0, summary.exact_name_auto_links)
            self.assertEqual(0, queue_count)
            self.assertEqual(1, summary.unresolved_rows_remaining)

    def test_exact_name_ownership_row_does_not_force_company_scope_from_internally_managed_subclass(self) -> None:
        with self.SessionLocal() as session:
            manager_entity = self._add_entity(
                session,
                canonical_name="Ownership Match Manager Pty Ltd",
                entity_type="manager",
            )
            self._add_entity_alias(
                session,
                entity_id=manager_entity.id,
                alias="Ownership Match Manager Pty Ltd",
            )
            holding = self._add_holding(
                session,
                raw_name="Ownership Match Manager Pty Ltd",
                source_row_number=18,
                security_identifier_type=None,
                security_identifier_value=None,
                source_asset_class_raw="Unlisted Equity",
            )
            holding.source_subclass_raw = "Internally Managed"
            holding.disclosure_completeness = "ownership_only"
            holding.ownership_pct = Decimal("0.309")

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertEqual(manager_entity.id, refreshed_holding.entity_id)
            self.assertEqual(1, summary.exact_name_auto_links)
            self.assertEqual(0, summary.exact_name_candidates_rejected_due_to_scope_conflict)
            self.assertEqual(0, summary.unresolved_rows_remaining)

    def test_identifier_match_still_wins_over_exact_name_matching(self) -> None:
        with self.SessionLocal() as session:
            exact_name_entity = self._add_entity(session, canonical_name="Exact Name Target Pty Ltd")
            self._add_entity_alias(session, entity_id=exact_name_entity.id, alias="Priority Target Pty Ltd")
            identifier_entity = self._add_entity(session, canonical_name="Identifier Target Pty Ltd", abn="12 345 678 901")
            holding = self._add_holding(
                session,
                raw_name="Priority Target Pty Ltd",
                source_row_number=19,
                security_identifier_type="ABN",
                security_identifier_value="12345678901",
            )

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertEqual(identifier_entity.id, refreshed_holding.entity_id)
            self.assertEqual(1, summary.abn_matches)
            self.assertEqual(0, summary.exact_name_auto_links)

    def test_override_still_wins_over_exact_name_matching(self) -> None:
        with self.SessionLocal() as session:
            exact_name_entity = self._add_entity(session, canonical_name="Exact Name Target Pty Ltd")
            self._add_entity_alias(session, entity_id=exact_name_entity.id, alias="Override Priority Pty Ltd")
            override_entity = self._add_entity(session, canonical_name="Override Priority Target Pty Ltd")
            holding = self._add_holding(
                session,
                raw_name="Override Priority Pty Ltd",
                source_row_number=20,
                security_identifier_type=None,
                security_identifier_value=None,
            )
            self._add_override(
                session,
                raw_name=holding.raw_name,
                action="force_match",
                matched_entity_id=override_entity.id,
            )

            summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertEqual(override_entity.id, refreshed_holding.entity_id)
            self.assertEqual(1, summary.force_match_applications)
            self.assertEqual(0, summary.exact_name_auto_links)

    def test_exact_name_rerun_is_idempotent_without_force_rerun(self) -> None:
        with self.SessionLocal() as session:
            entity = self._add_entity(session, canonical_name="Rerun Exact Match Pty Ltd")
            self._add_entity_alias(session, entity_id=entity.id, alias="Rerun Exact Match Pty Ltd")
            holding = self._add_holding(
                session,
                raw_name="Rerun Exact Match Pty Ltd",
                source_row_number=21,
                security_identifier_type=None,
                security_identifier_value=None,
            )

            first_summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()
            self.assertEqual(1, first_summary.exact_name_auto_links)

            second_summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            refreshed_holding = session.get(Holding, holding.id)
            self.assertEqual(entity.id, refreshed_holding.entity_id)
            self.assertEqual(0, second_summary.exact_name_auto_links)
            self.assertEqual(1, second_summary.holdings_skipped_prelinked)
