from __future__ import annotations

from dataclasses import dataclass
from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Entity, EntityAlias, Holding, ReportingPeriod
from app.db.session import get_engine
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.entity_resolution.marron_group_holdings_seed import (
    MARRON_GROUP_HOLDINGS_CANONICAL_NAME,
    MARRON_GROUP_HOLDINGS_NOTES,
    MARRON_GROUP_HOLDINGS_OBSERVED_ALIASES,
    ensure_marron_group_holdings_seed,
)
from app.ingest.loader import ingest_australiansuper_local_file
from app.read_models import get_company_detail


AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()
AUSTRALIANSUPER_CONSERVATIVE_FIXTURE_PATH = Path(
    "tests/fixtures/real/australiansuper/Conservative PHD (1).csv"
).resolve()
MARRON_GROUP_HOLDINGS_WARRANTS_RAW_NAME = "Marron Group Holdings Pty Ltd Unissued Warrants"


@dataclass(frozen=True)
class MarronGroupHoldingsObservationSignature:
    raw_name: str
    source_file_id: int
    source_row_number: int
    disclosure_completeness: str
    value_aud: str | None
    ownership_pct: str | None
    source_asset_class_raw: str
    source_subclass_raw: str | None


class TestMarronGroupHoldingsSeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'marron_group_holdings_seed.db'}"
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

            cls.pre_seed_signatures = cls._load_marron_signatures(session)
            cls.pre_seed_null_entity_count = session.scalar(
                select(func.count(Holding.id)).where(
                    Holding.raw_name == MARRON_GROUP_HOLDINGS_CANONICAL_NAME,
                    Holding.entity_id.is_(None),
                )
            )
            cls.pre_seed_warrant_null_entity_count = session.scalar(
                select(func.count(Holding.id)).where(
                    Holding.raw_name == MARRON_GROUP_HOLDINGS_WARRANTS_RAW_NAME,
                    Holding.entity_id.is_(None),
                )
            )

            entity = ensure_marron_group_holdings_seed(session)
            cls.entity_id = entity.id
            cls.period_id = period.id
            cls.first_resolution_summary = resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        cls.tempdir.cleanup()

    @classmethod
    def _load_marron_signatures(cls, session) -> list[MarronGroupHoldingsObservationSignature]:
        rows = session.scalars(
            select(Holding)
            .where(Holding.raw_name == MARRON_GROUP_HOLDINGS_CANONICAL_NAME)
            .order_by(Holding.source_file_id.asc(), Holding.source_row_number.asc())
        ).all()
        return [
            MarronGroupHoldingsObservationSignature(
                raw_name=row.raw_name,
                source_file_id=row.source_file_id,
                source_row_number=row.source_row_number,
                disclosure_completeness=row.disclosure_completeness,
                value_aud=str(row.value_aud) if row.value_aud is not None else None,
                ownership_pct=str(row.ownership_pct) if row.ownership_pct is not None else None,
                source_asset_class_raw=row.source_asset_class_raw,
                source_subclass_raw=row.source_subclass_raw,
            )
            for row in rows
        ]

    def test_canonical_company_seed_exists_with_exact_observed_alias_only(self) -> None:
        with self.SessionLocal() as session:
            entity = session.get(Entity, self.entity_id)
            self.assertIsNotNone(entity)
            assert entity is not None

            self.assertEqual(MARRON_GROUP_HOLDINGS_CANONICAL_NAME, entity.canonical_name)
            self.assertEqual("company", entity.entity_type)
            self.assertIsNone(entity.abn)
            self.assertIsNone(entity.abn_review_source)
            self.assertIsNone(entity.registered_name_on_abr)
            self.assertIsNone(entity.acn)
            self.assertIsNone(entity.asic_company_status)
            self.assertIsNone(entity.asic_company_type)
            self.assertIsNone(entity.asic_registration_date)
            self.assertIsNone(entity.asic_next_review_date)
            self.assertIsNone(entity.asic_record_url)
            self.assertIsNone(entity.asic_review_source)
            self.assertIsNone(entity.asic_reviewed_by)
            self.assertIsNone(entity.asic_reviewed_at)
            self.assertIsNone(entity.country_code)
            self.assertIsNone(entity.is_australian_entity)
            self.assertIsNone(entity.confidence_tier)
            self.assertEqual(MARRON_GROUP_HOLDINGS_NOTES, entity.notes)

            aliases = session.scalars(
                select(EntityAlias.alias)
                .where(EntityAlias.entity_id == self.entity_id)
                .order_by(EntityAlias.alias.asc())
            ).all()
            self.assertEqual(
                [alias for alias, _is_preferred in MARRON_GROUP_HOLDINGS_OBSERVED_ALIASES],
                aliases,
            )

    def test_seed_is_idempotent_and_does_not_populate_reviewed_identity_or_asic_fields(self) -> None:
        with self.SessionLocal() as session:
            first = ensure_marron_group_holdings_seed(session)
            second = ensure_marron_group_holdings_seed(session)
            session.commit()

            self.assertEqual(first.id, second.id)
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count(Entity.id)).where(
                        Entity.canonical_name == MARRON_GROUP_HOLDINGS_CANONICAL_NAME
                    )
                ),
            )
            self.assertEqual(
                len(MARRON_GROUP_HOLDINGS_OBSERVED_ALIASES),
                session.scalar(
                    select(func.count(EntityAlias.id)).where(EntityAlias.entity_id == first.id)
                ),
            )

            entity = session.get(Entity, first.id)
            self.assertIsNotNone(entity)
            assert entity is not None
            self.assertIsNone(entity.abn)
            self.assertIsNone(entity.acn)
            self.assertIsNone(entity.asic_review_source)
            self.assertIsNone(entity.asic_reviewed_at)
            self.assertIsNone(entity.confidence_tier)

    def test_exact_name_resolution_links_only_company_rows_and_leaves_warrants_untouched(self) -> None:
        with self.SessionLocal() as session:
            company_rows = session.scalars(
                select(Holding)
                .where(Holding.raw_name == MARRON_GROUP_HOLDINGS_CANONICAL_NAME)
                .order_by(Holding.source_file_id.asc(), Holding.source_row_number.asc())
            ).all()
            warrant_rows = session.scalars(
                select(Holding)
                .where(Holding.raw_name == MARRON_GROUP_HOLDINGS_WARRANTS_RAW_NAME)
                .order_by(Holding.source_file_id.asc(), Holding.source_row_number.asc())
            ).all()

            self.assertEqual(2, len(company_rows))
            self.assertEqual(2, self.pre_seed_null_entity_count)
            self.assertEqual(2, self.first_resolution_summary.exact_name_auto_links)
            self.assertEqual(0, self.first_resolution_summary.exact_name_ambiguities_queued)
            self.assertEqual(0, self.first_resolution_summary.exact_name_candidates_rejected_due_to_scope_conflict)
            self.assertTrue(all(holding.entity_id == self.entity_id for holding in company_rows))
            self.assertEqual(self.pre_seed_signatures, self._load_marron_signatures(session))

            self.assertEqual(2, len(warrant_rows))
            self.assertEqual(2, self.pre_seed_warrant_null_entity_count)
            self.assertTrue(all(holding.entity_id is None for holding in warrant_rows))

            second_summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            self.assertEqual(0, second_summary.exact_name_auto_links)
            self.assertEqual(2, second_summary.holdings_skipped_prelinked)

            warrant_rows = session.scalars(
                select(Holding)
                .where(Holding.raw_name == MARRON_GROUP_HOLDINGS_WARRANTS_RAW_NAME)
                .order_by(Holding.source_file_id.asc(), Holding.source_row_number.asc())
            ).all()
            self.assertEqual(2, len(warrant_rows))
            self.assertTrue(all(holding.entity_id is None for holding in warrant_rows))

            detail = get_company_detail(session, entity_id=self.entity_id)
            self.assertIsNotNone(detail)
            assert detail is not None

            self.assertEqual(MARRON_GROUP_HOLDINGS_CANONICAL_NAME, detail.canonical_name)
            self.assertEqual("company", detail.entity_type)
            self.assertEqual(["Marron Group Holdings Pty Ltd"], detail.aliases)
            self.assertEqual(["Marron Group Holdings Pty Ltd"], detail.matched_raw_names)
            self.assertEqual(2, detail.observation_count)
            self.assertEqual(1, detail.fund_count)
            self.assertEqual(date(2025, 12, 31), detail.latest_reporting_period)
            self.assertTrue(detail.history_is_limited)
            self.assertEqual("Linked", detail.entity_confidence_label)
            self.assertIsNone(detail.abn)
            self.assertIsNone(detail.registered_name_on_abr)
            self.assertIsNone(detail.acn)
            self.assertIsNone(detail.asic_company_status)
            self.assertIsNone(detail.asic_company_type)
            self.assertIsNone(detail.asic_registration_date)
            self.assertIsNone(detail.asic_next_review_date)
            self.assertIsNone(detail.asic_record_url)
            self.assertIsNone(detail.asic_review_source)
            self.assertIsNone(detail.asic_reviewed_by)
            self.assertIsNone(detail.asic_reviewed_at)

            self.assertEqual(2, len(detail.observations))
            observations_by_option = {row.option_name: row for row in detail.observations}
            self.assertEqual({"Conservative Balanced", "Stable"}, set(observations_by_option))

            stable_observation = observations_by_option["Stable"]
            self.assertEqual("australiansuper", stable_observation.fund_code)
            self.assertEqual("Marron Group Holdings Pty Ltd", stable_observation.raw_name)
            self.assertEqual("ownership_only", stable_observation.disclosure_completeness)
            self.assertEqual(Decimal("0.0006"), stable_observation.ownership_pct)
            self.assertIsNone(stable_observation.value_aud)
            self.assertEqual("unlisted_equity", stable_observation.canonical_asset_class_code)
            self.assertEqual("Unlisted Equity", stable_observation.source_asset_class_raw)
            self.assertEqual("Internally Managed", stable_observation.source_subclass_raw)
            self.assertEqual("Linked", stable_observation.confidence_label)

            conservative_observation = observations_by_option["Conservative Balanced"]
            self.assertEqual("australiansuper", conservative_observation.fund_code)
            self.assertEqual("Marron Group Holdings Pty Ltd", conservative_observation.raw_name)
            self.assertEqual("ownership_only", conservative_observation.disclosure_completeness)
            self.assertEqual(Decimal("0.0015"), conservative_observation.ownership_pct)
            self.assertIsNone(conservative_observation.value_aud)
            self.assertEqual("unlisted_equity", conservative_observation.canonical_asset_class_code)
            self.assertEqual("Unlisted Equity", conservative_observation.source_asset_class_raw)
            self.assertEqual("Internally Managed", conservative_observation.source_subclass_raw)
            self.assertEqual("Linked", conservative_observation.confidence_label)
