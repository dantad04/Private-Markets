from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import Base, ReportingPeriod
from app.db.session import get_engine
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.entity_resolution.ifm_seed import (
    IFM_CANONICAL_NAME,
    ensure_ifm_art_sunsuper_issuer_relationship,
    ensure_ifm_seed,
)
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


class TestManagerDetailApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'stage3_manager_detail.db'}"
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
            resolve_entities_deterministically(session, reporting_period_id=period.id)
            ensure_ifm_art_sunsuper_issuer_relationship(session, ifm_entity_id=ifm_entity.id)
            session.commit()

            cls.ifm_entity_id = ifm_entity.id

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_manager_detail_endpoint_returns_canonical_ifm_identity_and_aliases(self) -> None:
        response = self.client.get(f"/entities/managers/{self.ifm_entity_id}")
        self.assertEqual(200, response.status_code)

        payload = response.json()
        self.assertEqual(self.ifm_entity_id, payload["entity_id"])
        self.assertEqual(IFM_CANONICAL_NAME, payload["canonical_name"])
        self.assertEqual("manager", payload["entity_type"])
        self.assertEqual(
            {"IFM Investors Pty Ltd", "IFM INVESTORS PTY LIMITED", "IFM Investors"},
            set(payload["aliases"]),
        )
        self.assertEqual(
            {"IFM Investors Pty Ltd", "IFM INVESTORS PTY LIMITED", "IFM Investors"},
            set(payload["matched_raw_names"]),
        )
        self.assertIn("fixed_income", payload["asset_classes"])
        self.assertIn("unlisted_equity", payload["asset_classes"])
        self.assertEqual(["manager", "issuer", "ownership"], payload["role_classes"])

    def test_manager_detail_endpoint_preserves_per_fund_option_period_observations_without_silent_aggregation(self) -> None:
        response = self.client.get(f"/entities/managers/{self.ifm_entity_id}")
        self.assertEqual(200, response.status_code)

        payload = response.json()
        self.assertEqual(10, payload["observation_count"])
        self.assertEqual(4, payload["fund_count"])

        counts_by_fund_option = Counter(
            (row["fund_code"], row["option_name"], row["reporting_period_end_date"])
            for row in payload["observations"]
        )
        self.assertEqual(1, counts_by_fund_option[("art", "ART Stable", "2025-12-31")])
        self.assertEqual(1, counts_by_fund_option[("hostplus", "HC High Growth - Class A Option", "2025-12-31")])
        self.assertEqual(2, counts_by_fund_option[("unisuper", "Conservative", "2025-12-31")])
        self.assertEqual(6, counts_by_fund_option[("australiansuper", "Stable", "2025-12-31")])

    def test_manager_detail_endpoint_preserves_disclosure_completeness_and_honest_observation_kinds(self) -> None:
        response = self.client.get(f"/entities/managers/{self.ifm_entity_id}")
        self.assertEqual(200, response.status_code)

        payload = response.json()
        observations = payload["observations"]

        self.assertTrue(
            any(
                row["fund_code"] == "art"
                and row["option_name"] == "ART Stable"
                and row["raw_name"] == "IFM Investors Pty Ltd"
                and row["disclosure_completeness"] == "value_only"
                and row["observation_kind"] == "manager_rollup"
                for row in observations
            )
        )
        self.assertTrue(
            any(
                row["fund_code"] == "unisuper"
                and row["option_name"] == "Conservative"
                and row["raw_name"] == "IFM INVESTORS PTY LIMITED"
                and row["disclosure_completeness"] == "ownership_only"
                and row["ownership_pct"] == "0.309"
                and row["observation_kind"] == "direct_holding"
                for row in observations
            )
        )
        self.assertTrue(
            any(
                row["fund_code"] == "australiansuper"
                and row["raw_name"] == "IFM Investors"
                and row["disclosure_completeness"] == "name_only"
                and row["source_asset_class_raw"] == "Private Equity"
                and row["observation_kind"] == "unknown"
                for row in observations
            )
        )

    def test_manager_detail_endpoint_does_not_fabricate_relationships(self) -> None:
        response = self.client.get(f"/entities/managers/{self.ifm_entity_id}")
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(["manager", "issuer", "ownership"], payload["role_classes"])
        self.assertEqual([], payload["relationships"])

    def test_manager_detail_admin_ui_renders_same_underlying_data(self) -> None:
        response = self.client.get(f"/admin/ui/managers/{self.ifm_entity_id}")
        self.assertEqual(200, response.status_code)
        self.assertIn("Manager Detail", response.text)
        self.assertIn("IFM Investors Pty Ltd", response.text)
        self.assertIn("IFM INVESTORS PTY LIMITED", response.text)
        self.assertIn("AustralianSuper", response.text)
        self.assertIn("manager", response.text)
        self.assertIn("issuer", response.text)
        self.assertIn("ownership", response.text)
        self.assertIn("manager_rollup", response.text)
        self.assertIn("direct_holding", response.text)
        self.assertIn("unknown", response.text)
        self.assertIn("No persisted entity-to-entity relationships for this manager in current stored truth.", response.text)
