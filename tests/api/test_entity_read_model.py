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
from tests.hesta_fixture import FIXTURE_PATH


class TestEntityReadModelApi(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage1_entity_read_model.db'}"
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
        ingest = self.client.post(
            "/admin/ingest/local-file",
            json={
                "file_path": str(FIXTURE_PATH),
                "fund_code": "hesta",
                "fund_name": "HESTA",
            },
        )
        self.assertEqual(200, ingest.status_code)

    def tearDown(self) -> None:
        self.app.dependency_overrides.clear()
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_entity_detail_by_name_returns_non_aggregate_observations(self) -> None:
        response = self.client.get("/entities/by-name", params={"name": "Generate Capital PBC"})
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual("Generate Capital PBC", payload["lookup_name"])
        self.assertEqual(1, payload["observation_count"])
        self.assertEqual({"ownership_only": 1}, payload["disclosure_completeness_counts"])
        self.assertEqual({"unlisted_infrastructure": 1}, payload["canonical_asset_class_counts"])
        self.assertEqual("0.0138", payload["observations"][0]["ownership_pct"])
        self.assertEqual("High Growth", payload["observations"][0]["option_name"])

    def test_entity_detail_returns_404_for_missing_name(self) -> None:
        response = self.client.get("/entities/by-name", params={"name": "Missing Entity Pty Ltd"})
        self.assertEqual(404, response.status_code)
