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
from app.entity_resolution.athena_financial_seed import (
    ATHENA_FINANCIAL_CANONICAL_NAME,
    ATHENA_FINANCIAL_NOTES,
    ATHENA_FINANCIAL_OBSERVED_ALIASES,
    ensure_athena_financial_seed,
)
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.entity_resolution.private_entity_asic_company_register_cross_reference import (
    ASIC_COMPANY_STATUS_REGISTERED,
    ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES,
    ASIC_REVIEWED_BY,
    ASIC_REVIEW_SOURCE,
    ATHENA_FINANCIAL_ABN,
    ATHENA_FINANCIAL_ACN,
    ATHENA_FINANCIAL_ASIC_CROSS_REFERENCE,
    ATHENA_FINANCIAL_ASIC_NEXT_REVIEW_DATE,
    ATHENA_FINANCIAL_ASIC_REGISTRATION_DATE,
    ATHENA_FINANCIAL_ASIC_REVIEWED_AT,
    ensure_athena_financial_asic_company_register_cross_reference,
)
from app.ingest.loader import ingest_australiansuper_local_file
from app.read_models import get_company_detail


AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()
AUSTRALIANSUPER_CONSERVATIVE_FIXTURE_PATH = Path(
    "tests/fixtures/real/australiansuper/Conservative PHD (1).csv"
).resolve()


@dataclass(frozen=True)
class AthenaFinancialObservationSignature:
    raw_name: str
    source_file_id: int
    source_row_number: int
    disclosure_completeness: str
    value_aud: str | None
    ownership_pct: str | None
    source_asset_class_raw: str
    source_subclass_raw: str | None


class TestAthenaFinancialSeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'athena_financial_seed.db'}"
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

            cls.pre_seed_signatures = cls._load_athena_signatures(session)
            cls.pre_seed_null_entity_count = session.scalar(
                select(func.count(Holding.id)).where(
                    Holding.raw_name == ATHENA_FINANCIAL_CANONICAL_NAME,
                    Holding.entity_id.is_(None),
                )
            )

            entity = ensure_athena_financial_seed(session)
            cls.entity_id = entity.id
            cls.period_id = period.id
            cls.first_resolution_summary = resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        cls.tempdir.cleanup()

    @classmethod
    def _load_athena_signatures(cls, session) -> list[AthenaFinancialObservationSignature]:
        rows = session.scalars(
            select(Holding)
            .where(Holding.raw_name == ATHENA_FINANCIAL_CANONICAL_NAME)
            .order_by(Holding.source_file_id.asc(), Holding.source_row_number.asc())
        ).all()
        return [
            AthenaFinancialObservationSignature(
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

            self.assertEqual(ATHENA_FINANCIAL_CANONICAL_NAME, entity.canonical_name)
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
            self.assertEqual(ATHENA_FINANCIAL_NOTES, entity.notes)

            aliases = session.scalars(
                select(EntityAlias.alias)
                .where(EntityAlias.entity_id == self.entity_id)
                .order_by(EntityAlias.alias.asc())
            ).all()
            self.assertEqual(
                [alias for alias, _is_preferred in ATHENA_FINANCIAL_OBSERVED_ALIASES],
                aliases,
            )

    def test_seed_is_idempotent_and_does_not_populate_reviewed_identity_or_asic_fields(self) -> None:
        with self.SessionLocal() as session:
            first = ensure_athena_financial_seed(session)
            second = ensure_athena_financial_seed(session)
            session.commit()

            self.assertEqual(first.id, second.id)
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count(Entity.id)).where(
                        Entity.canonical_name == ATHENA_FINANCIAL_CANONICAL_NAME
                    )
                ),
            )
            self.assertEqual(
                len(ATHENA_FINANCIAL_OBSERVED_ALIASES),
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

    def test_exact_name_resolution_links_athena_and_company_detail_stays_dependency_only(self) -> None:
        with self.SessionLocal() as session:
            rows = session.scalars(
                select(Holding)
                .where(Holding.raw_name == ATHENA_FINANCIAL_CANONICAL_NAME)
                .order_by(Holding.source_file_id.asc(), Holding.source_row_number.asc())
            ).all()

            self.assertEqual(4, len(rows))
            self.assertEqual(4, self.pre_seed_null_entity_count)
            self.assertEqual(4, self.first_resolution_summary.exact_name_auto_links)
            self.assertEqual(0, self.first_resolution_summary.exact_name_ambiguities_queued)
            self.assertEqual(0, self.first_resolution_summary.exact_name_candidates_rejected_due_to_scope_conflict)
            self.assertTrue(all(holding.entity_id == self.entity_id for holding in rows))
            self.assertEqual(self.pre_seed_signatures, self._load_athena_signatures(session))

            second_summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            self.assertEqual(0, second_summary.exact_name_auto_links)
            self.assertEqual(4, second_summary.holdings_skipped_prelinked)

            detail = get_company_detail(session, entity_id=self.entity_id)
            self.assertIsNotNone(detail)
            assert detail is not None

            self.assertEqual(ATHENA_FINANCIAL_CANONICAL_NAME, detail.canonical_name)
            self.assertEqual("company", detail.entity_type)
            self.assertEqual(["Athena Financial Pty Ltd"], detail.aliases)
            self.assertEqual(["Athena Financial Pty Ltd"], detail.matched_raw_names)
            self.assertEqual(4, detail.observation_count)
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

            observations_by_option = {}
            for observation in detail.observations:
                observations_by_option.setdefault(observation.option_name, []).append(observation)

            self.assertEqual({"Conservative Balanced", "Stable"}, set(observations_by_option))
            self.assertEqual(2, len(observations_by_option["Stable"]))
            self.assertEqual(2, len(observations_by_option["Conservative Balanced"]))

            stable_rows = sorted(
                observations_by_option["Stable"],
                key=lambda observation: (
                    observation.disclosure_completeness,
                    observation.source_subclass_raw or "",
                ),
            )
            stable_name_only = stable_rows[0]
            stable_ownership_only = stable_rows[1]

            self.assertEqual("Athena Financial Pty Ltd", stable_name_only.raw_name)
            self.assertEqual("name_only", stable_name_only.disclosure_completeness)
            self.assertIsNone(stable_name_only.ownership_pct)
            self.assertIsNone(stable_name_only.value_aud)
            self.assertEqual("unlisted_equity", stable_name_only.canonical_asset_class_code)
            self.assertEqual("Private Equity", stable_name_only.source_asset_class_raw)
            self.assertEqual("Private Equity", stable_name_only.source_subclass_raw)
            self.assertEqual("Linked", stable_name_only.confidence_label)

            self.assertEqual("Athena Financial Pty Ltd", stable_ownership_only.raw_name)
            self.assertEqual("ownership_only", stable_ownership_only.disclosure_completeness)
            self.assertEqual(Decimal("0.0002"), stable_ownership_only.ownership_pct)
            self.assertIsNone(stable_ownership_only.value_aud)
            self.assertEqual("unlisted_equity", stable_ownership_only.canonical_asset_class_code)
            self.assertEqual("Unlisted Equity", stable_ownership_only.source_asset_class_raw)
            self.assertEqual("Internally Managed", stable_ownership_only.source_subclass_raw)
            self.assertEqual("Linked", stable_ownership_only.confidence_label)

            conservative_rows = sorted(
                observations_by_option["Conservative Balanced"],
                key=lambda observation: (
                    observation.disclosure_completeness,
                    observation.source_subclass_raw or "",
                ),
            )
            conservative_name_only = conservative_rows[0]
            conservative_ownership_only = conservative_rows[1]

            self.assertEqual("Athena Financial Pty Ltd", conservative_name_only.raw_name)
            self.assertEqual("name_only", conservative_name_only.disclosure_completeness)
            self.assertIsNone(conservative_name_only.ownership_pct)
            self.assertIsNone(conservative_name_only.value_aud)
            self.assertEqual("unlisted_equity", conservative_name_only.canonical_asset_class_code)
            self.assertEqual("Private Equity", conservative_name_only.source_asset_class_raw)
            self.assertEqual("Private Equity", conservative_name_only.source_subclass_raw)
            self.assertEqual("Linked", conservative_name_only.confidence_label)

            self.assertEqual("Athena Financial Pty Ltd", conservative_ownership_only.raw_name)
            self.assertEqual("ownership_only", conservative_ownership_only.disclosure_completeness)
            self.assertEqual(Decimal("0.0006"), conservative_ownership_only.ownership_pct)
            self.assertIsNone(conservative_ownership_only.value_aud)
            self.assertEqual("unlisted_equity", conservative_ownership_only.canonical_asset_class_code)
            self.assertEqual("Unlisted Equity", conservative_ownership_only.source_asset_class_raw)
            self.assertEqual("Internally Managed", conservative_ownership_only.source_subclass_raw)
            self.assertEqual("Linked", conservative_ownership_only.confidence_label)


class TestAthenaFinancialAsicCrossReference(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'athena_financial_asic_cross_reference.db'}"
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

            cls.pre_seed_signatures = TestAthenaFinancialSeed._load_athena_signatures(session)
            cls.pre_seed_null_entity_count = session.scalar(
                select(func.count(Holding.id)).where(
                    Holding.raw_name == ATHENA_FINANCIAL_CANONICAL_NAME,
                    Holding.entity_id.is_(None),
                )
            )

            entity = ensure_athena_financial_seed(session)
            ensure_athena_financial_asic_company_register_cross_reference(session)
            cls.entity_id = entity.id
            cls.period_id = period.id
            cls.first_resolution_summary = resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_canonical_company_seed_persists_asic_cross_reference_without_abr_review_layer(self) -> None:
        with self.SessionLocal() as session:
            entity = session.get(Entity, self.entity_id)
            self.assertIsNotNone(entity)
            assert entity is not None

            self.assertEqual(ATHENA_FINANCIAL_CANONICAL_NAME, entity.canonical_name)
            self.assertEqual("company", entity.entity_type)
            self.assertEqual(ATHENA_FINANCIAL_ABN, entity.abn)
            self.assertIsNone(entity.abn_review_source)
            self.assertIsNone(entity.registered_name_on_abr)
            self.assertEqual(ATHENA_FINANCIAL_ACN, entity.acn)
            self.assertEqual(ASIC_COMPANY_STATUS_REGISTERED, entity.asic_company_status)
            self.assertEqual(ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES, entity.asic_company_type)
            self.assertEqual(ATHENA_FINANCIAL_ASIC_REGISTRATION_DATE, entity.asic_registration_date)
            self.assertEqual(ATHENA_FINANCIAL_ASIC_NEXT_REVIEW_DATE, entity.asic_next_review_date)
            self.assertEqual(ATHENA_FINANCIAL_ASIC_CROSS_REFERENCE.record_url, entity.asic_record_url)
            self.assertEqual(ASIC_REVIEW_SOURCE, entity.asic_review_source)
            self.assertEqual(ASIC_REVIEWED_BY, entity.asic_reviewed_by)
            self.assertEqual(ATHENA_FINANCIAL_ASIC_REVIEWED_AT, entity.asic_reviewed_at)
            self.assertEqual("AU", entity.country_code)
            self.assertTrue(entity.is_australian_entity)
            self.assertIsNone(entity.confidence_tier)
            self.assertEqual(ATHENA_FINANCIAL_NOTES, entity.notes)

            aliases = session.scalars(
                select(EntityAlias.alias)
                .where(EntityAlias.entity_id == self.entity_id)
                .order_by(EntityAlias.alias.asc())
            ).all()
            self.assertEqual(
                [alias for alias, _is_preferred in ATHENA_FINANCIAL_OBSERVED_ALIASES],
                aliases,
            )

    def test_seed_is_idempotent_and_reapplies_only_athena_asic_fields(self) -> None:
        with self.SessionLocal() as session:
            first = ensure_athena_financial_seed(session)
            second = ensure_athena_financial_seed(session)
            ensure_athena_financial_asic_company_register_cross_reference(session)
            ensure_athena_financial_asic_company_register_cross_reference(session)
            session.commit()

            self.assertEqual(first.id, second.id)
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count(Entity.id)).where(
                        Entity.canonical_name == ATHENA_FINANCIAL_CANONICAL_NAME
                    )
                ),
            )
            self.assertEqual(
                len(ATHENA_FINANCIAL_OBSERVED_ALIASES),
                session.scalar(
                    select(func.count(EntityAlias.id)).where(EntityAlias.entity_id == first.id)
                ),
            )

            entity = session.get(Entity, first.id)
            self.assertIsNotNone(entity)
            assert entity is not None
            self.assertEqual(ATHENA_FINANCIAL_ABN, entity.abn)
            self.assertIsNone(entity.abn_review_source)
            self.assertIsNone(entity.registered_name_on_abr)
            self.assertEqual(ATHENA_FINANCIAL_ACN, entity.acn)
            self.assertEqual(ATHENA_FINANCIAL_ASIC_CROSS_REFERENCE.record_url, entity.asic_record_url)
            self.assertEqual(ASIC_REVIEW_SOURCE, entity.asic_review_source)
            self.assertEqual(ATHENA_FINANCIAL_ASIC_REVIEWED_AT, entity.asic_reviewed_at)
            self.assertIsNone(entity.confidence_tier)

    def test_exact_name_resolution_links_athena_and_company_detail_stays_honest_with_asic_only_slice(self) -> None:
        with self.SessionLocal() as session:
            rows = session.scalars(
                select(Holding)
                .where(Holding.raw_name == ATHENA_FINANCIAL_CANONICAL_NAME)
                .order_by(Holding.source_file_id.asc(), Holding.source_row_number.asc())
            ).all()

            self.assertEqual(4, len(rows))
            self.assertEqual(4, self.pre_seed_null_entity_count)
            self.assertEqual(4, self.first_resolution_summary.exact_name_auto_links)
            self.assertEqual(0, self.first_resolution_summary.exact_name_ambiguities_queued)
            self.assertEqual(0, self.first_resolution_summary.exact_name_candidates_rejected_due_to_scope_conflict)
            self.assertTrue(all(holding.entity_id == self.entity_id for holding in rows))
            self.assertEqual(self.pre_seed_signatures, TestAthenaFinancialSeed._load_athena_signatures(session))

            second_summary = resolve_entities_deterministically(session, reporting_period_id=self.period_id)
            session.commit()

            self.assertEqual(0, second_summary.exact_name_auto_links)
            self.assertEqual(4, second_summary.holdings_skipped_prelinked)

            detail = get_company_detail(session, entity_id=self.entity_id)
            self.assertIsNotNone(detail)
            assert detail is not None

            self.assertEqual(ATHENA_FINANCIAL_CANONICAL_NAME, detail.canonical_name)
            self.assertEqual("company", detail.entity_type)
            self.assertEqual(["Athena Financial Pty Ltd"], detail.aliases)
            self.assertEqual(["Athena Financial Pty Ltd"], detail.matched_raw_names)
            self.assertEqual(4, detail.observation_count)
            self.assertEqual(1, detail.fund_count)
            self.assertEqual(date(2025, 12, 31), detail.latest_reporting_period)
            self.assertTrue(detail.history_is_limited)
            self.assertEqual("Linked", detail.entity_confidence_label)
            self.assertEqual(ATHENA_FINANCIAL_ABN, detail.abn)
            self.assertIsNone(detail.abn_review_source)
            self.assertIsNone(detail.registered_name_on_abr)
            self.assertEqual(ATHENA_FINANCIAL_ACN, detail.acn)
            self.assertEqual(ASIC_COMPANY_STATUS_REGISTERED, detail.asic_company_status)
            self.assertEqual(ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES, detail.asic_company_type)
            self.assertEqual(ATHENA_FINANCIAL_ASIC_REGISTRATION_DATE, detail.asic_registration_date)
            self.assertEqual(ATHENA_FINANCIAL_ASIC_NEXT_REVIEW_DATE, detail.asic_next_review_date)
            self.assertEqual(ATHENA_FINANCIAL_ASIC_CROSS_REFERENCE.record_url, detail.asic_record_url)
            self.assertEqual(ASIC_REVIEW_SOURCE, detail.asic_review_source)
            self.assertEqual(ASIC_REVIEWED_BY, detail.asic_reviewed_by)
            self.assertEqual(ATHENA_FINANCIAL_ASIC_REVIEWED_AT, detail.asic_reviewed_at)

            observations_by_option = {}
            for observation in detail.observations:
                observations_by_option.setdefault(observation.option_name, []).append(observation)

            self.assertEqual({"Conservative Balanced", "Stable"}, set(observations_by_option))
            self.assertEqual(2, len(observations_by_option["Stable"]))
            self.assertEqual(2, len(observations_by_option["Conservative Balanced"]))

            stable_rows = sorted(
                observations_by_option["Stable"],
                key=lambda observation: (
                    observation.disclosure_completeness,
                    observation.source_subclass_raw or "",
                ),
            )
            stable_name_only = stable_rows[0]
            stable_ownership_only = stable_rows[1]

            self.assertEqual("Athena Financial Pty Ltd", stable_name_only.raw_name)
            self.assertEqual("name_only", stable_name_only.disclosure_completeness)
            self.assertIsNone(stable_name_only.ownership_pct)
            self.assertIsNone(stable_name_only.value_aud)
            self.assertEqual("unlisted_equity", stable_name_only.canonical_asset_class_code)
            self.assertEqual("Private Equity", stable_name_only.source_asset_class_raw)
            self.assertEqual("Private Equity", stable_name_only.source_subclass_raw)
            self.assertEqual("Linked", stable_name_only.confidence_label)

            self.assertEqual("Athena Financial Pty Ltd", stable_ownership_only.raw_name)
            self.assertEqual("ownership_only", stable_ownership_only.disclosure_completeness)
            self.assertEqual(Decimal("0.0002"), stable_ownership_only.ownership_pct)
            self.assertIsNone(stable_ownership_only.value_aud)
            self.assertEqual("unlisted_equity", stable_ownership_only.canonical_asset_class_code)
            self.assertEqual("Unlisted Equity", stable_ownership_only.source_asset_class_raw)
            self.assertEqual("Internally Managed", stable_ownership_only.source_subclass_raw)
            self.assertEqual("Linked", stable_ownership_only.confidence_label)

            conservative_rows = sorted(
                observations_by_option["Conservative Balanced"],
                key=lambda observation: (
                    observation.disclosure_completeness,
                    observation.source_subclass_raw or "",
                ),
            )
            conservative_name_only = conservative_rows[0]
            conservative_ownership_only = conservative_rows[1]

            self.assertEqual("Athena Financial Pty Ltd", conservative_name_only.raw_name)
            self.assertEqual("name_only", conservative_name_only.disclosure_completeness)
            self.assertIsNone(conservative_name_only.ownership_pct)
            self.assertIsNone(conservative_name_only.value_aud)
            self.assertEqual("unlisted_equity", conservative_name_only.canonical_asset_class_code)
            self.assertEqual("Private Equity", conservative_name_only.source_asset_class_raw)
            self.assertEqual("Private Equity", conservative_name_only.source_subclass_raw)
            self.assertEqual("Linked", conservative_name_only.confidence_label)

            self.assertEqual("Athena Financial Pty Ltd", conservative_ownership_only.raw_name)
            self.assertEqual("ownership_only", conservative_ownership_only.disclosure_completeness)
            self.assertEqual(Decimal("0.0006"), conservative_ownership_only.ownership_pct)
            self.assertIsNone(conservative_ownership_only.value_aud)
            self.assertEqual("unlisted_equity", conservative_ownership_only.canonical_asset_class_code)
            self.assertEqual("Unlisted Equity", conservative_ownership_only.source_asset_class_raw)
            self.assertEqual("Internally Managed", conservative_ownership_only.source_subclass_raw)
            self.assertEqual("Linked", conservative_ownership_only.confidence_label)
