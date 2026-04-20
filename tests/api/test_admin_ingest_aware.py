
from __future__ import annotations

from datetime import datetime
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import Base, Holding, SourceFile
from app.db.session import get_engine


FIXTURE_PATH = Path("tests/fixtures/aware_synthetic_table1_minimal.csv").resolve()


class TestAdminAwareIngestEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_aware_api.db'}"
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

    def test_admin_ingest_local_file_aware_endpoint(self) -> None:
        response = self.client.post(
            "/admin/ingest/local-file/aware",
            json={
                "file_path": str(FIXTURE_PATH),
                "fund_code": "aware",
                "fund_name": "Aware Super",
                "terms_snapshot_url": "https://example.com/aware/terms",
                "downloaded_at": "2026-04-20T10:30:00",
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(19, payload["rows_staged"])
        self.assertEqual(19, payload["rows_inserted"])
        self.assertEqual(0, payload["rows_skipped_existing"])
        with self.SessionLocal() as session:
            self.assertEqual(19, session.query(Holding).count())
            source_file = session.get(SourceFile, payload["source_file_id"])
            self.assertEqual("AwarePhdAdapter", source_file.adapter_key)
            self.assertEqual("https://example.com/aware/terms", source_file.terms_snapshot_url)
            self.assertEqual(datetime(2026, 4, 20, 10, 30, 0), source_file.downloaded_at)
