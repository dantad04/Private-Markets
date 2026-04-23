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
from app.entity_resolution.private_entity_asic_company_register_cross_reference import (
    ASIC_COMPANY_STATUS_REGISTERED,
    ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES,
    ASIC_REVIEWED_AT,
    ASIC_REVIEWED_BY,
    ASIC_REVIEW_SOURCE,
    STAFFORD_CAPITAL_PARTNERS_ACN,
    STAFFORD_CAPITAL_PARTNERS_ASIC_CROSS_REFERENCE,
    STAFFORD_CAPITAL_PARTNERS_ASIC_NEXT_REVIEW_DATE,
    STAFFORD_CAPITAL_PARTNERS_ASIC_REGISTRATION_DATE,
    ensure_stafford_capital_partners_asic_company_register_cross_reference,
)
from app.entity_resolution.stafford_capital_partners_seed import (
    STAFFORD_CAPITAL_PARTNERS_ALIASES,
    STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME,
    STAFFORD_CAPITAL_PARTNERS_CURRENT_LEGAL_ALIAS,
    STAFFORD_CAPITAL_PARTNERS_NOTES,
    STAFFORD_CAPITAL_PARTNERS_REGISTERED_NAME_ON_ABR,
    STAFFORD_CAPITAL_PARTNERS_REVIEWED_ABN,
    STAFFORD_CAPITAL_PARTNERS_REVIEWED_AT,
    STAFFORD_CAPITAL_PARTNERS_REVIEWED_BY,
    STAFFORD_CAPITAL_PARTNERS_REVIEW_SOURCE,
    ensure_stafford_capital_partners_seed,
)
from app.ingest.loader import ingest_australiansuper_local_file
from app.read_models import get_manager_detail


AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()
AUSTRALIANSUPER_CONSERVATIVE_FIXTURE_PATH = Path(
    "tests/fixtures/real/australiansuper/Conservative PHD (1).csv"
).resolve()


@dataclass(frozen=True)
class StaffordObservationSignature:
    raw_name: str
    source_file_id: int
    source_row_number: int
    disclosure_completeness: str
    value_aud: str | None
    value_band_raw: str | None
    ownership_pct: str | None
    source_subclass_raw: str | None


class TestStaffordCapitalPartnersSeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'stafford_capital_partners_seed.db'}"
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

            cls.pre_seed_signatures = cls._load_stafford_signatures(session)
            cls.pre_seed_null_entity_count = session.scalar(
                select(func.count(Holding.id)).where(
                    Holding.raw_name == STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME,
                    Holding.entity_id.is_(None),
                )
            )

            entity = ensure_stafford_capital_partners_seed(session)
            ensure_stafford_capital_partners_asic_company_register_cross_reference(session)
            cls.entity_id = entity.id
            cls.period_id = period.id
            cls.first_resolution_summary = resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        cls.tempdir.cleanup()

    @classmethod
    def _load_stafford_signatures(cls, session) -> list[StaffordObservationSignature]:
        rows = session.scalars(
            select(Holding)
            .where(Holding.raw_name == STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME)
            .order_by(Holding.source_file_id.asc(), Holding.source_row_number.asc())
        ).all()
        return [
            StaffordObservationSignature(
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

    def test_canonical_manager_seed_persists_reviewed_identity_in_place_and_is_idempotent(self) -> None:
        with self.SessionLocal() as session:
            first = ensure_stafford_capital_partners_seed(session)
            second = ensure_stafford_capital_partners_seed(session)
            ensure_stafford_capital_partners_asic_company_register_cross_reference(session)
            ensure_stafford_capital_partners_asic_company_register_cross_reference(session)
            session.commit()

            self.assertEqual(first.id, second.id)
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count(Entity.id)).where(
                        Entity.canonical_name == STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME
                    )
                ),
            )
            self.assertEqual(
                len(STAFFORD_CAPITAL_PARTNERS_ALIASES),
                session.scalar(
                    select(func.count(EntityAlias.id)).where(EntityAlias.entity_id == first.id)
                ),
            )

            entity = session.get(Entity, first.id)
            self.assertIsNotNone(entity)
            assert entity is not None
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME, entity.canonical_name)
            self.assertEqual("manager", entity.entity_type)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_REVIEWED_ABN, entity.abn)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_REVIEW_SOURCE, entity.abn_review_source)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_REVIEWED_BY, entity.abn_reviewed_by)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_REVIEWED_AT, entity.abn_reviewed_at)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_REGISTERED_NAME_ON_ABR, entity.registered_name_on_abr)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_ACN, entity.acn)
            self.assertEqual(ASIC_COMPANY_STATUS_REGISTERED, entity.asic_company_status)
            self.assertEqual(ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES, entity.asic_company_type)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_ASIC_REGISTRATION_DATE, entity.asic_registration_date)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_ASIC_NEXT_REVIEW_DATE, entity.asic_next_review_date)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_ASIC_CROSS_REFERENCE.record_url, entity.asic_record_url)
            self.assertEqual(ASIC_REVIEW_SOURCE, entity.asic_review_source)
            self.assertEqual(ASIC_REVIEWED_BY, entity.asic_reviewed_by)
            self.assertEqual(ASIC_REVIEWED_AT, entity.asic_reviewed_at)
            self.assertEqual("AU", entity.country_code)
            self.assertTrue(entity.is_australian_entity)
            self.assertEqual("seeded", entity.confidence_tier)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_NOTES, entity.notes)

            aliases = session.scalars(
                select(EntityAlias.alias)
                .where(EntityAlias.entity_id == self.entity_id)
                .order_by(EntityAlias.is_preferred.desc(), EntityAlias.alias.asc())
            ).all()
            self.assertEqual(
                [alias for alias, _is_preferred in STAFFORD_CAPITAL_PARTNERS_ALIASES],
                aliases,
            )

    def test_deterministic_resolution_links_current_stafford_rows_without_changing_source_observations(
        self,
    ) -> None:
        with self.SessionLocal() as session:
            rows = session.scalars(
                select(Holding)
                .where(Holding.raw_name == STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME)
                .order_by(Holding.source_file_id.asc(), Holding.source_row_number.asc())
            ).all()

            self.assertEqual(4, len(rows))
            self.assertEqual(4, self.pre_seed_null_entity_count)
            self.assertEqual(4, self.first_resolution_summary.exact_name_auto_links)
            self.assertEqual(0, self.first_resolution_summary.exact_name_ambiguities_queued)
            self.assertEqual(0, self.first_resolution_summary.exact_name_candidates_rejected_due_to_scope_conflict)
            self.assertTrue(all(holding.entity_id == self.entity_id for holding in rows))
            self.assertEqual(self.pre_seed_signatures, self._load_stafford_signatures(session))

            second_summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            self.assertEqual(0, second_summary.exact_name_auto_links)
            self.assertEqual(4, second_summary.holdings_skipped_prelinked)

    def test_manager_detail_renders_reviewed_identity_layer_without_changing_linked_stafford_rows(
        self,
    ) -> None:
        with self.SessionLocal() as session:
            detail = get_manager_detail(session, entity_id=self.entity_id)
            self.assertIsNotNone(detail)
            assert detail is not None

            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME, detail.canonical_name)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_REVIEWED_ABN, detail.abn)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_REVIEW_SOURCE, detail.abn_review_source)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_REVIEWED_BY, detail.abn_reviewed_by)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_REVIEWED_AT, detail.abn_reviewed_at)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_REGISTERED_NAME_ON_ABR, detail.registered_name_on_abr)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_ACN, detail.acn)
            self.assertEqual(ASIC_COMPANY_STATUS_REGISTERED, detail.asic_company_status)
            self.assertEqual(ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES, detail.asic_company_type)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_ASIC_REGISTRATION_DATE, detail.asic_registration_date)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_ASIC_NEXT_REVIEW_DATE, detail.asic_next_review_date)
            self.assertEqual(STAFFORD_CAPITAL_PARTNERS_ASIC_CROSS_REFERENCE.record_url, detail.asic_record_url)
            self.assertEqual(ASIC_REVIEW_SOURCE, detail.asic_review_source)
            self.assertEqual(ASIC_REVIEWED_BY, detail.asic_reviewed_by)
            self.assertEqual(ASIC_REVIEWED_AT, detail.asic_reviewed_at)
            self.assertEqual(
                [
                    STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME,
                    STAFFORD_CAPITAL_PARTNERS_CURRENT_LEGAL_ALIAS,
                ],
                detail.aliases,
            )
            self.assertEqual([STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME], detail.matched_raw_names)
            self.assertEqual("Reviewed", detail.entity_confidence_label)
            self.assertEqual(4, detail.observation_count)
            self.assertEqual(1, detail.fund_count)
            self.assertEqual(["manager"], detail.role_classes)
            self.assertEqual(2, len(detail.primary_observations))
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
                    ("australiansuper", "Stable", 3467, "value_only", "manager_rollup"),
                    ("australiansuper", "Conservative Balanced", 3467, "value_only", "manager_rollup"),
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
                    ("australiansuper", "Stable", 3645, "name_only", "unknown"),
                    ("australiansuper", "Conservative Balanced", 3646, "name_only", "unknown"),
                },
                supplemental_rows,
            )
