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
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.entity_resolution.ifm_seed import ensure_ifm_seed
from app.entity_resolution.industry_super_holdings_seed import ensure_industry_super_holdings_seed
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


class TestSearchApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'stage4_search.db'}"
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
            cls.ifm_entity_id = ensure_ifm_seed(session).id
            cls.industry_super_entity_id = ensure_industry_super_holdings_seed(session).id
            resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_search_api_returns_fund_results_for_code_and_name_queries(self) -> None:
        response = self.client.get("/search", params={"q": "art"})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("art", payload["query"])
        self.assertGreaterEqual(payload["result_count"], 1)
        self.assertEqual("fund", payload["results"][0]["result_kind"])
        self.assertEqual("art", payload["results"][0]["fund_code"])
        self.assertEqual("fund_code", payload["results"][0]["matched_on"])

        response = self.client.get("/search", params={"q": "AustralianSuper"})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(
            any(
                result["result_kind"] == "fund"
                and result["title"] == "AustralianSuper"
                and result["matched_on"] in {"fund_code", "fund_name"}
                and result["fund_code"] == "australiansuper"
                for result in payload["results"]
            )
        )

    def test_search_api_returns_company_results_for_canonical_and_alias_queries(self) -> None:
        response = self.client.get("/search", params={"q": "Industry Super Holdings Pty Ltd"})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(
            any(
                result["result_kind"] == "company"
                and result["title"] == "Industry Super Holdings Pty Ltd"
                and result["matched_on"] == "canonical_name"
                and result["entity_id"] == self.industry_super_entity_id
                for result in payload["results"]
            )
        )

        response = self.client.get("/search", params={"q": "Industry Super Holdings"})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(
            any(
                result["result_kind"] == "company"
                and result["title"] == "Industry Super Holdings Pty Ltd"
                and result["matched_on"] == "alias"
                and result["matched_value"] == "Industry Super Holdings"
                and result["entity_id"] == self.industry_super_entity_id
                for result in payload["results"]
            )
        )

    def test_search_api_returns_manager_results_for_canonical_and_alias_queries(self) -> None:
        response = self.client.get("/search", params={"q": "IFM Investors Pty Ltd"})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(
            any(
                result["result_kind"] == "manager"
                and result["title"] == "IFM Investors Pty Ltd"
                and result["matched_on"] == "canonical_name"
                and result["entity_id"] == self.ifm_entity_id
                for result in payload["results"]
            )
        )

        response = self.client.get("/search", params={"q": "IFM INVESTORS PTY LIMITED"})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertTrue(
            any(
                result["result_kind"] == "manager"
                and result["title"] == "IFM Investors Pty Ltd"
                and result["matched_on"] == "alias"
                and result["matched_value"] == "IFM INVESTORS PTY LIMITED"
                and result["entity_id"] == self.ifm_entity_id
                for result in payload["results"]
            )
        )

    def test_search_api_kind_filter_limits_results_and_reports_counts(self) -> None:
        response = self.client.get("/search", params={"q": "super", "kind": "company"})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("company", payload["active_kind"])
        self.assertGreater(payload["kind_counts"]["company"], 0)
        self.assertGreater(payload["kind_counts"]["fund"], 0)
        self.assertGreater(payload["total_result_count"], payload["result_count"])
        self.assertTrue(payload["results"])
        self.assertTrue(all(result["result_kind"] == "company" for result in payload["results"]))

    def test_search_admin_ui_renders_alias_results_and_detail_links(self) -> None:
        response = self.client.get("/admin/ui/search", params={"q": "Industry Super Holdings"})
        self.assertEqual(200, response.status_code)
        self.assertIn("Stage 4 search slice", response.text)
        self.assertIn("Industry Super Holdings Pty Ltd", response.text)
        self.assertIn("Alias", response.text)
        self.assertIn("Open company", response.text)
        self.assertIn(f"/admin/ui/companies/{self.industry_super_entity_id}", response.text)

    def test_search_admin_ui_renders_scope_filters_and_filtered_results(self) -> None:
        response = self.client.get("/admin/ui/search", params={"q": "super", "kind": "company"})
        self.assertEqual(200, response.status_code)
        self.assertIn("All results", response.text)
        self.assertIn("Companies", response.text)
        self.assertIn("Funds", response.text)
        self.assertIn("Managers", response.text)
        self.assertIn("Scope Companies", response.text)
        self.assertIn("Industry Super Holdings Pty Ltd", response.text)
        self.assertNotIn("/admin/ui/funds/australiansuper", response.text)
