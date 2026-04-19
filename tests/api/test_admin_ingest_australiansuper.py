from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import Base, ReportingPeriod, SchemaReviewQueue, SourceFile
from app.db.session import get_engine
from app.ingest.governance import AUSTRALIANSUPER_MAPPING_VERSION_ID


FIXTURE_DIR = Path("tests/fixtures/real/australiansuper").resolve()
MEMBER_DIRECT_PATH = FIXTURE_DIR / "Member Direct PHD (1).csv"
STABLE_PATH = FIXTURE_DIR / "Stable PHD (1).csv"


class TestAdminAustralianSuperIngestEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_australiansuper_api.db'}"
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

    def test_admin_ingest_member_direct_official_file(self) -> None:
        response = self.client.post(
            "/admin/ingest/local-file/australiansuper",
            json={
                "file_path": str(MEMBER_DIRECT_PATH),
                "fund_code": "australiansuper",
                "fund_name": "AustralianSuper",
                "reporting_period_id": self.reporting_period_id,
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(564, payload["rows_staged"])
        self.assertEqual(564, payload["rows_inserted"])

        with self.SessionLocal() as session:
            source_file = session.get(SourceFile, payload["source_file_id"])
            self.assertEqual("AustralianSuperPhdAdapter", source_file.adapter_key)
            self.assertEqual(AUSTRALIANSUPER_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(0, session.query(SchemaReviewQueue).count())

        listing = self.client.get("/admin/source-files")
        self.assertEqual(200, listing.status_code)
        self.assertEqual("AustralianSuperPhdAdapter", listing.json()[0]["adapter_key"])

        detail = self.client.get(f"/admin/source-files/{payload['source_file_id']}", params={"page": 1, "size": 200})
        self.assertEqual(200, detail.status_code)
        holdings = detail.json()["holdings"]

        morella_row = next(row for row in holdings if row["raw_name"] == "Morella Corporation Ltd")
        self.assertEqual("listed_equity", morella_row["canonical_asset_class_code"])
        self.assertEqual("BNSMZ47", morella_row["security_identifier_value"])
        self.assertEqual("fully_disclosed", morella_row["disclosure_completeness"])
        self.assertEqual(1, len(morella_row["raw_payload_json"]))
        self.assertEqual(2, morella_row["raw_payload_json"][0]["source_row_number"])
        self.assertEqual(
            ["AR2O", "Member Direct", "Equity", "Listed"],
            morella_row["raw_payload_json"][0]["payload"][:4],
        )
        self.assertEqual("Morella Corporation Ltd", morella_row["raw_payload_json"][0]["payload"][5])
        self.assertEqual("BNSMZ47", morella_row["raw_payload_json"][0]["payload"][9])
        self.assertEqual("27255.189", morella_row["raw_payload_json"][0]["payload"][14])

        aggregate_detail = self.client.get(
            f"/admin/source-files/{payload['source_file_id']}",
            params={"page": 3, "size": 200},
        )
        self.assertEqual(200, aggregate_detail.status_code)
        aggregate_holdings = aggregate_detail.json()["holdings"]

        total_row = next(row for row in aggregate_holdings if row["source_row_number"] == 551)
        self.assertTrue(total_row["is_aggregate"])
        self.assertEqual("aggregate_total", total_row["disclosure_completeness"])
        self.assertEqual("2844353758", total_row["value_aud"])
        self.assertEqual("Listed Equity", total_row["source_asset_class_raw"])

        admin_ui_detail = self.client.get(f"/admin/ui/source-files/{payload['source_file_id']}")
        self.assertEqual(200, admin_ui_detail.status_code)
        self.assertIn("Morella Corporation Ltd", admin_ui_detail.text)
        self.assertIn("aggregate_total", admin_ui_detail.text)

        entity_detail = self.client.get("/entities/by-name", params={"name": "Morella Corporation Ltd"})
        self.assertEqual(200, entity_detail.status_code)
        self.assertEqual("fully_disclosed", entity_detail.json()["observations"][0]["disclosure_completeness"])
        self.assertEqual("BNSMZ47", entity_detail.json()["observations"][0]["security_identifier_value"])

    def test_admin_ingest_stable_file_returns_review_conflict_until_broader_mapping_is_approved(self) -> None:
        response = self.client.post(
            "/admin/ingest/local-file/australiansuper",
            json={
                "file_path": str(STABLE_PATH),
                "fund_code": "australiansuper",
                "fund_name": "AustralianSuper",
                "reporting_period_id": self.reporting_period_id,
            },
        )
        self.assertEqual(409, response.status_code)
        self.assertIn("AustralianSuperPhdAdapter drift detected", response.json()["detail"])

        with self.SessionLocal() as session:
            self.assertEqual(1, session.query(SchemaReviewQueue).count())
            review_item = session.query(SchemaReviewQueue).one()
            self.assertEqual("schema_drift", review_item.review_reason)
