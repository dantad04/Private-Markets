from __future__ import annotations

from datetime import UTC, date, datetime
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    Base,
    CanonicalAssetClass,
    Entity,
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

    def _add_entity(self, session, *, canonical_name: str, abn: str | None = None) -> Entity:
        entity = Entity(entity_type="company", canonical_name=canonical_name, abn=abn)
        session.add(entity)
        session.flush()
        return entity

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
            source_asset_class_raw="Unlisted Equity",
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
