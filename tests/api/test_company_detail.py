from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import Base, Entity, EntityRelationship, HoldingRelationship, ReportingPeriod
from app.db.session import get_engine
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.entity_resolution.industry_super_holdings_seed import (
    INDUSTRY_SUPER_HOLDINGS_CANONICAL_NAME,
    ensure_industry_super_holdings_seed,
)
from app.ingest.loader import (
    ingest_art_qsuper_local_file,
    ingest_art_sunsuper_local_file,
    ingest_australiansuper_local_file,
    ingest_hostplus_local_file,
    ingest_unisuper_local_file,
)


ART_SUNSUPER_FIXTURE_PATH = Path("tests/fixtures/art_sunsuper_synthetic_stable_minimal.csv").resolve()
ART_QSUPER_FIXTURE_PATH = Path("tests/fixtures/art_qsuper_synthetic_balanced_minimal.csv").resolve()
HOSTPLUS_FIXTURE_PATH = Path("tests/fixtures/hostplus_real_extract.csv").resolve()
UNISUPER_FIXTURE_PATH = Path("tests/fixtures/unisuper_real_extract.csv").resolve()
AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()


class TestCompanyDetailApi(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'stage3_company_detail.db'}"
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
            ingest_hostplus_local_file(
                session,
                fund_code="hostplus",
                fund_name="Hostplus",
                file_path=str(HOSTPLUS_FIXTURE_PATH),
                reporting_period_id=period.id,
            )
            ingest_unisuper_local_file(
                session,
                fund_code="unisuper",
                fund_name="UniSuper",
                file_path=str(UNISUPER_FIXTURE_PATH),
                reporting_period_id=period.id,
            )
            ingest_australiansuper_local_file(
                session,
                fund_code="australiansuper",
                fund_name="AustralianSuper",
                file_path=str(AUSTRALIANSUPER_STABLE_FIXTURE_PATH),
                reporting_period_id=period.id,
            )
            entity = ensure_industry_super_holdings_seed(session)
            blackbird_entity = Entity(
                entity_type="company",
                canonical_name="Blackbird Ventures Growth I",
                abn=None,
                country_code="AU",
                is_australian_entity=True,
                confidence_tier="seeded",
                notes="Stage 4 company-page value-band fixture entity.",
            )
            session.add(blackbird_entity)
            session.flush()
            resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

            cls.entity_id = entity.id
            cls.blackbird_entity_id = blackbird_entity.id

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_company_detail_endpoint_returns_canonical_identity_aliases_and_honest_history_shape(self) -> None:
        response = self.client.get(f"/entities/companies/{self.entity_id}")
        self.assertEqual(200, response.status_code)

        payload = response.json()
        self.assertEqual(self.entity_id, payload["entity_id"])
        self.assertEqual(INDUSTRY_SUPER_HOLDINGS_CANONICAL_NAME, payload["canonical_name"])
        self.assertEqual("company", payload["entity_type"])
        self.assertIsNone(payload["abn"])
        self.assertEqual(
            {
                "Industry Super Holdings",
                "Industry Super Holdings Pty Ltd",
                "Industry Super Holdings Pty Ltd F/P",
            },
            set(payload["aliases"]),
        )
        self.assertEqual(
            {
                "Industry Super Holdings",
                "Industry Super Holdings Pty Ltd",
                "Industry Super Holdings Pty Ltd F/P",
            },
            set(payload["matched_raw_names"]),
        )
        self.assertEqual(5, payload["observation_count"])
        self.assertEqual(3, payload["fund_count"])
        self.assertEqual("2025-12-31", payload["latest_reporting_period"])
        self.assertTrue(payload["history_is_limited"])
        self.assertIn("Only one reporting period", payload["history_note"])
        self.assertEqual(
            [
                {
                    "reporting_period_end_date": "2025-12-31",
                    "observation_count": 5,
                    "fund_count": 3,
                }
            ],
            payload["period_history"],
        )

    def test_company_detail_endpoint_preserves_per_fund_option_period_observations_and_disclosure_variance(self) -> None:
        response = self.client.get(f"/entities/companies/{self.entity_id}")
        self.assertEqual(200, response.status_code)

        payload = response.json()
        observations = payload["observations"]
        counts_by_fund_option_period = Counter(
            (row["fund_code"], row["option_name"], row["reporting_period_end_date"])
            for row in observations
        )
        self.assertEqual(1, counts_by_fund_option_period[("art", "ART Balanced", "2025-12-31")])
        self.assertEqual(1, counts_by_fund_option_period[("art", "ART Stable", "2025-12-31")])
        self.assertEqual(1, counts_by_fund_option_period[("hostplus", "HC High Growth - Class A Option", "2025-12-31")])
        self.assertEqual(2, counts_by_fund_option_period[("australiansuper", "Stable", "2025-12-31")])

        self.assertTrue(
            any(
                row["fund_code"] == "art"
                and row["option_name"] == "ART Balanced"
                and row["raw_name"] == "Industry Super Holdings Pty Ltd"
                and row["disclosure_completeness"] == "ownership_only"
                and row["ownership_pct"] == "0.1432"
                and row["canonical_asset_class_code"] == "unlisted_equity"
                and row["source_asset_class_raw"] == "Unlisted Equity"
                and row["source_file_id"] is not None
                for row in observations
            )
        )
        self.assertTrue(
            any(
                row["fund_code"] == "art"
                and row["option_name"] == "ART Stable"
                and row["raw_name"] == "Industry Super Holdings Pty Ltd"
                and row["disclosure_completeness"] == "ownership_only"
                and row["ownership_pct"] == "0.18"
                and row["canonical_asset_class_code"] == "unlisted_equity"
                and row["source_asset_class_raw"] == "Private Equity"
                for row in observations
            )
        )
        self.assertTrue(
            any(
                row["fund_code"] == "hostplus"
                and row["option_name"] == "HC High Growth - Class A Option"
                and row["raw_name"] == "Industry Super Holdings"
                and row["disclosure_completeness"] == "ownership_only"
                and row["ownership_pct"] == "0.1317"
                for row in observations
            )
        )
        self.assertTrue(
            any(
                row["fund_code"] == "australiansuper"
                and row["option_name"] == "Stable"
                and row["raw_name"] == "Industry Super Holdings Pty Ltd F/P"
                and row["disclosure_completeness"] == "ownership_only"
                and row["ownership_pct"] == "0.0018"
                for row in observations
            )
        )
        self.assertTrue(
            any(
                row["fund_code"] == "australiansuper"
                and row["option_name"] == "Stable"
                and row["raw_name"] == "Industry Super Holdings Pty Ltd F/P"
                and row["disclosure_completeness"] == "name_only"
                and row["ownership_pct"] is None
                and row["value_aud"] is None
                for row in observations
            )
        )

    def test_company_detail_endpoint_does_not_compute_cross_fund_totals_and_excludes_unresolved_discount_variant(self) -> None:
        response = self.client.get(f"/entities/companies/{self.entity_id}")
        self.assertEqual(200, response.status_code)

        payload = response.json()
        self.assertNotIn("total_ownership_pct", payload)
        self.assertNotIn("total_value_aud", payload)
        self.assertNotIn("unisuper", {row["fund_code"] for row in payload["observations"]})
        self.assertFalse(
            any("MINORITY DISCOUNT" in row["raw_name"] for row in payload["observations"])
        )
        self.assertIn("unresolved raw-name variants remain outside", payload["resolution_scope_note"])

    def test_company_detail_endpoint_does_not_fabricate_relationships_and_admin_ui_renders_same_data(self) -> None:
        response = self.client.get(f"/entities/companies/{self.entity_id}")
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual([], payload["relationships"])

        with self.SessionLocal() as session:
            self.assertEqual(
                0,
                session.scalar(
                    select(func.count(EntityRelationship.id)).where(
                        (EntityRelationship.from_entity_id == self.entity_id)
                        | (EntityRelationship.to_entity_id == self.entity_id)
                    )
                ),
            )
            self.assertEqual(
                0,
                session.scalar(
                    select(func.count(HoldingRelationship.id)).where(
                        HoldingRelationship.related_entity_id == self.entity_id
                    )
                ),
            )

        ui_response = self.client.get(f"/admin/ui/companies/{self.entity_id}")
        self.assertEqual(200, ui_response.status_code)
        self.assertIn("Named Private Company Ownership Index", ui_response.text)
        self.assertIn("Industry Super Holdings Pty Ltd", ui_response.text)
        self.assertIn("Industry Super Holdings Pty Ltd F/P", ui_response.text)
        self.assertIn("HC High Growth - Class A Option", ui_response.text)
        self.assertIn("0.1432", ui_response.text)
        self.assertIn("0.1317", ui_response.text)
        self.assertIn("Confidence: Reviewed", ui_response.text)
        self.assertIn("Observed holdings", ui_response.text)
        self.assertIn("Holder slices", ui_response.text)
        self.assertIn("No persisted relationships for this company in current stored truth.", ui_response.text)
        self.assertIn("Only one reporting period is currently available", ui_response.text)

    def test_company_detail_admin_ui_surfaces_value_band_rows_in_a_separate_facet(self) -> None:
        ui_response = self.client.get(f"/admin/ui/companies/{self.blackbird_entity_id}")
        self.assertEqual(200, ui_response.status_code)
        self.assertIn("Blackbird Ventures Growth I", ui_response.text)
        self.assertIn("Value-band disclosures", ui_response.text)
        self.assertIn("excluded from computed dollar totals", ui_response.text)
        self.assertIn("$100m-$500m", ui_response.text)
        self.assertIn("Confidence: Reviewed", ui_response.text)
        self.assertIn("Name Only", ui_response.text)
