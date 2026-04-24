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
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.entity_resolution.s2search_australia_seed import (
    S2SEARCH_AUSTRALIA_CANONICAL_NAME,
    S2SEARCH_AUSTRALIA_NOTES,
    S2SEARCH_AUSTRALIA_OBSERVED_ALIASES,
    ensure_s2search_australia_seed,
)
from app.entity_resolution.validly_seed import (
    VALIDLY_CANONICAL_NAME,
    VALIDLY_NOTES,
    VALIDLY_OBSERVED_ALIASES,
    ensure_validly_seed,
)
from app.ingest.loader import ingest_australiansuper_local_file
from app.read_models import get_company_detail


AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()
AUSTRALIANSUPER_CONSERVATIVE_FIXTURE_PATH = Path(
    "tests/fixtures/real/australiansuper/Conservative PHD (1).csv"
).resolve()


@dataclass(frozen=True)
class DependencyOnlyCompanyExpectation:
    canonical_name: str
    notes: str
    observed_aliases: tuple[tuple[str, bool], ...]


@dataclass(frozen=True)
class PrivateEquityObservationSignature:
    raw_name: str
    source_file_id: int
    source_row_number: int
    disclosure_completeness: str
    value_aud: str | None
    ownership_pct: str | None
    source_asset_class_raw: str
    source_subclass_raw: str | None


EXPECTATIONS: tuple[DependencyOnlyCompanyExpectation, ...] = (
    DependencyOnlyCompanyExpectation(
        canonical_name=S2SEARCH_AUSTRALIA_CANONICAL_NAME,
        notes=S2SEARCH_AUSTRALIA_NOTES,
        observed_aliases=S2SEARCH_AUSTRALIA_OBSERVED_ALIASES,
    ),
    DependencyOnlyCompanyExpectation(
        canonical_name=VALIDLY_CANONICAL_NAME,
        notes=VALIDLY_NOTES,
        observed_aliases=VALIDLY_OBSERVED_ALIASES,
    ),
)


