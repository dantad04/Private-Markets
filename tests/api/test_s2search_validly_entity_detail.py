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
from app.entity_resolution.s2search_australia_seed import (
    S2SEARCH_AUSTRALIA_CANONICAL_NAME,
    ensure_s2search_australia_seed,
)
from app.entity_resolution.validly_seed import (
    VALIDLY_CANONICAL_NAME,
    ensure_validly_seed,
)
from app.ingest.loader import ingest_australiansuper_local_file


AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()
AUSTRALIANSUPER_CONSERVATIVE_FIXTURE_PATH = Path(
    "tests/fixtures/real/australiansuper/Conservative PHD (1).csv"
).resolve()


class TestS2SearchValidlyEntityDetailApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 's2search_validly_entity_detail.db'}"
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

            s2search_entity = ensure_s2search_australia_seed(session)
            validly_entity = ensure_validly_seed(session)
            cls.entity_ids = {
                S2SEARCH_AUSTRALIA_CANONICAL_NAME: s2search_entity.id,
                VALIDLY_CANONICAL_NAME: validly_entity.id,
            }
            resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def _assert_dependency_only_company_page(self, canonical_name: str) -> None:
        response = self.client.get(f"/admin/ui/companies/{self.entity_ids[canonical_name]}")
        self.assertEqual(200, response.status_code)
        self.assertIn("Named Private Company Ownership Index", response.text)
        self.assertIn(canonical_name, response.text)
        self.assertIn("Confidence: Linked", response.text)
        self.assertIn("Observed holdings", response.text)
        self.assertIn("Private Equity", response.text)
        self.assertIn("Name Only", response.text)
        self.assertIn("2025-12-31", response.text)
        self.assertIn("Only one reporting period is currently available", response.text)
        self.assertIn("No persisted relationships for this company in current stored truth.", response.text)
        self.assertNotIn("ABR reviewed", response.text)
        self.assertNotIn("ASIC cross-reference", response.text)
        self.assertNotIn("ASIC company record", response.text)
        self.assertNotIn("searchText=", response.text)

    def test_s2search_company_page_renders_dependency_only_company_detail(self) -> None:
        self._assert_dependency_only_company_page(S2SEARCH_AUSTRALIA_CANONICAL_NAME)

    def test_validly_company_page_renders_dependency_only_company_detail(self) -> None:
        self._assert_dependency_only_company_page(VALIDLY_CANONICAL_NAME)
