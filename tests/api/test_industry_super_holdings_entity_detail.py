from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import Base, Entity, EntityAlias, EntityRelationship, HoldingRelationship, ReportingPeriod
from app.db.session import get_engine
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.entity_resolution.industry_super_holdings_seed import (
    INDUSTRY_SUPER_HOLDINGS_CANONICAL_NAME,
    INDUSTRY_SUPER_HOLDINGS_OBSERVED_ALIASES,
    INDUSTRY_SUPER_HOLDINGS_REGISTERED_NAME_ON_ABR,
    INDUSTRY_SUPER_HOLDINGS_REVIEW_SOURCE,
    INDUSTRY_SUPER_HOLDINGS_REVIEWED_ABN,
    INDUSTRY_SUPER_HOLDINGS_REVIEWED_AT,
    INDUSTRY_SUPER_HOLDINGS_REVIEWED_BY,
    ensure_industry_super_holdings_seed,
)
from app.entity_resolution.private_entity_asic_company_register_cross_reference import (
    ASIC_COMPANY_STATUS_REGISTERED,
    ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES,
    ASIC_REVIEWED_AT,
    ASIC_REVIEWED_BY,
    ASIC_REVIEW_SOURCE,
    INDUSTRY_SUPER_HOLDINGS_ACN,
    INDUSTRY_SUPER_HOLDINGS_ASIC_CROSS_REFERENCE,
    INDUSTRY_SUPER_HOLDINGS_ASIC_NEXT_REVIEW_DATE,
    INDUSTRY_SUPER_HOLDINGS_ASIC_REGISTRATION_DATE,
    ensure_industry_super_holdings_asic_company_register_cross_reference,
)
from app.ingest.loader import (
    ingest_art_qsuper_local_file,
    ingest_art_sunsuper_local_file,
    ingest_australiansuper_local_file,
    ingest_hostplus_local_file,
    ingest_unisuper_local_file,
)


ART_SUNSUPER_FIXTURE_PATH = Path("tests/fixtures/art_sunsuper_synthetic_stable_minimal.csv").resolve()
ART_QSUPER_FIXTURE_PATH = Path("tests/fixtures/art_qsuper_synthetic_balanced_minimal.csv").resolve()
HOSTPLUS_FIXTURE_PATH = Path("tests/fixtures/hostplus_real_extract.csv").resolve()
UNISUPER_FIXTURE_PATH = Path("tests/fixtures/unisuper_real_extract.csv").resolve()
AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()


