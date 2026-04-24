from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import Base, Holding, SourceFile
from app.db.session import get_engine
from app.ingest.governance import CBUS_MAPPING_VERSION_ID


FIXTURE_PATH = Path("tests/fixtures/real/cbus/super-high-growth__1_.csv").resolve()


class TestAdminCbusIngestEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_cbus_api.db'}"
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

    def test_admin_ingest_local_file_cbus_endpoint(self) -> None:
        response = self.client.post(
            "/admin/ingest/local-file/cbus",
            json={
                "file_path": str(FIXTURE_PATH),
                "fund_code": "cbus",
                "fund_name": "Cbus",
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(2249, payload["rows_staged"])
        self.assertEqual(2249, payload["rows_inserted"])
        self.assertEqual(0, payload["rows_skipped_existing"])
        self.assertIsNotNone(payload["investment_option_id"])
        self.assertEqual([], payload["warnings"])

        with self.SessionLocal() as session:
            self.assertEqual(2249, session.query(Holding).count())
            source_file = session.get(SourceFile, payload["source_file_id"])
            self.assertEqual("CbusPhdAdapter", source_file.adapter_key)
            self.assertEqual(CBUS_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(0, source_file.encoding_replacement_count)

        listing = self.client.get("/admin/source-files")
        self.assertEqual(200, listing.status_code)
        self.assertEqual("CbusPhdAdapter", listing.json()[0]["adapter_key"])
        self.assertEqual(2249, listing.json()[0]["rows_loaded"])
        self.assertEqual(0, listing.json()[0]["encoding_replacement_count"])

        detail = self.client.get(f"/admin/source-files/{payload['source_file_id']}", params={"page": 1, "size": 200})
        self.assertEqual(200, detail.status_code)
        self.assertEqual("High Growth Accumulation Option", detail.json()["holdings"][0]["source_option_name"])

        admin_ui_detail = self.client.get(f"/admin/ui/source-files/{payload['source_file_id']}", params={"page": 1, "size": 200})
        self.assertEqual(200, admin_ui_detail.status_code)
        self.assertIn("CBUS_HIGH_GROWTH_ACCUMULATION_OPTION", admin_ui_detail.text)
        self.assertIn("AUSTRALIA &amp; NEW ZEALAND BANKING GROUP LTD", admin_ui_detail.text)


if __name__ == "__main__":
    unittest.main()
