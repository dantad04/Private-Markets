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


FIXTURE_PATH = Path("tests/fixtures/art_qsuper_synthetic_balanced_minimal.csv").resolve()


class TestAdminSchemaReviewQueueUi(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_schema_review_ui.db'}"
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

    def test_schema_review_queue_pages_render_and_rejection_moves_item_out_of_open_queue(self) -> None:
        drifted_path = Path(self.tempdir.name) / "art_qsuper_drifted_review_ui.csv"
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

        listing = self.client.get("/admin/ui/schema-review-queue")
        self.assertEqual(200, listing.status_code)
        self.assertIn("<title>Schema Review Queue - Private Market Insider: Australia</title>", listing.text)
        self.assertIn("schema_drift", listing.text)
        self.assertIn("ArtQsuperPhdAdapter", listing.text)

        detail_link_count = listing.text.count("/admin/ui/schema-review-queue/")
        self.assertEqual(1, detail_link_count)

        review_item_id = int(
            listing.text.split('/admin/ui/schema-review-queue/', 1)[1].split('"', 1)[0]
        )
        detail = self.client.get(f"/admin/ui/schema-review-queue/{review_item_id}")
        self.assertEqual(200, detail.status_code)
        self.assertIn("Source File Metadata", detail.text)
        self.assertIn("Approved Mapping Version", detail.text)
        self.assertIn("observed_internal_external_values", detail.text)
        self.assertIn("External Mandate", detail.text)

        update = self.client.post(
            f"/admin/ui/schema-review-queue/{review_item_id}/status",
            data={"status": "rejected"},
            follow_redirects=True,
        )
        self.assertEqual(200, update.status_code)
        self.assertIn(f"Review item {review_item_id} marked rejected.", update.text)
        self.assertIn("No review items found.", update.text)

        all_items = self.client.get("/admin/ui/schema-review-queue?status=all")
        self.assertEqual(200, all_items.status_code)
        self.assertIn(">rejected<", all_items.text)

