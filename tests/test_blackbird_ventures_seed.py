from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Entity, EntityAlias, Holding, ReportingPeriod
from app.db.session import get_engine
from app.entity_resolution.blackbird_ventures_seed import (
    BLACKBIRD_VENTURES_ALIASES,
    BLACKBIRD_VENTURES_CANONICAL_NAME,
    BLACKBIRD_VENTURES_CURRENT_LEGAL_ALIAS,
    BLACKBIRD_VENTURES_NOTES,
    ensure_blackbird_ventures_seed,
)
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.ingest.loader import ingest_australiansuper_local_file, ingest_hostplus_local_file
from app.read_models import get_manager_detail


AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()
AUSTRALIANSUPER_CONSERVATIVE_FIXTURE_PATH = Path(
    "tests/fixtures/real/australiansuper/Conservative PHD (1).csv"
).resolve()
HOSTPLUS_FIXTURE_PATH = Path("tests/fixtures/hostplus_real_extract.csv").resolve()
BLACKBIRD_VENTURES_OBSERVED_NAMES = (
    BLACKBIRD_VENTURES_CANONICAL_NAME,
    BLACKBIRD_VENTURES_CURRENT_LEGAL_ALIAS,
)
BLACKBIRD_VENTURES_FUND_VEHICLE_NAME = "Den - Blackbird Ventures 2022 Core Fund"


@dataclass(frozen=True)
class BlackbirdObservationSignature:
    raw_name: str
    source_file_id: int
    source_row_number: int
    disclosure_completeness: str
    value_aud: str | None
    value_band_raw: str | None
    ownership_pct: str | None
    source_subclass_raw: str | None


class TestBlackbirdVenturesSeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'blackbird_ventures_seed.db'}"
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

            cls.pre_seed_signatures = cls._load_blackbird_signatures(session)
            cls.pre_seed_null_entity_count = session.scalar(
                select(func.count(Holding.id)).where(
                    Holding.raw_name.in_(BLACKBIRD_VENTURES_OBSERVED_NAMES),
                    Holding.entity_id.is_(None),
                )
            )
            cls.pre_seed_fund_vehicle_null_entity_count = session.scalar(
                select(func.count(Holding.id)).where(
                    Holding.raw_name == BLACKBIRD_VENTURES_FUND_VEHICLE_NAME,
                    Holding.entity_id.is_(None),
                )
            )

            entity = ensure_blackbird_ventures_seed(session)
            cls.entity_id = entity.id
            cls.period_id = period.id
            cls.first_resolution_summary = resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        cls.tempdir.cleanup()

    @classmethod
    def _load_blackbird_signatures(cls, session) -> list[BlackbirdObservationSignature]:
        rows = session.scalars(
            select(Holding)
            .where(Holding.raw_name.in_(BLACKBIRD_VENTURES_OBSERVED_NAMES))
            .order_by(Holding.source_file_id.asc(), Holding.source_row_number.asc())
        ).all()
        return [
            BlackbirdObservationSignature(
                raw_name=row.raw_name,
                source_file_id=row.source_file_id,
                source_row_number=row.source_row_number,
                disclosure_completeness=row.disclosure_completeness,
                value_aud=str(row.value_aud) if row.value_aud is not None else None,
                value_band_raw=row.value_band_raw,
                ownership_pct=str(row.ownership_pct) if row.ownership_pct is not None else None,
                source_subclass_raw=row.source_subclass_raw,
            )
            for row in rows
        ]

    def test_canonical_manager_seed_persists_dependency_only_shape_and_is_idempotent(self) -> None:
        with self.SessionLocal() as session:
            first = ensure_blackbird_ventures_seed(session)
            second = ensure_blackbird_ventures_seed(session)
            session.commit()

            self.assertEqual(first.id, second.id)
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count(Entity.id)).where(
                        Entity.canonical_name == BLACKBIRD_VENTURES_CANONICAL_NAME
                    )
                ),
            )
            self.assertEqual(
                len(BLACKBIRD_VENTURES_ALIASES),
                session.scalar(
                    select(func.count(EntityAlias.id)).where(EntityAlias.entity_id == first.id)
                ),
            )

            entity = session.get(Entity, first.id)
            self.assertIsNotNone(entity)
            assert entity is not None
            self.assertEqual(BLACKBIRD_VENTURES_CANONICAL_NAME, entity.canonical_name)
            self.assertEqual("manager", entity.entity_type)
            self.assertIsNone(entity.abn)
            self.assertIsNone(entity.abn_review_source)
            self.assertIsNone(entity.abn_reviewed_by)
            self.assertIsNone(entity.abn_reviewed_at)
            self.assertIsNone(entity.registered_name_on_abr)
            self.assertIsNone(entity.country_code)
            self.assertIsNone(entity.is_australian_entity)
            self.assertIsNone(entity.confidence_tier)
            self.assertEqual(BLACKBIRD_VENTURES_NOTES, entity.notes)

            aliases = session.scalars(
                select(EntityAlias.alias)
                .where(EntityAlias.entity_id == self.entity_id)
                .order_by(EntityAlias.is_preferred.desc(), EntityAlias.alias.asc())
            ).all()
            self.assertEqual(
                [alias for alias, _is_preferred in BLACKBIRD_VENTURES_ALIASES],
                aliases,
            )

    def test_deterministic_resolution_links_current_blackbird_rows_without_changing_source_observations(
        self,
    ) -> None:
        with self.SessionLocal() as session:
            rows = session.scalars(
                select(Holding)
                .where(Holding.raw_name.in_(BLACKBIRD_VENTURES_OBSERVED_NAMES))
                .order_by(Holding.source_file_id.asc(), Holding.source_row_number.asc())
            ).all()

            self.assertEqual(5, len(rows))
            self.assertEqual(5, self.pre_seed_null_entity_count)
            self.assertEqual(5, self.first_resolution_summary.exact_name_auto_links)
            self.assertEqual(0, self.first_resolution_summary.exact_name_ambiguities_queued)
            self.assertEqual(0, self.first_resolution_summary.exact_name_candidates_rejected_due_to_scope_conflict)
            self.assertTrue(all(holding.entity_id == self.entity_id for holding in rows))
            self.assertEqual(self.pre_seed_signatures, self._load_blackbird_signatures(session))

            fund_vehicle_rows = session.scalars(
                select(Holding)
                .where(Holding.raw_name == BLACKBIRD_VENTURES_FUND_VEHICLE_NAME)
                .order_by(Holding.source_file_id.asc(), Holding.source_row_number.asc())
            ).all()
            self.assertEqual(2, len(fund_vehicle_rows))
            self.assertEqual(2, self.pre_seed_fund_vehicle_null_entity_count)
            self.assertTrue(all(holding.entity_id is None for holding in fund_vehicle_rows))

            second_summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            self.assertEqual(0, second_summary.exact_name_auto_links)
            self.assertEqual(5, second_summary.holdings_skipped_prelinked)

    def test_manager_detail_renders_linked_blackbird_rows_without_reviewed_identity_fields(self) -> None:
        with self.SessionLocal() as session:
            detail = get_manager_detail(session, entity_id=self.entity_id)
            self.assertIsNotNone(detail)
            assert detail is not None

            self.assertEqual(BLACKBIRD_VENTURES_CANONICAL_NAME, detail.canonical_name)
            self.assertIsNone(detail.abn)
            self.assertIsNone(detail.abn_review_source)
            self.assertIsNone(detail.abn_reviewed_by)
            self.assertIsNone(detail.abn_reviewed_at)
            self.assertIsNone(detail.registered_name_on_abr)
            self.assertEqual(
                [
                    BLACKBIRD_VENTURES_CANONICAL_NAME,
                    BLACKBIRD_VENTURES_CURRENT_LEGAL_ALIAS,
                ],
                detail.aliases,
            )
            self.assertEqual(
                [
                    BLACKBIRD_VENTURES_CANONICAL_NAME,
                    BLACKBIRD_VENTURES_CURRENT_LEGAL_ALIAS,
                ],
                detail.matched_raw_names,
            )
            self.assertEqual("Linked", detail.entity_confidence_label)
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
                    ("australiansuper", "Stable", 3392, "value_only", "manager_rollup"),
                    ("australiansuper", "Conservative Balanced", 3392, "value_only", "manager_rollup"),
                    ("hostplus", "HC High Growth - Class A Option", 3196, "value_only", "manager_rollup"),
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
                    ("australiansuper", "Stable", 3955, "name_only", "unknown"),
                    ("australiansuper", "Conservative Balanced", 3960, "name_only", "unknown"),
                },
                supplemental_rows,
            )
