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
from app.ingest.governance import AWARE_INVESTMENT_FUNDS_2025_MAPPING_VERSION_ID


REAL_FIXTURE_DIR = Path("tests/fixtures/real/aware").resolve()
REAL_SHAPE_FINGERPRINT = "5f32c5b412bf04749982c45080dfec21e9e2e46911971d1a9d6e1f2277cb1e0a"
LATEST_PERIOD_BATCH_CASES = (
    (REAL_FIXTURE_DIR / "IFA-Australian-Equities.csv", "Australian Equities", "SS8K", 329),
    (REAL_FIXTURE_DIR / "IFA-Balanced.csv", "Balanced", "SS6K", 1968),
    (REAL_FIXTURE_DIR / "IFA-Capital-Stable.csv", "Capital Stable", "SS5K", 1966),
    (REAL_FIXTURE_DIR / "IFA-Cash.csv", "Cash", "SS3K", 25),
    (REAL_FIXTURE_DIR / "IFA-Growth.csv", "Growth", "SS9K", 1965),
    (REAL_FIXTURE_DIR / "IFA-International-Equities.csv", "International Equities", "SRCK", 1344),
    (REAL_FIXTURE_DIR / "IFA-Moderate.csv", "Moderate", "SS7K", 1969),
    (REAL_FIXTURE_DIR / "IFB-Australian-Equities.csv", "Australian Equities", "SR5K", 329),
    (REAL_FIXTURE_DIR / "IFB-Balanced.csv", "Balanced", "SR2K", 1968),
    (REAL_FIXTURE_DIR / "IFB-Capital-Stable.csv", "Capital Stable", "SRYK", 1966),
    (REAL_FIXTURE_DIR / "IFB-Cash.csv", "Cash", "SRSK", 25),
    (REAL_FIXTURE_DIR / "IFB-Growth.csv", "Growth", "SR6K", 1965),
    (REAL_FIXTURE_DIR / "IFB-International-Equities.csv", "International Equities", "SR7K", 1344),
    (REAL_FIXTURE_DIR / "IFB-Moderate.csv", "Moderate", "SR4K", 1969),
)


class TestAdminIngestAwareLatestPeriod(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'aware_latest_period_api.db'}"
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

    def test_aware_latest_period_batch_renders_admin_source_file_and_entity_surfaces(self) -> None:
        source_file_ids: list[int] = []
        for fixture_path, _option_name, _option_code, expected_rows in LATEST_PERIOD_BATCH_CASES:
            response = self.client.post(
                "/admin/ingest/local-file/aware",
                json={
                    "file_path": str(fixture_path),
                    "fund_code": "aware",
                    "fund_name": "Aware Super",
                },
            )
            self.assertEqual(200, response.status_code)
            payload = response.json()
            self.assertEqual(expected_rows, payload["rows_staged"])
            self.assertEqual(expected_rows, payload["rows_inserted"])
            self.assertEqual(0, payload["rows_skipped_existing"])
            self.assertEqual(REAL_SHAPE_FINGERPRINT, payload["schema_fingerprint"])
            source_file_ids.append(payload["source_file_id"])

        listing = self.client.get("/admin/source-files")
        self.assertEqual(200, listing.status_code)
        list_payload = listing.json()
        self.assertEqual(14, len(list_payload))
        self.assertEqual(set(source_file_ids), {row["source_file_id"] for row in list_payload})
        self.assertEqual(
            sorted(rows for _path, _option, _code, rows in LATEST_PERIOD_BATCH_CASES),
            sorted(row["rows_loaded"] for row in list_payload),
        )

        detail = self.client.get(f"/admin/source-files/{source_file_ids[-1]}")
        self.assertEqual(200, detail.status_code)
        detail_payload = detail.json()
        self.assertEqual("aware", detail_payload["source_file"]["fund_code"])
        self.assertEqual("Moderate", detail_payload["source_file"]["investment_option_name"])
        self.assertEqual(AWARE_INVESTMENT_FUNDS_2025_MAPPING_VERSION_ID, detail_payload["source_file"]["mapping_version_id"])
        self.assertEqual(1969, detail_payload["total_rows"])
        self.assertEqual("aggregate_total", next(key for key in detail_payload["disclosure_counts"] if key == "aggregate_total"))
        self.assertEqual(
            detail_payload["holdings"][0]["source_row_number"],
            detail_payload["holdings"][0]["raw_payload_json"][0]["source_row_number"],
        )

        detail_ui = self.client.get(f"/admin/ui/source-files/{source_file_ids[-1]}")
        self.assertEqual(200, detail_ui.status_code)
        self.assertIn("Aware Super", detail_ui.text)
        self.assertIn("Moderate", detail_ui.text)

        entity = self.client.get("/entities/by-name", params={"name": "STATE STREET BANK AND TRUST"})
        self.assertEqual(200, entity.status_code)
        entity_payload = entity.json()
        self.assertEqual("STATE STREET BANK AND TRUST", entity_payload["lookup_name"])
        self.assertEqual(168, entity_payload["observation_count"])
        self.assertEqual({"value_only": 168}, entity_payload["disclosure_completeness_counts"])

        with self.SessionLocal() as session:
            source_urls = {source_file.source_url for source_file in session.query(SourceFile).all()}
            self.assertEqual(
                {str(path) for path, _option, _code, _rows in LATEST_PERIOD_BATCH_CASES},
                source_urls,
            )
            self.assertFalse(
                any(
                    forbidden in Path(source_url).name.casefold()
                    for source_url in source_urls
                    for forbidden in ("retirement", "pension", "income stream", "ttr")
                )
            )
