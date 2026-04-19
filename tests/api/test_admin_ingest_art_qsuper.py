from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import Base, Holding, SchemaReviewQueue, SourceFile
from app.db.session import get_engine
from app.ingest.governance import ART_QSUPER_MAPPING_VERSION_ID


FIXTURE_PATH = Path("tests/fixtures/art_qsuper_synthetic_balanced_minimal.csv").resolve()


class TestAdminArtQsuperIngestEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_art_qsuper_api.db'}"
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

    def test_admin_ingest_local_file_art_qsuper_endpoint(self) -> None:
        response = self.client.post(
            "/admin/ingest/local-file/art-qsuper",
            json={
                "file_path": str(FIXTURE_PATH),
                "fund_code": "art",
                "fund_name": "ART",
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(8, payload["rows_staged"])
        self.assertEqual(8, payload["rows_inserted"])
        self.assertEqual(0, payload["rows_skipped_existing"])

        with self.SessionLocal() as session:
            self.assertEqual(8, session.query(Holding).count())
            source_file = session.get(SourceFile, payload["source_file_id"])
            self.assertEqual("ArtQsuperPhdAdapter", source_file.adapter_key)
            self.assertEqual(ART_QSUPER_MAPPING_VERSION_ID, source_file.mapping_version_id)

        source_files = self.client.get("/admin/source-files")
        self.assertEqual(200, source_files.status_code)
        self.assertEqual(ART_QSUPER_MAPPING_VERSION_ID, source_files.json()[0]["mapping_version_id"])

        source_file_detail = self.client.get(f"/admin/source-files/{payload['source_file_id']}")
        self.assertEqual(200, source_file_detail.status_code)
        self.assertEqual("ART", source_file_detail.json()["source_file"]["fund_name"])

        admin_ui_detail = self.client.get(f"/admin/ui/source-files/{payload['source_file_id']}")
        self.assertEqual(200, admin_ui_detail.status_code)
        self.assertIn("Industry Super Holdings Pty Ltd", admin_ui_detail.text)

        entity_detail = self.client.get("/entities/by-name", params={"name": "Industry Super Holdings Pty Ltd"})
        self.assertEqual(200, entity_detail.status_code)
        self.assertEqual("ownership_only", entity_detail.json()["observations"][0]["disclosure_completeness"])

    def test_drifted_art_qsuper_file_returns_conflict_and_persists_review_item(self) -> None:
        drifted_path = Path(self.tempdir.name) / "art_qsuper_drifted_api.csv"
        drifted_text = FIXTURE_PATH.read_text(encoding="utf-8").replace(
            "Externally Managed,ART CORE BOND FUND",
            "External Mandate,ART CORE BOND FUND",
            1,
        )
        drifted_path.write_text(drifted_text, encoding="utf-8")

        response = self.client.post(
            "/admin/ingest/local-file/art-qsuper",
            json={
                "file_path": str(drifted_path),
                "fund_code": "art",
                "fund_name": "ART",
            },
        )
        self.assertEqual(409, response.status_code)

        with self.SessionLocal() as session:
            self.assertEqual(1, session.query(SchemaReviewQueue).count())
            review_item = session.query(SchemaReviewQueue).one()
            self.assertEqual("schema_drift", review_item.review_reason)
