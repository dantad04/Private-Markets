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
from app.entity_resolution.marron_group_holdings_seed import (
    MARRON_GROUP_HOLDINGS_CANONICAL_NAME,
    ensure_marron_group_holdings_seed,
)
from app.entity_resolution.private_entity_asic_company_register_cross_reference import (
    ASIC_COMPANY_STATUS_REGISTERED,
    ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES,
    ASIC_REVIEWED_BY,
    ASIC_REVIEW_SOURCE,
    MARRON_GROUP_HOLDINGS_ABN,
    MARRON_GROUP_HOLDINGS_ACN,
    MARRON_GROUP_HOLDINGS_ASIC_NEXT_REVIEW_DATE,
    MARRON_GROUP_HOLDINGS_ASIC_REGISTRATION_DATE,
    MARRON_GROUP_HOLDINGS_ASIC_REVIEWED_AT,
    ensure_marron_group_holdings_asic_company_register_cross_reference,
)
from app.ingest.loader import ingest_australiansuper_local_file


AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()
AUSTRALIANSUPER_CONSERVATIVE_FIXTURE_PATH = Path(
    "tests/fixtures/real/australiansuper/Conservative PHD (1).csv"
).resolve()


class TestMarronGroupHoldingsEntityDetailApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'marron_group_holdings_entity_detail.db'}"
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
            entity = ensure_marron_group_holdings_seed(session)
            ensure_marron_group_holdings_asic_company_register_cross_reference(session)
            cls.entity_id = entity.id
            resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_marron_company_page_renders_asic_cross_reference_without_warrant_or_scope_drift(self) -> None:
        response = self.client.get(f"/admin/ui/companies/{self.entity_id}")
        self.assertEqual(200, response.status_code)
        self.assertIn(MARRON_GROUP_HOLDINGS_CANONICAL_NAME, response.text)
        self.assertIn("Linked", response.text)
        self.assertIn("2025-12-31", response.text)
        self.assertIn(MARRON_GROUP_HOLDINGS_ABN, response.text)
        self.assertIn(MARRON_GROUP_HOLDINGS_ACN, response.text)
        self.assertIn("ASIC cross-reference", response.text)
        self.assertIn(ASIC_COMPANY_STATUS_REGISTERED, response.text)
        self.assertIn(ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES, response.text)
        self.assertIn(ASIC_REVIEW_SOURCE, response.text)
        self.assertIn(ASIC_REVIEWED_BY, response.text)
        self.assertIn(MARRON_GROUP_HOLDINGS_ASIC_REVIEWED_AT.isoformat(), response.text)
        self.assertIn(MARRON_GROUP_HOLDINGS_ASIC_REGISTRATION_DATE.isoformat(), response.text)
        self.assertIn(MARRON_GROUP_HOLDINGS_ASIC_NEXT_REVIEW_DATE.isoformat(), response.text)
        self.assertIn("ASIC company record", response.text)
        self.assertIn("searchText=631941403", response.text)
        self.assertIn("No persisted relationships for this company in current stored truth.", response.text)
        self.assertNotIn("ABR reviewed", response.text)
        self.assertNotIn("Marron Group Holdings Pty Ltd Unissued Warrants", response.text)
        self.assertNotIn("MELBOURNE VIC 3000", response.text)
        self.assertNotIn("BGH HOLDCO A PTY LTD", response.text)
        self.assertNotIn("MARRON GROUP HOLDINGS PTY LTD", response.text)
