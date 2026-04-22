from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Entity, EntityAlias, Holding, ReportingPeriod
from app.db.session import get_engine
from app.entity_resolution.brandon_capital_partners_seed import (
    BRANDON_CAPITAL_PARTNERS_ALIASES,
    BRANDON_CAPITAL_PARTNERS_CANONICAL_NAME,
    BRANDON_CAPITAL_PARTNERS_CURRENT_LEGAL_ALIAS,
    BRANDON_CAPITAL_PARTNERS_NOTES,
    BRANDON_CAPITAL_PARTNERS_REGISTERED_NAME_ON_ABR,
    BRANDON_CAPITAL_PARTNERS_REVIEWED_ABN,
    BRANDON_CAPITAL_PARTNERS_REVIEWED_AT,
    BRANDON_CAPITAL_PARTNERS_REVIEWED_BY,
    BRANDON_CAPITAL_PARTNERS_REVIEW_SOURCE,
    ensure_brandon_capital_partners_seed,
)
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.ingest.loader import ingest_australiansuper_local_file, ingest_hostplus_local_file
from app.read_models import get_manager_detail


AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()
AUSTRALIANSUPER_CONSERVATIVE_FIXTURE_PATH = Path(
    "tests/fixtures/real/australiansuper/Conservative PHD (1).csv"
).resolve()
HOSTPLUS_FIXTURE_PATH = Path("tests/fixtures/hostplus_real_extract.csv").resolve()


class TestBrandonCapitalPartnersSeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'brandon_capital_partners_seed.db'}"
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
            ingest_hostplus_local_file(
                session,
                fund_code="hostplus",
                fund_name="Hostplus",
                file_path=str(HOSTPLUS_FIXTURE_PATH),
                reporting_period_id=period.id,
            )

            entity = ensure_brandon_capital_partners_seed(session)
            cls.entity_id = entity.id
            cls.period_id = period.id
            cls.first_resolution_summary = resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_canonical_manager_seed_persists_reviewed_identity_in_place_and_is_idempotent(self) -> None:
        with self.SessionLocal() as session:
            first = ensure_brandon_capital_partners_seed(session)
            second = ensure_brandon_capital_partners_seed(session)
            session.commit()

            self.assertEqual(first.id, second.id)
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count(Entity.id)).where(
                        Entity.canonical_name == BRANDON_CAPITAL_PARTNERS_CANONICAL_NAME
                    )
                ),
            )
            self.assertEqual(
                len(BRANDON_CAPITAL_PARTNERS_ALIASES),
                session.scalar(
                    select(func.count(EntityAlias.id)).where(EntityAlias.entity_id == first.id)
                ),
            )

            entity = session.get(Entity, first.id)
            self.assertIsNotNone(entity)
            assert entity is not None
            self.assertEqual(BRANDON_CAPITAL_PARTNERS_CANONICAL_NAME, entity.canonical_name)
            self.assertEqual("manager", entity.entity_type)
            self.assertEqual(BRANDON_CAPITAL_PARTNERS_REVIEWED_ABN, entity.abn)
            self.assertEqual(BRANDON_CAPITAL_PARTNERS_REVIEW_SOURCE, entity.abn_review_source)
            self.assertEqual(BRANDON_CAPITAL_PARTNERS_REVIEWED_BY, entity.abn_reviewed_by)
            self.assertEqual(BRANDON_CAPITAL_PARTNERS_REVIEWED_AT, entity.abn_reviewed_at)
            self.assertEqual(BRANDON_CAPITAL_PARTNERS_REGISTERED_NAME_ON_ABR, entity.registered_name_on_abr)
            self.assertEqual("AU", entity.country_code)
            self.assertTrue(entity.is_australian_entity)
            self.assertEqual("seeded", entity.confidence_tier)
            self.assertEqual(BRANDON_CAPITAL_PARTNERS_NOTES, entity.notes)

            aliases = session.scalars(
                select(EntityAlias.alias)
                .where(EntityAlias.entity_id == self.entity_id)
                .order_by(EntityAlias.is_preferred.desc(), EntityAlias.alias.asc())
            ).all()
            self.assertEqual(
                [alias for alias, _is_preferred in BRANDON_CAPITAL_PARTNERS_ALIASES],
                aliases,
            )

    def test_deterministic_resolution_links_exact_current_brandon_rows_and_reruns_idempotently(self) -> None:
        with self.SessionLocal() as session:
            rows = session.scalars(
                select(Holding)
                .where(Holding.raw_name == BRANDON_CAPITAL_PARTNERS_CANONICAL_NAME)
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

    def test_manager_detail_renders_current_brandon_rows_with_reviewed_identity_fields(self) -> None:
        with self.SessionLocal() as session:
            detail = get_manager_detail(session, entity_id=self.entity_id)
            self.assertIsNotNone(detail)
            assert detail is not None

            self.assertEqual(BRANDON_CAPITAL_PARTNERS_CANONICAL_NAME, detail.canonical_name)
            self.assertEqual(BRANDON_CAPITAL_PARTNERS_REVIEWED_ABN, detail.abn)
            self.assertEqual(BRANDON_CAPITAL_PARTNERS_REVIEW_SOURCE, detail.abn_review_source)
            self.assertEqual(BRANDON_CAPITAL_PARTNERS_REVIEWED_BY, detail.abn_reviewed_by)
            self.assertEqual(BRANDON_CAPITAL_PARTNERS_REVIEWED_AT, detail.abn_reviewed_at)
            self.assertEqual(BRANDON_CAPITAL_PARTNERS_REGISTERED_NAME_ON_ABR, detail.registered_name_on_abr)
            self.assertEqual(
                [
                    BRANDON_CAPITAL_PARTNERS_CANONICAL_NAME,
                    BRANDON_CAPITAL_PARTNERS_CURRENT_LEGAL_ALIAS,
                ],
                detail.aliases,
            )
            self.assertEqual([BRANDON_CAPITAL_PARTNERS_CANONICAL_NAME], detail.matched_raw_names)
            self.assertEqual("Reviewed", detail.entity_confidence_label)
            self.assertEqual(5, detail.observation_count)
            self.assertEqual(2, detail.fund_count)
            self.assertEqual(["manager"], detail.role_classes)
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
                    ("australiansuper", "Stable", 3395, "value_only", "manager_rollup"),
                    ("australiansuper", "Conservative Balanced", 3395, "value_only", "manager_rollup"),
                    ("hostplus", "HC High Growth - Class A Option", 3197, "value_only", "manager_rollup"),
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
                )
                for row in detail.supplemental_observations
            }
            self.assertEqual(
                {
                    ("australiansuper", "Stable", 3901, "name_only", "unknown"),
                    ("australiansuper", "Conservative Balanced", 3916, "name_only", "unknown"),
                },
                supplemental_rows,
            )
