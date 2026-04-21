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
from app.entity_resolution.virtual_communities_seed import (
    VIRTUAL_COMMUNITIES_CANONICAL_NAME,
    VIRTUAL_COMMUNITIES_NOTES,
    VIRTUAL_COMMUNITIES_OBSERVED_ALIASES,
    ensure_virtual_communities_seed,
)
from app.ingest.loader import ingest_australiansuper_local_file, ingest_hostplus_local_file
from app.read_models import get_manager_detail


HOSTPLUS_FIXTURE_PATH = Path("tests/fixtures/hostplus_real_extract.csv").resolve()
AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()
AUSTRALIANSUPER_CONSERVATIVE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Conservative PHD (1).csv").resolve()


class TestVirtualCommunitiesSeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'virtual_communities_seed.db'}"
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
            ingest_australiansuper_local_file(
                session,
                fund_code="australiansuper",
                fund_name="AustralianSuper",
                file_path=str(AUSTRALIANSUPER_CONSERVATIVE_FIXTURE_PATH),
                reporting_period_id=period.id,
            )

            entity = ensure_virtual_communities_seed(session)
            cls.entity_id = entity.id
            cls.period_id = period.id
            cls.first_resolution_summary = resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_canonical_manager_seed_exists_with_exact_observed_alias_only(self) -> None:
        with self.SessionLocal() as session:
            entity = session.get(Entity, self.entity_id)
            self.assertIsNotNone(entity)
            assert entity is not None

            self.assertEqual(VIRTUAL_COMMUNITIES_CANONICAL_NAME, entity.canonical_name)
            self.assertEqual("manager", entity.entity_type)
            self.assertIsNone(entity.abn)
            self.assertIsNone(entity.abn_review_source)
            self.assertIsNone(entity.abn_reviewed_by)
            self.assertIsNone(entity.abn_reviewed_at)
            self.assertIsNone(entity.registered_name_on_abr)
            self.assertIsNone(entity.country_code)
            self.assertIsNone(entity.is_australian_entity)
            self.assertIsNone(entity.confidence_tier)
            self.assertEqual(VIRTUAL_COMMUNITIES_NOTES, entity.notes)

            aliases = session.scalars(
                select(EntityAlias.alias)
                .where(EntityAlias.entity_id == self.entity_id)
                .order_by(EntityAlias.alias.asc())
            ).all()
            self.assertEqual(
                [alias for alias, _is_preferred in VIRTUAL_COMMUNITIES_OBSERVED_ALIASES],
                aliases,
            )

    def test_seed_is_idempotent_without_creating_duplicate_aliases(self) -> None:
        with self.SessionLocal() as session:
            first = ensure_virtual_communities_seed(session)
            second = ensure_virtual_communities_seed(session)
            session.commit()

            self.assertEqual(first.id, second.id)
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count(Entity.id)).where(
                        Entity.canonical_name == VIRTUAL_COMMUNITIES_CANONICAL_NAME
                    )
                ),
            )
            self.assertEqual(
                len(VIRTUAL_COMMUNITIES_OBSERVED_ALIASES),
                session.scalar(
                    select(func.count(EntityAlias.id)).where(EntityAlias.entity_id == first.id)
                ),
            )
            refreshed = session.get(Entity, first.id)
            self.assertIsNotNone(refreshed)
            assert refreshed is not None
            self.assertIsNone(refreshed.abn)
            self.assertIsNone(refreshed.abn_review_source)
            self.assertIsNone(refreshed.registered_name_on_abr)
            self.assertIsNone(refreshed.confidence_tier)

    def test_conflicting_entity_type_raises_instead_of_silently_widening_scope(self) -> None:
        with self.SessionLocal() as session:
            entity = session.get(Entity, self.entity_id)
            self.assertIsNotNone(entity)
            assert entity is not None

            entity.entity_type = "company"
            session.flush()

            with self.assertRaisesRegex(ValueError, "conflicting entity_type"):
                ensure_virtual_communities_seed(session)

    def test_deterministic_resolution_links_all_current_exact_match_rows_and_reruns_idempotently(self) -> None:
        with self.SessionLocal() as session:
            rows = session.scalars(
                select(Holding)
                .where(Holding.raw_name == VIRTUAL_COMMUNITIES_CANONICAL_NAME)
                .order_by(Holding.source_file_id.asc(), Holding.source_row_number.asc())
            ).all()

            self.assertEqual(5, len(rows))
            self.assertEqual(5, self.first_resolution_summary.exact_name_auto_links)
            self.assertEqual(0, self.first_resolution_summary.exact_name_ambiguities_queued)
            self.assertEqual(0, self.first_resolution_summary.exact_name_candidates_rejected_due_to_scope_conflict)
            self.assertTrue(all(holding.entity_id == self.entity_id for holding in rows))

            second_summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            self.assertEqual(0, second_summary.exact_name_auto_links)
            self.assertEqual(5, second_summary.holdings_skipped_prelinked)

    def test_manager_detail_keeps_current_scope_behavior_explicit_and_unreviewed(self) -> None:
        with self.SessionLocal() as session:
            detail = get_manager_detail(session, entity_id=self.entity_id)
            self.assertIsNotNone(detail)
            assert detail is not None

            self.assertIsNone(detail.abn)
            self.assertIsNone(detail.abn_review_source)
            self.assertIsNone(detail.abn_reviewed_by)
            self.assertIsNone(detail.abn_reviewed_at)
            self.assertIsNone(detail.registered_name_on_abr)
            self.assertEqual("Linked", detail.entity_confidence_label)
            self.assertEqual(5, detail.observation_count)
            self.assertEqual(2, detail.fund_count)
            self.assertEqual(["manager", "ownership"], detail.role_classes)
            self.assertEqual(3, len(detail.primary_observations))
            self.assertEqual(2, len(detail.supplemental_observations))

            primary_rows = {
                (
                    row.fund_code,
                    row.option_name,
                    row.source_row_number,
                    row.disclosure_completeness,
                    row.observation_kind,
                )
                for row in detail.primary_observations
            }
            self.assertEqual(
                {
                    ("hostplus", "HC High Growth - Class A Option", 3230, "value_only", "manager_rollup"),
                    ("australiansuper", "Stable", 3479, "ownership_only", "direct_holding"),
                    ("australiansuper", "Conservative Balanced", 3479, "ownership_only", "direct_holding"),
                },
                primary_rows,
            )

            supplemental_rows = {
                (
                    row.fund_code,
                    row.option_name,
                    row.source_row_number,
                    row.disclosure_completeness,
                    row.observation_kind,
                    row.is_non_precise,
                )
                for row in detail.supplemental_observations
            }
            self.assertEqual(
                {
                    ("australiansuper", "Stable", 3672, "name_only", "unknown", True),
                    ("australiansuper", "Conservative Balanced", 3662, "name_only", "unknown", True),
                },
                supplemental_rows,
            )
