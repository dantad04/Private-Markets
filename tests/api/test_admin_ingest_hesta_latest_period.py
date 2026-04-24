from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import Base, SourceFile
from app.db.session import get_engine


REAL_FIXTURE_DIR = Path("tests/fixtures/real/hesta").resolve()
LATEST_PERIOD_BATCH_CASES = (
    (REAL_FIXTURE_DIR / "Australian-Shares-super-assets.csv", "Australian Shares", 346),
    (REAL_FIXTURE_DIR / "Balanced-Growth-super-assets.csv", "Balanced Growth", 3050),
    (REAL_FIXTURE_DIR / "Conservative-super-assets.csv", "Conservative", 2955),
    (REAL_FIXTURE_DIR / "Diversified-Bonds-super-assets.csv", "Diversified Bonds", 181),
    (REAL_FIXTURE_DIR / "High-Growth-super-assets (1).csv", "High Growth", 2835),
    (REAL_FIXTURE_DIR / "Indexed-Balanced-Growth-super-assets.csv", "Indexed Balanced Growth", 1991),
    (REAL_FIXTURE_DIR / "International-Shares-super-assets.csv", "International Shares", 2456),
    (REAL_FIXTURE_DIR / "Property-and-Infrastructure-super-assets.csv", "Property and Infrastructure", 72),
    (REAL_FIXTURE_DIR / "Sustainable-Growth-super-assets.csv", "Sustainable Growth", 734),
)


class TestAdminIngestHestaLatestPeriod(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'hesta_latest_period_api.db'}"
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

    def test_hesta_latest_period_batch_renders_admin_source_file_and_entity_surfaces(self) -> None:
        source_file_ids: list[int] = []
        for fixture_path, _option_name, expected_rows in LATEST_PERIOD_BATCH_CASES:
            response = self.client.post(
                "/admin/ingest/local-file",
                json={
                    "file_path": str(fixture_path),
                    "fund_code": "hesta",
                    "fund_name": "HESTA",
                },
            )
            self.assertEqual(200, response.status_code)
            payload = response.json()
            self.assertEqual(expected_rows, payload["rows_staged"])
            self.assertEqual(expected_rows, payload["rows_inserted"])
            self.assertEqual(0, payload["rows_skipped_existing"])
            source_file_ids.append(payload["source_file_id"])

        listing = self.client.get("/admin/source-files")
        self.assertEqual(200, listing.status_code)
        list_payload = listing.json()
        self.assertEqual(len(LATEST_PERIOD_BATCH_CASES), len(list_payload))
        self.assertEqual(set(source_file_ids), {row["source_file_id"] for row in list_payload})
        self.assertEqual({rows for _path, _option, rows in LATEST_PERIOD_BATCH_CASES}, {row["rows_loaded"] for row in list_payload})

        detail = self.client.get(f"/admin/source-files/{source_file_ids[-1]}")
        self.assertEqual(200, detail.status_code)
        detail_payload = detail.json()
        self.assertEqual("hesta", detail_payload["source_file"]["fund_code"])
        self.assertEqual("Sustainable Growth", detail_payload["source_file"]["investment_option_name"])
        self.assertEqual(734, detail_payload["total_rows"])
        self.assertIn("aggregate_total", detail_payload["disclosure_counts"])
        self.assertEqual(
            detail_payload["holdings"][0]["source_row_number"],
            detail_payload["holdings"][0]["raw_payload_json"][0]["source_row_number"],
        )

        entity = self.client.get("/entities/by-name", params={"name": "IFM Investors Pty Ltd"})
        self.assertEqual(200, entity.status_code)
        entity_payload = entity.json()
        self.assertEqual("IFM Investors Pty Ltd", entity_payload["lookup_name"])
        self.assertEqual(9, entity_payload["observation_count"])
        self.assertEqual(
            {"fixed_income": 2, "unlisted_equity": 3, "unlisted_infrastructure": 4},
            entity_payload["canonical_asset_class_counts"],
        )

        with self.SessionLocal() as session:
            source_urls = {source_file.source_url for source_file in session.query(SourceFile).all()}
            self.assertFalse(any("derivatives" in source_url for source_url in source_urls))
