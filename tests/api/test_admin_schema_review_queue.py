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
from app.ingest.governance import ART_QSUPER_MAPPING_VERSION_ID


FIXTURE_PATH = Path("tests/fixtures/art_qsuper_synthetic_balanced_minimal.csv").resolve()


class TestAdminSchemaReviewQueueApi(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_schema_review_api.db'}"
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

    def test_schema_review_queue_endpoints_list_detail_and_resolve_real_drift_item(self) -> None:
        drifted_path = Path(self.tempdir.name) / "art_qsuper_drifted_review.csv"
        drifted_text = FIXTURE_PATH.read_text(encoding="utf-8").replace(
            "Externally Managed,ART CORE BOND FUND",
            "External Mandate,ART CORE BOND FUND",
            1,
        )
        drifted_path.write_text(drifted_text, encoding="utf-8")

        ingest = self.client.post(
            "/admin/ingest/local-file/art-qsuper",
            json={
                "file_path": str(drifted_path),
                "fund_code": "art",
                "fund_name": "ART",
            },
        )
        self.assertEqual(409, ingest.status_code)

        listing = self.client.get("/admin/schema-review-queue")
        self.assertEqual(200, listing.status_code)
        list_payload = listing.json()
        self.assertEqual(1, len(list_payload))
        self.assertEqual("schema_drift", list_payload[0]["review_reason"])
        self.assertEqual("open", list_payload[0]["status"])
        review_item_id = list_payload[0]["review_item_id"]

        detail = self.client.get(f"/admin/schema-review-queue/{review_item_id}")
        self.assertEqual(200, detail.status_code)
        detail_payload = detail.json()
        self.assertEqual("art", detail_payload["source_file"]["fund_code"])
        self.assertEqual("review_required", detail_payload["source_file"]["ingest_status"])
        self.assertEqual(ART_QSUPER_MAPPING_VERSION_ID, detail_payload["approved_mapping_version"]["mapping_version_id"])
        self.assertIn("observed_internal_external_values", detail_payload["drift_summary_json"])
        self.assertIn("External Mandate", "\n".join(",".join(row) for row in detail_payload["sample_rows_json"]))

        update = self.client.post(
            f"/admin/schema-review-queue/{review_item_id}/status",
            json={"status": "resolved"},
        )
        self.assertEqual(200, update.status_code)
        self.assertEqual("resolved", update.json()["review_item"]["status"])

        open_listing = self.client.get("/admin/schema-review-queue")
        self.assertEqual([], open_listing.json())

        all_listing = self.client.get("/admin/schema-review-queue", params={"status": "all"})
        self.assertEqual(1, len(all_listing.json()))
        self.assertEqual("resolved", all_listing.json()[0]["status"])

