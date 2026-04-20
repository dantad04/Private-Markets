from __future__ import annotations

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


class TestCrossAdapterReadModelApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'stage3_cross_adapter.db'}"
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
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_cross_adapter_lookup_uses_exact_conservative_normalized_name_for_ifm(self) -> None:
        response = self.client.get("/entities/cross-adapter", params={"name": "IFM Investors"})
        self.assertEqual(200, response.status_code)

        payload = response.json()
        self.assertEqual("IFM Investors", payload["lookup_name"])
        self.assertEqual("ifm investors", payload["normalized_lookup_name"])
        self.assertEqual(1, payload["fund_count"])
        self.assertEqual(
            {"IFM Investors"},
            set(payload["matched_raw_names"]),
        )
        self.assertTrue(all(observation["raw_name"] == "IFM Investors" for observation in payload["observations"]))
        self.assertTrue(all(observation["fund_code"] == "australiansuper" for observation in payload["observations"]))
        self.assertTrue(
            any(
                observation["option_name"] == "Stable"
                and observation["disclosure_completeness"] == "value_only"
                and observation["value_aud"] == "216358991"
                and observation["value_band_raw"] == "$100m to $300m"
                for observation in payload["observations"]
            )
        )

    def test_cross_adapter_lookup_uses_exact_conservative_normalized_name_for_industry_super_holdings(self) -> None:
        response = self.client.get("/entities/cross-adapter", params={"name": "Industry Super Holdings"})
        self.assertEqual(200, response.status_code)

        payload = response.json()
        self.assertEqual("industry super holdings", payload["normalized_lookup_name"])
        self.assertEqual(1, payload["fund_count"])
        self.assertEqual(
            ["Industry Super Holdings"],
            payload["matched_raw_names"],
        )
        self.assertEqual(1, payload["observation_count"])
        observation = payload["observations"][0]
        self.assertEqual("hostplus", observation["fund_code"])
        self.assertEqual("HC High Growth - Class A Option", observation["option_name"])
        self.assertEqual("ownership_only", observation["disclosure_completeness"])
        self.assertEqual("0.1317", observation["ownership_pct"])

    def test_cross_adapter_admin_ui_renders_strict_name_lookup_table(self) -> None:
        response = self.client.get("/admin/ui/cross-adapter", params={"name": "IFM Investors"})
        self.assertEqual(200, response.status_code)
        self.assertIn("Cross-Adapter Lookup", response.text)
        self.assertIn("IFM Investors", response.text)
        self.assertIn("AustralianSuper", response.text)
        self.assertNotIn("IFM INVESTORS PTY LIMITED", response.text)
