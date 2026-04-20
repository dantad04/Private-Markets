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
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.entity_resolution.ifm_seed import ensure_ifm_seed
from app.entity_resolution.industry_super_holdings_seed import ensure_industry_super_holdings_seed
from app.ingest.loader import ingest_art_qsuper_local_file, ingest_art_sunsuper_local_file


ART_SUNSUPER_FIXTURE_PATH = Path("tests/fixtures/art_sunsuper_synthetic_stable_minimal.csv").resolve()
ART_QSUPER_FIXTURE_PATH = Path("tests/fixtures/art_qsuper_synthetic_balanced_minimal.csv").resolve()


class TestFundDetailApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'stage3_fund_detail.db'}"
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

            ingest_art_sunsuper_local_file(
                session,
                fund_code="art",
                fund_name="ART",
                file_path=str(ART_SUNSUPER_FIXTURE_PATH),
                reporting_period_id=period.id,
            )
            ingest_art_qsuper_local_file(
                session,
                fund_code="art",
                fund_name="ART",
                file_path=str(ART_QSUPER_FIXTURE_PATH),
                reporting_period_id=period.id,
            )
            ensure_ifm_seed(session)
            ensure_industry_super_holdings_seed(session)
            resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_fund_detail_endpoint_returns_identity_and_investment_options(self) -> None:
        response = self.client.get("/funds/art")
        self.assertEqual(200, response.status_code)

        payload = response.json()
        self.assertEqual("art", payload["fund_code"])
        self.assertEqual("ART", payload["fund_name"])
        self.assertIsInstance(payload["fund_id"], int)
        self.assertEqual(
            [("ART Balanced", "ART Balanced"), ("ARST", "ART Stable")],
            [(row["option_code"], row["option_name"]) for row in payload["investment_options"]],
        )

    def test_asset_class_mix_is_preserved_by_disclosure_completeness_instead_of_blended(self) -> None:
        response = self.client.get("/funds/art")
        self.assertEqual(200, response.status_code)
        payload = response.json()

        options = {row["option_name"]: row for row in payload["investment_options"]}
        balanced_mix = {
            row["canonical_asset_class_code"]: {
                bucket["disclosure_completeness"]: bucket for bucket in row["by_disclosure_completeness"]
            }
            for row in options["ART Balanced"]["asset_class_mix"]
        }

        self.assertEqual(
            {"name_only", "ownership_only"},
            set(balanced_mix["unlisted_equity"].keys()),
        )
        self.assertEqual(
            1,
            balanced_mix["unlisted_equity"]["ownership_only"]["observation_count"],
        )
        self.assertEqual(
            1,
            balanced_mix["unlisted_equity"]["name_only"]["observation_count"],
        )
        self.assertEqual(
            "25000000",
            balanced_mix["fixed_income"]["value_only"]["precise_value_aud_total"],
        )
        self.assertNotIn("total_precise_value_aud", payload)

    def test_top_direct_private_holdings_are_separate_from_manager_level_aggregate_exposures(self) -> None:
        response = self.client.get("/funds/art")
        self.assertEqual(200, response.status_code)
        payload = response.json()

        options = {row["option_name"]: row for row in payload["investment_options"]}
        balanced_direct_names = {
            row["raw_name"] for row in options["ART Balanced"]["top_direct_private_holdings"]
        }
        balanced_manager_names = {
            row["raw_name"] for row in options["ART Balanced"]["manager_level_aggregate_exposures"]
        }
        stable_direct_names = {
            row["raw_name"] for row in options["ART Stable"]["top_direct_private_holdings"]
        }
        stable_manager_names = {
            row["raw_name"] for row in options["ART Stable"]["manager_level_aggregate_exposures"]
        }

        self.assertIn("Industry Super Holdings Pty Ltd", balanced_direct_names)
        self.assertIn("Queen Street Logistics Trust", balanced_direct_names)
        self.assertIn("ART CORE BOND FUND", balanced_manager_names)
        self.assertIn("Industry Super Holdings Pty Ltd", stable_direct_names)
        self.assertIn("IFM Investors Pty Ltd", stable_manager_names)

        self.assertNotIn("IFM Investors Pty Ltd", stable_direct_names)
        self.assertNotIn("Industry Super Holdings Pty Ltd", stable_manager_names)
        self.assertNotIn("relationships", payload)

    def test_value_band_name_only_rows_are_excluded_from_computed_dollar_totals(self) -> None:
        response = self.client.get("/funds/art")
        self.assertEqual(200, response.status_code)
        payload = response.json()

        options = {row["option_name"]: row for row in payload["investment_options"]}
        balanced_mix = {
            row["canonical_asset_class_code"]: {
                bucket["disclosure_completeness"]: bucket for bucket in row["by_disclosure_completeness"]
            }
            for row in options["ART Balanced"]["asset_class_mix"]
        }

        name_only_bucket = balanced_mix["unlisted_equity"]["name_only"]
        self.assertEqual(1, name_only_bucket["observation_count"])
        self.assertEqual(0, name_only_bucket["precise_value_row_count"])
        self.assertEqual("0", name_only_bucket["precise_value_aud_total"])
        self.assertTrue(
            any(
                row["raw_name"] == "Blackbird Ventures Growth I"
                and row["disclosure_completeness"] == "name_only"
                and row["value_band_raw"] == "$100m-$500m"
                for row in options["ART Balanced"]["named_private_exposures"]
            )
        )

    def test_change_shape_is_honest_about_current_history_limitations(self) -> None:
        response = self.client.get("/funds/art")
        self.assertEqual(200, response.status_code)
        payload = response.json()

        change = payload["change_since_prior_reporting_period"]
        self.assertFalse(change["available"])
        self.assertEqual("2025-12-31", change["current_reporting_period_end_date"])
        self.assertIsNone(change["prior_reporting_period_end_date"])
        self.assertIn("Only one reporting period", change["note"])

    def test_fund_detail_admin_ui_renders_same_underlying_sections(self) -> None:
        response = self.client.get("/admin/ui/funds/art")
        self.assertEqual(200, response.status_code)
        self.assertIn("Fund Detail", response.text)
        self.assertIn("ART Balanced", response.text)
        self.assertIn("ART Stable", response.text)
        self.assertIn("Asset-class mix by disclosure completeness", response.text)
        self.assertIn("Top direct private holdings", response.text)
        self.assertIn("Manager-level aggregate exposures", response.text)
        self.assertIn("Only one reporting period", response.text)

