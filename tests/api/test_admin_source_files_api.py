from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import Base
from app.db.session import get_engine
from tests.hesta_fixture import EXPECTED_TOTAL_ROWS, FIXTURE_PATH


class TestAdminSourceFilesApi(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage1_admin_source_files.db'}"
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

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_source_files_endpoints_return_stage1_read_model(self) -> None:
        ingest = self.client.post(
            "/admin/ingest/local-file",
            json={
                "file_path": str(FIXTURE_PATH),
                "fund_code": "hesta",
                "fund_name": "HESTA",
            },
        )
        self.assertEqual(200, ingest.status_code)
        source_file_id = ingest.json()["source_file_id"]

        listing = self.client.get("/admin/source-files")
        self.assertEqual(200, listing.status_code)
        list_payload = listing.json()
        self.assertEqual(1, len(list_payload))
        self.assertEqual(source_file_id, list_payload[0]["source_file_id"])
        self.assertEqual(EXPECTED_TOTAL_ROWS, list_payload[0]["rows_loaded"])
        self.assertTrue(list_payload[0]["is_current_version"])

        detail = self.client.get(f"/admin/source-files/{source_file_id}")
        self.assertEqual(200, detail.status_code)
        detail_payload = detail.json()
        self.assertEqual(EXPECTED_TOTAL_ROWS, detail_payload["total_rows"])
        self.assertEqual("hesta", detail_payload["source_file"]["fund_code"])
        self.assertIn("ownership_only", detail_payload["disclosure_counts"])
        self.assertEqual("JPMorgan Chase & Co", detail_payload["holdings"][0]["raw_name"])