class TestIndustrySuperHoldingsEntityDetailApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'stage5_industry_super_holdings_entity_detail.db'}"
        cls.engine = get_engine(cls.database_url)
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False, future=True)
        cls.app = create_app()

        def override_get_db_session():
            session = cls.SessionLocal()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        cls.app.dependency_overrides[get_db_session] = override_get_db_session
        cls.client = TestClient(cls.app)

        with cls.SessionLocal() as session:
            period = ReportingPeriod(
                period_end_date=date(2025, 12, 31),
                disclosure_due_date=date(2026, 3, 31),
                label="2025-12-31",
                source_cycle="semi_annual",
            )
            session.add(period)
            session.flush()

            ingest_art_sunsuper_local_file(
                session,
                fund_code="art",
                fund_name="ART",
                file_path=str(ART_SUNSUPER_FIXTURE_PATH),
                reporting_period_id=period.id,
            )
            ingest_art_qsuper_local_file(
                session,
                fund_code="art",
                fund_name="ART",
                file_path=str(ART_QSUPER_FIXTURE_PATH),
                reporting_period_id=period.id,
            )
            ingest_hostplus_local_file(
                session,
                fund_code="hostplus",
                fund_name="Hostplus",
                file_path=str(HOSTPLUS_FIXTURE_PATH),
                reporting_period_id=period.id,
            )
            ingest_unisuper_local_file(
                session,
                fund_code="unisuper",
                fund_name="UniSuper",
                file_path=str(UNISUPER_FIXTURE_PATH),
                reporting_period_id=period.id,
            )
            ingest_australiansuper_local_file(
                session,
                fund_code="australiansuper",
                fund_name="AustralianSuper",
                file_path=str(AUSTRALIANSUPER_STABLE_FIXTURE_PATH),
                reporting_period_id=period.id,
            )
            entity = ensure_industry_super_holdings_seed(session)
            ensure_industry_super_holdings_asic_company_register_cross_reference(session)
            cls.entity_id = entity.id
            resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_industry_super_holdings_seed_persists_reviewed_abn_and_abr_provenance(self) -> None:
        with self.SessionLocal() as session:
            entity = session.get(Entity, self.entity_id)
            self.assertIsNotNone(entity)
            assert entity is not None

            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_CANONICAL_NAME, entity.canonical_name)
            self.assertEqual("company", entity.entity_type)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_REVIEWED_ABN, entity.abn)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_REVIEW_SOURCE, entity.abn_review_source)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_REVIEWED_BY, entity.abn_reviewed_by)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_REVIEWED_AT, entity.abn_reviewed_at)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_REGISTERED_NAME_ON_ABR, entity.registered_name_on_abr)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_ACN, entity.acn)
            self.assertEqual(ASIC_COMPANY_STATUS_REGISTERED, entity.asic_company_status)
            self.assertEqual(ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES, entity.asic_company_type)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_ASIC_REGISTRATION_DATE, entity.asic_registration_date)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_ASIC_NEXT_REVIEW_DATE, entity.asic_next_review_date)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_ASIC_CROSS_REFERENCE.record_url, entity.asic_record_url)
            self.assertEqual(ASIC_REVIEW_SOURCE, entity.asic_review_source)
            self.assertEqual(ASIC_REVIEWED_BY, entity.asic_reviewed_by)
            self.assertEqual(ASIC_REVIEWED_AT, entity.asic_reviewed_at)
            self.assertTrue(entity.is_australian_entity)

    def test_industry_super_holdings_seed_is_idempotent_when_reapplied(self) -> None:
        with self.SessionLocal() as session:
            first = ensure_industry_super_holdings_seed(session)
            second = ensure_industry_super_holdings_seed(session)
            ensure_industry_super_holdings_asic_company_register_cross_reference(session)
            ensure_industry_super_holdings_asic_company_register_cross_reference(session)
            session.commit()

            self.assertEqual(first.id, second.id)
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count(Entity.id)).where(
                        Entity.canonical_name == INDUSTRY_SUPER_HOLDINGS_CANONICAL_NAME
                    )
                ),
            )
            self.assertEqual(
                len(INDUSTRY_SUPER_HOLDINGS_OBSERVED_ALIASES),
                session.scalar(
                    select(func.count(EntityAlias.id)).where(EntityAlias.entity_id == first.id)
                ),
            )

            refreshed = session.get(Entity, first.id)
            self.assertIsNotNone(refreshed)
            assert refreshed is not None
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_REVIEWED_ABN, refreshed.abn)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_REVIEW_SOURCE, refreshed.abn_review_source)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_REVIEWED_BY, refreshed.abn_reviewed_by)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_REVIEWED_AT, refreshed.abn_reviewed_at)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_REGISTERED_NAME_ON_ABR, refreshed.registered_name_on_abr)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_ACN, refreshed.acn)
            self.assertEqual(ASIC_COMPANY_STATUS_REGISTERED, refreshed.asic_company_status)
            self.assertEqual(ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES, refreshed.asic_company_type)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_ASIC_REGISTRATION_DATE, refreshed.asic_registration_date)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_ASIC_NEXT_REVIEW_DATE, refreshed.asic_next_review_date)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_ASIC_CROSS_REFERENCE.record_url, refreshed.asic_record_url)
            self.assertEqual(ASIC_REVIEW_SOURCE, refreshed.asic_review_source)
            self.assertEqual(ASIC_REVIEWED_BY, refreshed.asic_reviewed_by)
            self.assertEqual(ASIC_REVIEWED_AT, refreshed.asic_reviewed_at)
            self.assertEqual(
                0,
                session.scalar(
                    select(func.count(EntityRelationship.id)).where(
                        (EntityRelationship.from_entity_id == first.id)
                        | (EntityRelationship.to_entity_id == first.id)
                    )
                ),
            )
            self.assertEqual(
                0,
                session.scalar(
                    select(func.count(HoldingRelationship.id)).where(
                        HoldingRelationship.related_entity_id == first.id
                    )
                ),
            )

    def test_industry_super_holdings_company_page_renders_reviewed_abn_abr_and_asic_provenance(self) -> None:
        response = self.client.get(f"/admin/ui/companies/{self.entity_id}")
        self.assertEqual(200, response.status_code)
        self.assertIn(INDUSTRY_SUPER_HOLDINGS_CANONICAL_NAME, response.text)
        self.assertIn(INDUSTRY_SUPER_HOLDINGS_REVIEWED_ABN, response.text)
        self.assertIn("ABR reviewed", response.text)
        self.assertIn(INDUSTRY_SUPER_HOLDINGS_REVIEW_SOURCE, response.text)
        self.assertIn(INDUSTRY_SUPER_HOLDINGS_REVIEWED_BY, response.text)
        self.assertIn(INDUSTRY_SUPER_HOLDINGS_REVIEWED_AT.isoformat(), response.text)
        self.assertIn(INDUSTRY_SUPER_HOLDINGS_REGISTERED_NAME_ON_ABR, response.text)
        self.assertIn("ASIC cross-reference", response.text)
        self.assertIn(INDUSTRY_SUPER_HOLDINGS_ACN, response.text)
        self.assertIn(ASIC_COMPANY_STATUS_REGISTERED, response.text)
        self.assertIn(ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES, response.text)
        self.assertIn(ASIC_REVIEW_SOURCE, response.text)
        self.assertIn(ASIC_REVIEWED_BY, response.text)
        self.assertIn(ASIC_REVIEWED_AT.isoformat(), response.text)
        self.assertIn(INDUSTRY_SUPER_HOLDINGS_ASIC_REGISTRATION_DATE.isoformat(), response.text)
        self.assertIn(INDUSTRY_SUPER_HOLDINGS_ASIC_NEXT_REVIEW_DATE.isoformat(), response.text)
        self.assertIn("ASIC company record", response.text)
        self.assertIn("searchText=119748060", response.text)