class TestS2SearchValidlySeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 's2search_validly_seed.db'}"
        cls.engine = get_engine(cls.database_url)
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False, future=True)
        cls.expectations_by_name = {expectation.canonical_name: expectation for expectation in EXPECTATIONS}

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

            cls.pre_seed_signatures = {
                expectation.canonical_name: cls._load_signatures(session, expectation.canonical_name)
                for expectation in EXPECTATIONS
            }
            cls.pre_seed_null_entity_counts = {
                expectation.canonical_name: session.scalar(
                    select(func.count(Holding.id)).where(
                        Holding.raw_name == expectation.canonical_name,
                        Holding.entity_id.is_(None),
                    )
                )
                for expectation in EXPECTATIONS
            }

            s2search_entity = ensure_s2search_australia_seed(session)
            validly_entity = ensure_validly_seed(session)
            cls.entity_ids = {
                S2SEARCH_AUSTRALIA_CANONICAL_NAME: s2search_entity.id,
                VALIDLY_CANONICAL_NAME: validly_entity.id,
            }
            cls.period_id = period.id
            cls.first_resolution_summary = resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        cls.tempdir.cleanup()

    @classmethod
    def _load_signatures(
        cls,
        session,
        raw_name: str,
    ) -> list[PrivateEquityObservationSignature]:
        rows = session.scalars(
            select(Holding)
            .where(Holding.raw_name == raw_name)
            .order_by(Holding.source_file_id.asc(), Holding.source_row_number.asc())
        ).all()
        return [
            PrivateEquityObservationSignature(
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

    def test_canonical_company_seeds_exist_with_exact_observed_aliases_only(self) -> None:
        with self.SessionLocal() as session:
            for expectation in EXPECTATIONS:
                entity = session.get(Entity, self.entity_ids[expectation.canonical_name])
                self.assertIsNotNone(entity)
                assert entity is not None

                self.assertEqual(expectation.canonical_name, entity.canonical_name)
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
                self.assertEqual(expectation.notes, entity.notes)

                aliases = session.scalars(
                    select(EntityAlias.alias)
                    .where(EntityAlias.entity_id == entity.id)
                    .order_by(EntityAlias.alias.asc())
                ).all()
                self.assertEqual(
                    [alias for alias, _is_preferred in expectation.observed_aliases],
                    aliases,
                )

    def test_seed_helpers_are_idempotent_and_do_not_populate_reviewed_identity_or_asic_fields(self) -> None:
        with self.SessionLocal() as session:
            first_s2search = ensure_s2search_australia_seed(session)
            second_s2search = ensure_s2search_australia_seed(session)
            first_validly = ensure_validly_seed(session)
            second_validly = ensure_validly_seed(session)
            session.commit()

            self.assertEqual(first_s2search.id, second_s2search.id)
            self.assertEqual(first_validly.id, second_validly.id)

            for expectation in EXPECTATIONS:
                self.assertEqual(
                    1,
                    session.scalar(
                        select(func.count(Entity.id)).where(
                            Entity.canonical_name == expectation.canonical_name
                        )
                    ),
                )
                entity = session.get(Entity, self.entity_ids[expectation.canonical_name])
                self.assertIsNotNone(entity)
                assert entity is not None
                self.assertIsNone(entity.abn)
                self.assertIsNone(entity.acn)
                self.assertIsNone(entity.asic_review_source)
                self.assertIsNone(entity.asic_reviewed_at)
                self.assertIsNone(entity.confidence_tier)

    def test_exact_name_resolution_links_both_companies_and_company_detail_stays_dependency_only(self) -> None:
        with self.SessionLocal() as session:
            self.assertEqual(4, self.first_resolution_summary.exact_name_auto_links)
            self.assertEqual(0, self.first_resolution_summary.exact_name_ambiguities_queued)
            self.assertEqual(0, self.first_resolution_summary.exact_name_candidates_rejected_due_to_scope_conflict)

            for expectation in EXPECTATIONS:
                rows = session.scalars(
                    select(Holding)
                    .where(Holding.raw_name == expectation.canonical_name)
                    .order_by(Holding.source_file_id.asc(), Holding.source_row_number.asc())
                ).all()

                self.assertEqual(2, len(rows))
                self.assertEqual(2, self.pre_seed_null_entity_counts[expectation.canonical_name])
                self.assertTrue(
                    all(
                        holding.entity_id == self.entity_ids[expectation.canonical_name]
                        for holding in rows
                    )
                )
                self.assertEqual(
                    self.pre_seed_signatures[expectation.canonical_name],
                    self._load_signatures(session, expectation.canonical_name),
                )

            second_summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            self.assertEqual(0, second_summary.exact_name_auto_links)
            self.assertEqual(4, second_summary.holdings_skipped_prelinked)

            for expectation in EXPECTATIONS:
                detail = get_company_detail(
                    session,
                    entity_id=self.entity_ids[expectation.canonical_name],
                )
                self.assertIsNotNone(detail)
                assert detail is not None

                self.assertEqual(expectation.canonical_name, detail.canonical_name)
                self.assertEqual("company", detail.entity_type)
                self.assertEqual([expectation.canonical_name], detail.aliases)
                self.assertEqual([expectation.canonical_name], detail.matched_raw_names)
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
                self.assertEqual(expectation.canonical_name, stable_observation.raw_name)
                self.assertEqual("name_only", stable_observation.disclosure_completeness)
                self.assertIsNone(stable_observation.ownership_pct)
                self.assertIsNone(stable_observation.value_aud)
                self.assertEqual("unlisted_equity", stable_observation.canonical_asset_class_code)
                self.assertEqual("Private Equity", stable_observation.source_asset_class_raw)
                self.assertEqual("Private Equity", stable_observation.source_subclass_raw)
                self.assertEqual("Linked", stable_observation.confidence_label)

                conservative_observation = observations_by_option["Conservative Balanced"]
                self.assertEqual("australiansuper", conservative_observation.fund_code)
                self.assertEqual(expectation.canonical_name, conservative_observation.raw_name)
                self.assertEqual("name_only", conservative_observation.disclosure_completeness)
                self.assertIsNone(conservative_observation.ownership_pct)
                self.assertIsNone(conservative_observation.value_aud)
                self.assertEqual("unlisted_equity", conservative_observation.canonical_asset_class_code)
                self.assertEqual("Private Equity", conservative_observation.source_asset_class_raw)
                self.assertEqual("Private Equity", conservative_observation.source_subclass_raw)
                self.assertEqual("Linked", conservative_observation.confidence_label)
