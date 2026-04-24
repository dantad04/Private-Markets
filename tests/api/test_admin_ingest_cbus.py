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
from app.ingest.governance import (
    CBUS_AUSTRALIAN_SHARES_MAPPING_VERSION_ID,
    CBUS_CASH_MAPPING_VERSION_ID,
    CBUS_MAPPING_VERSION_ID,
    CBUS_OVERSEAS_SHARES_MAPPING_VERSION_ID,
    CBUS_PROPERTY_MAPPING_VERSION_ID,
)


FIXTURE_PATH = Path("tests/fixtures/real/cbus/super-high-growth__1_.csv").resolve()
PROPERTY_PATH = Path("tests/fixtures/real/cbus/super-property__1_.csv").resolve()
OVERSEAS_SHARES_PATH = Path("tests/fixtures/real/cbus/super-overseas-shares.csv").resolve()
AUSTRALIAN_SHARES_PATH = Path("tests/fixtures/real/cbus/super-australian-shares__1_.csv").resolve()
CASH_PATH = Path("tests/fixtures/real/cbus/super-cash.csv").resolve()

SOURCE_URLS = {
    PROPERTY_PATH: "https://www.cbussuper.com.au/content/dam/cbus/files/governance/investment-holdings/super-property.csv",
    OVERSEAS_SHARES_PATH: "https://www.cbussuper.com.au/content/dam/cbus/files/governance/investment-holdings/super-overseas-shares.csv",
    AUSTRALIAN_SHARES_PATH: "https://www.cbussuper.com.au/content/dam/cbus/files/governance/investment-holdings/super-australian-shares.csv",
    CASH_PATH: "https://www.cbussuper.com.au/content/dam/cbus/files/governance/investment-holdings/super-cash.csv",
}

BATCH_1_CASES = (
    (PROPERTY_PATH, SOURCE_URLS[PROPERTY_PATH], CBUS_PROPERTY_MAPPING_VERSION_ID, 106),
    (OVERSEAS_SHARES_PATH, SOURCE_URLS[OVERSEAS_SHARES_PATH], CBUS_OVERSEAS_SHARES_MAPPING_VERSION_ID, 1421),
    (
        AUSTRALIAN_SHARES_PATH,
        SOURCE_URLS[AUSTRALIAN_SHARES_PATH],
        CBUS_AUSTRALIAN_SHARES_MAPPING_VERSION_ID,
        353,
    ),
    (CASH_PATH, SOURCE_URLS[CASH_PATH], CBUS_CASH_MAPPING_VERSION_ID, 16),
)


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

    def test_admin_ingest_latest_period_batch_1_uses_mapping_seeds(self) -> None:
        for file_path, source_url, mapping_version_id, expected_rows in BATCH_1_CASES:
            with self.subTest(file=file_path.name):
                response = self.client.post(
                    "/admin/ingest/local-file/cbus",
                    json={
                        "file_path": str(file_path),
                        "fund_code": "cbus",
                        "fund_name": "Cbus",
                        "source_url": source_url,
                    },
                )
                self.assertEqual(200, response.status_code)
                payload = response.json()
                self.assertEqual(expected_rows, payload["rows_staged"])
                self.assertEqual(expected_rows, payload["rows_inserted"])
                self.assertEqual(0, payload["rows_skipped_existing"])

                with self.SessionLocal() as session:
                    source_file = session.get(SourceFile, payload["source_file_id"])
                    self.assertEqual("CbusPhdAdapter", source_file.adapter_key)
                    self.assertEqual(mapping_version_id, source_file.mapping_version_id)
                    self.assertEqual(source_url, source_file.source_url)
                    self.assertEqual(0, source_file.encoding_replacement_count)

        with self.SessionLocal() as session:
            self.assertEqual(sum(case[3] for case in BATCH_1_CASES), session.query(Holding).count())
            source_urls = {source_file.source_url.lower() for source_file in session.query(SourceFile).all()}
            self.assertFalse(any("super-high-growth" in source_url for source_url in source_urls))
            self.assertFalse(any("retirement" in source_url or "pension" in source_url for source_url in source_urls))


if __name__ == "__main__":
    unittest.main()
