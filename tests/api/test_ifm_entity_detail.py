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
from app.db.models import Base, Entity, EntityAlias, ReportingPeriod
from app.db.session import get_engine
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.entity_resolution.ifm_seed import IFM_CANONICAL_NAME, ensure_ifm_seed
from app.ingest.loader import (
    ingest_art_sunsuper_local_file,
    ingest_australiansuper_local_file,
    ingest_hostplus_local_file,
    ingest_unisuper_local_file,
)


ART_SUNSUPER_FIXTURE_PATH = Path("tests/fixtures/art_sunsuper_synthetic_stable_minimal.csv").resolve()
HOSTPLUS_FIXTURE_PATH = Path("tests/fixtures/hostplus_real_extract.csv").resolve()
UNISUPER_FIXTURE_PATH = Path("tests/fixtures/unisuper_real_extract.csv").resolve()
AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()


class TestIfmEntityDetailApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'stage3_ifm_entity_detail.db'}"
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
            ifm_entity = ensure_ifm_seed(session)
            cls.ifm_entity_id = ifm_entity.id
            cls.period_id = period.id
            cls.resolver_summary = resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_ifm_seed_is_idempotent_when_reapplied(self) -> None:
        with self.SessionLocal() as session:
            first = ensure_ifm_seed(session)
            second = ensure_ifm_seed(session)
            session.commit()

            self.assertEqual(first.id, second.id)
            self.assertEqual(1, session.scalar(select(func.count(Entity.id)).where(Entity.canonical_name == IFM_CANONICAL_NAME)))
            self.assertEqual(3, session.scalar(select(func.count(EntityAlias.id)).where(EntityAlias.entity_id == first.id)))

    def test_entity_detail_by_id_returns_ifm_aliases_and_fund_period_counts(self) -> None:
        response = self.client.get(f"/entities/{self.ifm_entity_id}")
        self.assertEqual(200, response.status_code)

        payload = response.json()
        self.assertEqual(self.ifm_entity_id, payload["entity_id"])
        self.assertEqual(IFM_CANONICAL_NAME, payload["canonical_name"])
        self.assertEqual("manager", payload["entity_type"])
        self.assertIsNone(payload["abn"])
        self.assertEqual(
            {"IFM Investors Pty Ltd", "IFM INVESTORS PTY LIMITED", "IFM Investors"},
            set(payload["aliases"]),
        )
        self.assertEqual([], payload["relationships"])

        counts_by_fund = {
            row["fund_code"]: row["observation_count"]
            for row in payload["observed_holdings_count_by_fund_period"]
        }
        self.assertEqual(1, counts_by_fund["art"])
        self.assertEqual(1, counts_by_fund["hostplus"])
        self.assertEqual(2, counts_by_fund["unisuper"])
        self.assertEqual(6, counts_by_fund["australiansuper"])

    def test_cross_adapter_lookup_by_entity_id_returns_ifm_observations_across_aliases(self) -> None:
        response = self.client.get("/entities/cross-adapter", params={"entity_id": self.ifm_entity_id})
        self.assertEqual(200, response.status_code)

        payload = response.json()
        self.assertEqual(self.ifm_entity_id, payload["entity_id"])
        self.assertEqual(IFM_CANONICAL_NAME, payload["lookup_name"])
        self.assertGreaterEqual(payload["fund_count"], 4)
        self.assertGreaterEqual(
            set(payload["matched_raw_names"]),
            {"IFM Investors", "IFM Investors Pty Ltd", "IFM INVESTORS PTY LIMITED"},
        )

        observations_by_fund = {}
        for observation in payload["observations"]:
            observations_by_fund.setdefault(observation["fund_code"], []).append(observation)

        self.assertTrue(
            any(
                row["option_name"] == "ART Stable"
                and row["raw_name"] == "IFM Investors Pty Ltd"
                and row["disclosure_completeness"] == "value_only"
                for row in observations_by_fund["art"]
            )
        )
        self.assertTrue(
            any(
                row["option_name"] == "HC High Growth - Class A Option"
                and row["raw_name"] == "IFM Investors Pty Ltd"
                and row["disclosure_completeness"] == "value_only"
                for row in observations_by_fund["hostplus"]
            )
        )
        self.assertTrue(
            any(
                row["option_name"] == "Conservative"
                and row["raw_name"] == "IFM INVESTORS PTY LIMITED"
                and row["disclosure_completeness"] == "ownership_only"
                for row in observations_by_fund["unisuper"]
            )
        )
        self.assertTrue(
            any(
                row["option_name"] == "Stable"
                and row["raw_name"] == "IFM Investors"
                and row["disclosure_completeness"] == "value_only"
                for row in observations_by_fund["australiansuper"]
            )
        )
