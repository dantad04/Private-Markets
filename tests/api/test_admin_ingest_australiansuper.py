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
from app.ingest.governance import (
    AUSTRALIANSUPER_BALANCED_MAPPING_VERSION_ID,
    AUSTRALIANSUPER_CONSERVATIVE_MAPPING_VERSION_ID,
    AUSTRALIANSUPER_HIGH_GROWTH_MAPPING_VERSION_ID,
    AUSTRALIANSUPER_MAPPING_VERSION_ID,
    AUSTRALIANSUPER_STABLE_MAPPING_VERSION_ID,
)


FIXTURE_DIR = Path("tests/fixtures/real/australiansuper").resolve()
MEMBER_DIRECT_PATH = FIXTURE_DIR / "Member Direct PHD (1).csv"
STABLE_PATH = FIXTURE_DIR / "Stable PHD (1).csv"
CONSERVATIVE_PATH = FIXTURE_DIR / "Conservative PHD (1).csv"
BALANCED_PATH = FIXTURE_DIR / "Balanced PHD (6).csv"
HIGH_GROWTH_PATH = FIXTURE_DIR / "High Growth PHD (2).csv"
SOCIALLY_AWARE_PATH = FIXTURE_DIR / "Socially Aware PHD.csv"

SOURCE_URLS = {
    MEMBER_DIRECT_PATH: "https://www.australiansuper.com/-/media/australian-super/files/investments/phd/superannuation/member-direct-phd.csv",
    STABLE_PATH: "https://www.australiansuper.com/-/media/australian-super/files/investments/phd/superannuation/stable-phd.csv",
    CONSERVATIVE_PATH: "https://www.australiansuper.com/-/media/australian-super/files/investments/phd/superannuation/conservative-phd.csv",
    BALANCED_PATH: "https://www.australiansuper.com/-/media/australian-super/files/investments/phd/superannuation/balanced-phd.csv",
    HIGH_GROWTH_PATH: "https://www.australiansuper.com/-/media/australian-super/files/investments/phd/superannuation/high-growth-phd.csv",
}


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
                "source_url": SOURCE_URLS[MEMBER_DIRECT_PATH],
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(564, payload["rows_staged"])
        self.assertEqual(564, payload["rows_inserted"])

        with self.SessionLocal() as session:
            source_file = session.get(SourceFile, payload["source_file_id"])
            self.assertEqual("AustralianSuperPhdAdapter", source_file.adapter_key)
            self.assertEqual(SOURCE_URLS[MEMBER_DIRECT_PATH], source_file.source_url)
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

        admin_ui_detail = self.client.get(
            f"/admin/ui/source-files/{payload['source_file_id']}",
            params={"page": 1, "size": 200},
        )
        self.assertEqual(200, admin_ui_detail.status_code)
        self.assertIn("Morella Corporation Ltd", admin_ui_detail.text)

        entity_detail = self.client.get("/entities/by-name", params={"name": "Morella Corporation Ltd"})
        self.assertEqual(200, entity_detail.status_code)
        self.assertEqual("fully_disclosed", entity_detail.json()["observations"][0]["disclosure_completeness"])
        self.assertEqual("BNSMZ47", entity_detail.json()["observations"][0]["security_identifier_value"])

    def test_admin_ingest_stable_file_uses_approved_mapping_and_keeps_ambiguities_in_review_queue(self) -> None:
        response = self.client.post(
            "/admin/ingest/local-file/australiansuper",
            json={
                "file_path": str(STABLE_PATH),
                "fund_code": "australiansuper",
                "fund_name": "AustralianSuper",
                "reporting_period_id": self.reporting_period_id,
                "source_url": SOURCE_URLS[STABLE_PATH],
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(4023, payload["rows_staged"])
        self.assertEqual(4023, payload["rows_inserted"])

        with self.SessionLocal() as session:
            source_file = session.get(SourceFile, payload["source_file_id"])
            self.assertEqual(SOURCE_URLS[STABLE_PATH], source_file.source_url)
            self.assertEqual(AUSTRALIANSUPER_STABLE_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(194, session.query(SchemaReviewQueue).count())

        detail = self.client.get(
            f"/admin/source-files/{payload['source_file_id']}",
            params={"page": 18, "size": 200},
        )
        self.assertEqual(200, detail.status_code)
        holdings = detail.json()["holdings"]
        ifm_row = next(row for row in holdings if row["source_row_number"] == 3420)
        self.assertEqual("IFM Investors", ifm_row["raw_name"])
        self.assertEqual([3999], ifm_row["metadata_attached_from_row_numbers"])
        self.assertEqual("$100m to $300m", ifm_row["value_band_raw"])

        admin_ui_detail = self.client.get(
            f"/admin/ui/source-files/{payload['source_file_id']}",
            params={"page": 18, "size": 200},
        )
        self.assertEqual(200, admin_ui_detail.status_code)
        self.assertIn("IFM Investors", admin_ui_detail.text)
        self.assertIn("metadata_attached_from_row_numbers=[3999]", admin_ui_detail.text)

    def test_admin_ingest_conservative_file_uses_the_conservative_mapping_seed(self) -> None:
        response = self.client.post(
            "/admin/ingest/local-file/australiansuper",
            json={
                "file_path": str(CONSERVATIVE_PATH),
                "fund_code": "australiansuper",
                "fund_name": "AustralianSuper",
                "reporting_period_id": self.reporting_period_id,
                "source_url": SOURCE_URLS[CONSERVATIVE_PATH],
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(4023, payload["rows_staged"])
        self.assertEqual(4023, payload["rows_inserted"])

        with self.SessionLocal() as session:
            source_file = session.get(SourceFile, payload["source_file_id"])
            self.assertEqual(SOURCE_URLS[CONSERVATIVE_PATH], source_file.source_url)
            self.assertEqual(AUSTRALIANSUPER_CONSERVATIVE_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(194, session.query(SchemaReviewQueue).count())

        detail = self.client.get(
            f"/admin/source-files/{payload['source_file_id']}",
            params={"page": 17, "size": 200},
        )
        self.assertEqual(200, detail.status_code)
        holdings = detail.json()["holdings"]
        merged_row = next(row for row in holdings if row["source_row_number"] == 3368)
        self.assertEqual("1200 W Carroll", merged_row["raw_name"])
        self.assertEqual([3877], merged_row["metadata_attached_from_row_numbers"])
        self.assertEqual("< $2m", merged_row["value_band_raw"])

        admin_ui_detail = self.client.get(
            f"/admin/ui/source-files/{payload['source_file_id']}",
            params={"page": 17, "size": 200},
        )
        self.assertEqual(200, admin_ui_detail.status_code)
        self.assertIn("1200 W Carroll", admin_ui_detail.text)
        self.assertIn("metadata_attached_from_row_numbers=[3877]", admin_ui_detail.text)

    def test_admin_ingest_balanced_and_high_growth_use_latest_period_mapping_seeds(self) -> None:
        cases = (
            (BALANCED_PATH, SOURCE_URLS[BALANCED_PATH], AUSTRALIANSUPER_BALANCED_MAPPING_VERSION_ID, 3920, 185),
            (
                HIGH_GROWTH_PATH,
                SOURCE_URLS[HIGH_GROWTH_PATH],
                AUSTRALIANSUPER_HIGH_GROWTH_MAPPING_VERSION_ID,
                3919,
                185,
            ),
        )

        cumulative_review_items = 0
        for file_path, source_url, mapping_version_id, expected_rows, expected_review_items in cases:
            with self.subTest(file=file_path.name):
                response = self.client.post(
                    "/admin/ingest/local-file/australiansuper",
                    json={
                        "file_path": str(file_path),
                        "fund_code": "australiansuper",
                        "fund_name": "AustralianSuper",
                        "reporting_period_id": self.reporting_period_id,
                        "source_url": source_url,
                    },
                )
                self.assertEqual(200, response.status_code)
                payload = response.json()
                self.assertEqual(expected_rows, payload["rows_staged"])
                self.assertEqual(expected_rows, payload["rows_inserted"])
                cumulative_review_items += expected_review_items

                with self.SessionLocal() as session:
                    source_file = session.get(SourceFile, payload["source_file_id"])
                    self.assertEqual("AustralianSuperPhdAdapter", source_file.adapter_key)
                    self.assertEqual(source_url, source_file.source_url)
                    self.assertEqual(mapping_version_id, source_file.mapping_version_id)
                    self.assertEqual(cumulative_review_items, session.query(SchemaReviewQueue).count())

    def test_admin_ingest_socially_aware_file_remains_review_gated(self) -> None:
        response = self.client.post(
            "/admin/ingest/local-file/australiansuper",
            json={
                "file_path": str(SOCIALLY_AWARE_PATH),
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
