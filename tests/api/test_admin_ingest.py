from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import Base, Holding
from app.db.session import get_engine
from tests.hesta_fixture import EXPECTED_TOTAL_ROWS, FIXTURE_PATH


class TestAdminIngestEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage1_api.db'}"
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

    def test_admin_ingest_local_file_endpoint(self) -> None:
        response = self.client.post(
            "/admin/ingest/local-file",
            json={
                "file_path": str(FIXTURE_PATH),
                "fund_code": "hesta",
                "fund_name": "HESTA",
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(EXPECTED_TOTAL_ROWS, payload["rows_staged"])
        self.assertEqual(EXPECTED_TOTAL_ROWS, payload["rows_inserted"])
        self.assertEqual(0, payload["rows_skipped_existing"])
        with self.SessionLocal() as session:
            self.assertEqual(EXPECTED_TOTAL_ROWS, session.query(Holding).count())
