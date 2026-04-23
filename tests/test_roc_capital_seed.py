from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Entity, EntityAlias, Holding, ReportingPeriod
from app.db.session import get_engine
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.entity_resolution.private_entity_asic_company_register_cross_reference import (
    ASIC_COMPANY_STATUS_REGISTERED,
    ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES,
    ASIC_REVIEWED_AT,
    ASIC_REVIEWED_BY,
    ASIC_REVIEW_SOURCE,
    ROC_CAPITAL_ACN,
    ROC_CAPITAL_ASIC_CROSS_REFERENCE,
    ROC_CAPITAL_ASIC_NEXT_REVIEW_DATE,
    ROC_CAPITAL_ASIC_REGISTRATION_DATE,
    ensure_roc_capital_asic_company_register_cross_reference,
)
from app.entity_resolution.roc_capital_seed import (
    ROC_CAPITAL_CANONICAL_NAME,
    ROC_CAPITAL_REGISTERED_NAME_ON_ABR,
    ROC_CAPITAL_NOTES,
    ROC_CAPITAL_OBSERVED_ALIASES,
    ROC_CAPITAL_REVIEWED_ABN,
    ROC_CAPITAL_REVIEWED_AT,
    ROC_CAPITAL_REVIEWED_BY,
    ROC_CAPITAL_REVIEW_SOURCE,
    ensure_roc_capital_seed,
)
from app.ingest.loader import ingest_australiansuper_local_file, ingest_hostplus_local_file
from app.read_models import get_manager_detail


HOSTPLUS_FIXTURE_PATH = Path("tests/fixtures/hostplus_real_extract.csv").resolve()
AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()


class TestRocCapitalSeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'roc_capital_seed.db'}"
        cls.engine = get_engine(cls.database_url)
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False, future=True)

        with cls.SessionLocal() as session:
            period = ReportingPeriod(
                period_end_date=date(2025, 12, 31),
                disclosure_due_date=date(2026, 3, 31),
                label="2025-12-31",
                source_cycle="semi_annual",
            )
            session.add(period)
            session.flush()

            ingest_hostplus_local_file(
                session,
                fund_code="hostplus",
                fund_name="Hostplus",
                file_path=str(HOSTPLUS_FIXTURE_PATH),
                reporting_period_id=period.id,
            )
            ingest_australiansuper_local_file(
                session,
                fund_code="australiansuper",
                fund_name="AustralianSuper",
                file_path=str(AUSTRALIANSUPER_STABLE_FIXTURE_PATH),
                reporting_period_id=period.id,
            )

            entity = ensure_roc_capital_seed(session)
            ensure_roc_capital_asic_company_register_cross_reference(session)
            cls.entity_id = entity.id
            cls.period_id = period.id
            cls.first_resolution_summary = resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_canonical_manager_seed_exists_with_exact_observed_aliases_only(self) -> None:
        with self.SessionLocal() as session:
            entity = session.get(Entity, self.entity_id)
            self.assertIsNotNone(entity)
            assert entity is not None

            self.assertEqual(ROC_CAPITAL_CANONICAL_NAME, entity.canonical_name)
            self.assertEqual("manager", entity.entity_type)
            self.assertEqual(ROC_CAPITAL_REVIEWED_ABN, entity.abn)
            self.assertEqual(ROC_CAPITAL_REVIEW_SOURCE, entity.abn_review_source)
            self.assertEqual(ROC_CAPITAL_REVIEWED_BY, entity.abn_reviewed_by)
            self.assertEqual(ROC_CAPITAL_REVIEWED_AT, entity.abn_reviewed_at)
            self.assertEqual(ROC_CAPITAL_REGISTERED_NAME_ON_ABR, entity.registered_name_on_abr)
            self.assertEqual("seeded", entity.confidence_tier)
            self.assertTrue(entity.is_australian_entity)
            self.assertEqual("AU", entity.country_code)
            self.assertEqual(ROC_CAPITAL_NOTES, entity.notes)

            aliases = session.scalars(
                select(EntityAlias.alias)
                .where(EntityAlias.entity_id == self.entity_id)
                .order_by(EntityAlias.alias.asc())
            ).all()
            self.assertEqual(
                [alias for alias, _is_preferred in ROC_CAPITAL_OBSERVED_ALIASES],
                aliases,
            )

    def test_seed_is_idempotent_without_creating_duplicate_aliases(self) -> None:
        with self.SessionLocal() as session:
            first = ensure_roc_capital_seed(session)
            second = ensure_roc_capital_seed(session)
            ensure_roc_capital_asic_company_register_cross_reference(session)
            ensure_roc_capital_asic_company_register_cross_reference(session)
            session.commit()

            self.assertEqual(first.id, second.id)
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count(Entity.id)).where(Entity.canonical_name == ROC_CAPITAL_CANONICAL_NAME)
                ),
            )
            self.assertEqual(
                len(ROC_CAPITAL_OBSERVED_ALIASES),
                session.scalar(
                    select(func.count(EntityAlias.id)).where(EntityAlias.entity_id == first.id)
                ),
            )
            refreshed = session.get(Entity, first.id)
            self.assertIsNotNone(refreshed)
            assert refreshed is not None
            self.assertEqual(ROC_CAPITAL_REVIEWED_ABN, refreshed.abn)
            self.assertEqual(ROC_CAPITAL_REVIEW_SOURCE, refreshed.abn_review_source)
            self.assertEqual(ROC_CAPITAL_REVIEWED_BY, refreshed.abn_reviewed_by)
            self.assertEqual(ROC_CAPITAL_REVIEWED_AT, refreshed.abn_reviewed_at)
            self.assertEqual(ROC_CAPITAL_REGISTERED_NAME_ON_ABR, refreshed.registered_name_on_abr)
            self.assertEqual(ROC_CAPITAL_ACN, refreshed.acn)
            self.assertEqual(ASIC_COMPANY_STATUS_REGISTERED, refreshed.asic_company_status)
            self.assertEqual(ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES, refreshed.asic_company_type)
            self.assertEqual(ROC_CAPITAL_ASIC_REGISTRATION_DATE, refreshed.asic_registration_date)
            self.assertEqual(ROC_CAPITAL_ASIC_NEXT_REVIEW_DATE, refreshed.asic_next_review_date)
            self.assertEqual(ROC_CAPITAL_ASIC_CROSS_REFERENCE.record_url, refreshed.asic_record_url)
            self.assertEqual(ASIC_REVIEW_SOURCE, refreshed.asic_review_source)
            self.assertEqual(ASIC_REVIEWED_BY, refreshed.asic_reviewed_by)
            self.assertEqual(ASIC_REVIEWED_AT, refreshed.asic_reviewed_at)
            self.assertEqual("seeded", refreshed.confidence_tier)

    def test_conflicting_reviewed_identity_raises_in_manager_style_conflict_guard(self) -> None:
        with self.SessionLocal() as session:
            entity = session.get(Entity, self.entity_id)
            self.assertIsNotNone(entity)
            assert entity is not None

            entity.abn = "37 167 858 765"
            session.flush()

            with self.assertRaisesRegex(ValueError, "conflicting reviewed ABN"):
                ensure_roc_capital_seed(session)

    def test_deterministic_resolution_links_current_roc_rows_and_reruns_idempotently(self) -> None:
        with self.SessionLocal() as session:
            roc_rows = session.scalars(
                select(Holding)
                .where(Holding.raw_name.in_(("ROC Capital Pty Limited", "ROC Capital Pty Ltd")))
                .order_by(Holding.source_row_number.asc())
            ).all()

            self.assertEqual(3, len(roc_rows))
            self.assertEqual(3, self.first_resolution_summary.exact_name_auto_links)
            self.assertEqual(0, self.first_resolution_summary.exact_name_ambiguities_queued)
            self.assertTrue(all(holding.entity_id == self.entity_id for holding in roc_rows))

            manager_scope_rows = [holding for holding in roc_rows if holding.source_row_number in {3223, 3461}]
            self.assertEqual(2, len(manager_scope_rows))
            self.assertTrue(all(holding.entity_id == self.entity_id for holding in manager_scope_rows))

            second_summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            self.assertEqual(0, second_summary.exact_name_auto_links)
            self.assertEqual(3, second_summary.holdings_skipped_prelinked)

    def test_manager_detail_keeps_extra_name_only_row_explicit_as_unknown_non_precise_observation(self) -> None:
        with self.SessionLocal() as session:
            detail = get_manager_detail(session, entity_id=self.entity_id)
            self.assertIsNotNone(detail)
            assert detail is not None

            self.assertEqual(ROC_CAPITAL_REVIEWED_ABN, detail.abn)
            self.assertEqual(ROC_CAPITAL_REVIEW_SOURCE, detail.abn_review_source)
            self.assertEqual(ROC_CAPITAL_REVIEWED_BY, detail.abn_reviewed_by)
            self.assertEqual(ROC_CAPITAL_REVIEWED_AT, detail.abn_reviewed_at)
            self.assertEqual(ROC_CAPITAL_REGISTERED_NAME_ON_ABR, detail.registered_name_on_abr)
            self.assertEqual(ROC_CAPITAL_ACN, detail.acn)
            self.assertEqual(ASIC_COMPANY_STATUS_REGISTERED, detail.asic_company_status)
            self.assertEqual(ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES, detail.asic_company_type)
            self.assertEqual(ROC_CAPITAL_ASIC_REGISTRATION_DATE, detail.asic_registration_date)
            self.assertEqual(ROC_CAPITAL_ASIC_NEXT_REVIEW_DATE, detail.asic_next_review_date)
            self.assertEqual(ROC_CAPITAL_ASIC_CROSS_REFERENCE.record_url, detail.asic_record_url)
            self.assertEqual(ASIC_REVIEW_SOURCE, detail.asic_review_source)
            self.assertEqual(ASIC_REVIEWED_BY, detail.asic_reviewed_by)
            self.assertEqual(ASIC_REVIEWED_AT, detail.asic_reviewed_at)
            self.assertEqual("Reviewed", detail.entity_confidence_label)
            self.assertEqual(3, detail.observation_count)
            self.assertEqual(2, detail.fund_count)
            self.assertEqual(["manager"], detail.role_classes)
            self.assertEqual(2, len(detail.primary_observations))
            self.assertEqual(1, len(detail.supplemental_observations))

            primary_row_numbers = {row.source_row_number for row in detail.primary_observations}
            self.assertEqual({3223, 3461}, primary_row_numbers)

            extra_row = detail.supplemental_observations[0]
            self.assertEqual("ROC Capital Pty Limited", extra_row.raw_name)
            self.assertEqual("australiansuper", extra_row.fund_code)
            self.assertEqual("Stable", extra_row.option_name)
            self.assertEqual(3610, extra_row.source_row_number)
            self.assertEqual("name_only", extra_row.disclosure_completeness)
            self.assertEqual("unknown", extra_row.observation_kind)
            self.assertTrue(extra_row.is_non_precise)
