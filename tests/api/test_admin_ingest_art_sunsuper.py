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
from app.ingest.governance import ART_SUNSUPER_MAPPING_VERSION_ID


FIXTURE_PATH = Path("tests/fixtures/art_sunsuper_synthetic_stable_minimal.csv").resolve()


class TestAdminArtSunsuperIngestEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_art_sunsuper_api.db'}"
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

    def test_admin_ingest_local_file_art_sunsuper_endpoint(self) -> None:
        response = self.client.post(
            "/admin/ingest/local-file/art-sunsuper",
            json={
                "file_path": str(FIXTURE_PATH),
                "fund_code": "art",
                "fund_name": "ART",
                "reporting_period_id": self.reporting_period_id,
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(4, payload["rows_staged"])
        self.assertEqual(4, payload["rows_inserted"])

        with self.SessionLocal() as session:
            source_file = session.get(SourceFile, payload["source_file_id"])
            self.assertEqual("ArtSunsuperPhdAdapter", source_file.adapter_key)
            self.assertEqual(ART_SUNSUPER_MAPPING_VERSION_ID, source_file.mapping_version_id)

        listing = self.client.get("/admin/source-files")
        self.assertEqual(200, listing.status_code)
        self.assertEqual("ArtSunsuperPhdAdapter", listing.json()[0]["adapter_key"])

        detail = self.client.get(f"/admin/source-files/{payload['source_file_id']}")
        self.assertEqual(200, detail.status_code)
        holdings = detail.json()["holdings"]
        ifm_row = next(row for row in holdings if row["raw_name"] == "IFM Investors Pty Ltd")
        self.assertEqual([3], ifm_row["metadata_attached_from_row_numbers"])
        self.assertEqual(
            [
                {
                    "source_row_number": 2,
                    "payload": [
                        "ARST",
                        "ART Stable",
                        "Externally Managed",
                        "Fixed Income",
                        "Manager",
                        "IFM Investors Pty Ltd",
                        "n/a",
                        "AUD",
                        "n/a",
                        "339726831",
                        "n/a",
                        "0.07",
                        "n/a",
                        "n/a",
                        "n/a",
                        "n/a",
                        "n/a",
                        "n/a",
                        "Externally Managed",
                        "n/a",
                        "IFM Investors Pty Ltd",
                        "Australia",
                        "n/a",
                        "Management Slice",
                    ],
                },
                {
                    "source_row_number": 3,
                    "payload": [
                        "ARST",
                        "ART Stable",
                        "All Assets",
                        "Fixed Income",
                        "Manager",
                        "IFM Investors Pty Ltd",
                        "n/a",
                        "AUD",
                        "n/a",
                        "n/a",
                        "n/a",
                        "n/a",
                        "$100m to $300m",
                        "Debt Manager",
                        "Level 15, 20 Bond Street, Sydney NSW 2000",
                        "Australia",
                        "-33.8644",
                        "151.2088",
                        "Externally Managed",
                        "n/a",
                        "IFM Investors Pty Ltd",
                        "Australia",
                        "n/a",
                        "All Assets Slice",
                    ],
                },
            ],
            ifm_row["raw_payload_json"],
        )

        admin_ui_detail = self.client.get(f"/admin/ui/source-files/{payload['source_file_id']}")
        self.assertEqual(200, admin_ui_detail.status_code)
        self.assertIn("metadata_attached_from_row_numbers=[3]", admin_ui_detail.text)

        entity_detail = self.client.get("/entities/by-name", params={"name": "Industry Super Holdings Pty Ltd"})
        self.assertEqual(200, entity_detail.status_code)
        self.assertEqual("ownership_only", entity_detail.json()["observations"][0]["disclosure_completeness"])
        self.assertEqual("0.18", entity_detail.json()["observations"][0]["ownership_pct"])

    def test_ambiguous_duplicate_group_returns_200_and_queues_review_item(self) -> None:
        ambiguous_path = Path(self.tempdir.name) / "art_sunsuper_ambiguous_api.csv"
        ambiguous_text = FIXTURE_PATH.read_text(encoding="utf-8") + (
            "\nARST,ART Stable,Externally Managed,Listed Infrastructure,Manager,IFM Investors Pty Ltd,n/a,AUD,n/a,5000000,n/a,0.01,n/a,n/a,n/a,Australia,n/a,n/a,Externally Managed,n/a,IFM Investors Pty Ltd,Australia,n/a,Management Slice\n"
        )
        ambiguous_path.write_text(ambiguous_text, encoding="utf-8")

        response = self.client.post(
            "/admin/ingest/local-file/art-sunsuper",
            json={
                "file_path": str(ambiguous_path),
                "fund_code": "art",
                "fund_name": "ART",
                "reporting_period_id": self.reporting_period_id,
            },
        )
        self.assertEqual(200, response.status_code)

        with self.SessionLocal() as session:
            self.assertEqual(1, session.query(SchemaReviewQueue).count())
            review_item = session.query(SchemaReviewQueue).one()
            self.assertEqual("ambiguous_duplicate_group", review_item.review_reason)
