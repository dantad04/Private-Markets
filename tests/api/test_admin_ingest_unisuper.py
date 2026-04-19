from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import Base, ReportingPeriod, SourceFile
from app.db.session import get_engine
from app.ingest.governance import UNISUPER_MAPPING_VERSION_ID


FIXTURE_PATH = Path("tests/fixtures/unisuper_real_extract.csv").resolve()


class TestAdminUniSuperIngestEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_unisuper_api.db'}"
        self.engine = get_engine(self.database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)
        self.app = create_app()

        def override_get_db_session():
            session = self.SessionLocal()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        self.app.dependency_overrides[get_db_session] = override_get_db_session
        self.client = TestClient(self.app)

        with self.SessionLocal() as session:
            period = ReportingPeriod(
                period_end_date=date(2025, 12, 31),
                disclosure_due_date=date(2026, 3, 31),
                label="2025-12-31",
                source_cycle="semi_annual",
            )
            session.add(period)
            session.commit()
            self.reporting_period_id = period.id

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_admin_ingest_local_file_unisuper_endpoint(self) -> None:
        response = self.client.post(
            "/admin/ingest/local-file/unisuper",
            json={
                "file_path": str(FIXTURE_PATH),
                "fund_code": "unisuper",
                "fund_name": "UniSuper",
                "reporting_period_id": self.reporting_period_id,
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(3810, payload["rows_staged"])
        self.assertEqual(3810, payload["rows_inserted"])
        self.assertIsNone(payload["investment_option_id"])

        with self.SessionLocal() as session:
            source_file = session.get(SourceFile, payload["source_file_id"])
            self.assertEqual("UniSuperPhdStateMachineAdapter", source_file.adapter_key)
            self.assertEqual(UNISUPER_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertIsNone(source_file.investment_option_id)

        listing = self.client.get("/admin/source-files")
        self.assertEqual(200, listing.status_code)
        self.assertEqual("UniSuperPhdStateMachineAdapter", listing.json()[0]["adapter_key"])
        self.assertEqual(3810, listing.json()[0]["rows_loaded"])

        detail_first_page = self.client.get(f"/admin/source-files/{payload['source_file_id']}", params={"page": 1, "size": 200})
        self.assertEqual(200, detail_first_page.status_code)
        self.assertEqual("Conservative", detail_first_page.json()["holdings"][0]["source_option_name"])

        detail_last_page = self.client.get(
            f"/admin/source-files/{payload['source_file_id']}",
            params={"page": detail_first_page.json()["total_pages"], "size": 200},
        )
        self.assertEqual(200, detail_last_page.status_code)
        self.assertTrue(any(row["source_option_name"] == "Cash" for row in detail_last_page.json()["holdings"]))

        admin_ui_detail = self.client.get(
            f"/admin/ui/source-files/{payload['source_file_id']}",
            params={"page": detail_first_page.json()["total_pages"], "size": 200},
        )
        self.assertEqual(200, admin_ui_detail.status_code)
        self.assertIn("UNISUPER_CASH", admin_ui_detail.text)

        entity_detail = self.client.get("/entities/by-name", params={"name": "BNP PARIBAS SA (AUSTRALIA)"})
        self.assertEqual(200, entity_detail.status_code)
        self.assertEqual(28, entity_detail.json()["observation_count"])
        self.assertEqual(
            {"Conservative", "Cash"},
            {row["option_name"] for row in entity_detail.json()["observations"]},
        )
