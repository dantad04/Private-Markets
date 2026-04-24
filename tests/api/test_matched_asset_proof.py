from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import Base, ReportingPeriod
from app.db.session import get_engine
from app.entity_resolution.australiansuper_stable_matched_assets import (
    AUSTRALIANSUPER_STABLE_MATCHED_ASSET_SOURCE,
    ensure_australiansuper_stable_matched_asset_proof,
)
from app.ingest.loader import ingest_australiansuper_local_file
from app.read_models import get_australiansuper_stable_matched_asset_proof


AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()


class TestMatchedAssetProofApiAndUi(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'matched_asset_proof_api.db'}"
        cls.engine = get_engine(cls.database_url)
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False, future=True)
        cls.app = create_app()

        def override_get_db_session():
            session = cls.SessionLocal()
            try:
                yield session
                session.commit()
            except Exception:
                session.rollback()
                raise
            finally:
                session.close()

        cls.app.dependency_overrides[get_db_session] = override_get_db_session
        cls.client = TestClient(cls.app)

        with cls.SessionLocal() as session:
            period = ReportingPeriod(
                period_end_date=date(2025, 12, 31),
                disclosure_due_date=date(2026, 3, 31),
                label="2025-12-31",
                source_cycle="semi_annual",
            )
            session.add(period)
            session.flush()
            ingest_australiansuper_local_file(
                session,
                fund_code="australiansuper",
                fund_name="AustralianSuper",
                file_path=str(AUSTRALIANSUPER_STABLE_FIXTURE_PATH),
                reporting_period_id=period.id,
            )
            ensure_australiansuper_stable_matched_asset_proof(session)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_read_model_returns_the_seven_row_table_proof(self) -> None:
        with self.SessionLocal() as session:
            detail = get_australiansuper_stable_matched_asset_proof(session)

        self.assertEqual("australiansuper-stable-stage5-proof", detail.proof_key)
        self.assertIn("map precursor", detail.scope_note)
        self.assertEqual(7, detail.matched_asset_count)
        self.assertEqual(
            [3368, 3369, 3375, 3425, 3445, 3453, 3484],
            [row.source_row_number for row in detail.rows],
        )
        self.assertTrue(all(row.geo_lat is not None and row.geo_lng is not None for row in detail.rows))
        self.assertTrue(all(row.relationship_source == AUSTRALIANSUPER_STABLE_MATCHED_ASSET_SOURCE for row in detail.rows))

    def test_admin_api_returns_coordinates_confidence_and_provenance(self) -> None:
        response = self.client.get("/admin/matched-assets/australiansuper-stable-stage5-proof")
        self.assertEqual(200, response.status_code)

        payload = response.json()
        self.assertEqual(7, payload["matched_asset_count"])
        self.assertIn("Bounded Stage 5 matched-asset proof", payload["scope_note"])

        rows = payload["rows"]
        self.assertEqual(
            ["1200 W Carroll", "1300 W Carroll", "Ala Moana Shopping Centre", "Kingswood", "NSW Ports", "Perth Airport", "Wollert"],
            [row["asset_entity_name"] for row in rows],
        )
        first = rows[0]
        self.assertEqual("property_asset", first["entity_type"])
        self.assertEqual("australiansuper", first["source_fund_code"])
        self.assertEqual("Stable", first["option_name"])
        self.assertEqual("2025-12-31", first["reporting_period_end_date"])
        self.assertEqual("unlisted_property", first["canonical_asset_class_code"])
        self.assertEqual("Unlisted Property", first["source_asset_class_raw"])
        self.assertEqual("Internally Managed", first["source_subclass_raw"])
        self.assertEqual("ownership_only", first["disclosure_completeness"])
        self.assertEqual("0.0109", first["ownership_pct"])
        self.assertEqual("< $2m", first["value_band_raw"])
        self.assertEqual("Office", first["classification_raw"])
        self.assertEqual("1200 W Carroll Ave, Chicago, IL 60607, USA", first["address"])
        self.assertEqual("United States", first["location_raw"])
        self.assertIsNotNone(first["geo_lat"])
        self.assertIsNotNone(first["geo_lng"])
        self.assertEqual("1", first["confidence_score"])
        self.assertEqual(AUSTRALIANSUPER_STABLE_MATCHED_ASSET_SOURCE, first["relationship_source"])
        self.assertEqual(3368, first["source_row_number"])
        self.assertEqual([3885], first["metadata_attached_from_row_numbers"])

        nsw_ports = next(row for row in rows if row["asset_entity_name"] == "NSW Ports")
        self.assertEqual("infrastructure_asset", nsw_ports["entity_type"])
        self.assertEqual("unlisted_infrastructure", nsw_ports["canonical_asset_class_code"])
        self.assertEqual("Seaport", nsw_ports["classification_raw"])
        self.assertEqual([3990], nsw_ports["metadata_attached_from_row_numbers"])

    def test_admin_ui_renders_the_table_first_proof_without_map_claims(self) -> None:
        response = self.client.get("/admin/ui/matched-assets/australiansuper-stable-stage5-proof")
        self.assertEqual(200, response.status_code)

        self.assertIn("AustralianSuper Stable matched-asset proof", response.text)
        self.assertIn("Bounded Stage 5 matched-asset proof / map precursor", response.text)
        self.assertIn("not a complete property or infrastructure map", response.text)
        self.assertIn("1200 W Carroll", response.text)
        self.assertIn("Perth Airport", response.text)
        self.assertIn("property_asset", response.text)
        self.assertIn("infrastructure_asset", response.text)
        self.assertIn("lat", response.text)
        self.assertIn("lng", response.text)
        self.assertIn(AUSTRALIANSUPER_STABLE_MATCHED_ASSET_SOURCE, response.text)
        self.assertIn("file", response.text)
        self.assertIn("row <span class=\"mono\">3368</span>", response.text)
