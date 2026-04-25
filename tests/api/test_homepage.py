from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import Base, Entity, Holding, ReportingPeriod, SourceFile
from app.db.session import get_engine
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.entity_resolution.ifm_seed import ensure_ifm_seed
from app.entity_resolution.industry_super_holdings_seed import ensure_industry_super_holdings_seed
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


class TestHomepage(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'stage4_homepage.db'}"
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
            cls.ifm_entity_id = ensure_ifm_seed(session).id
            cls.industry_super_entity_id = ensure_industry_super_holdings_seed(session).id
            resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_homepage_renders_search_as_primary_action(self) -> None:
        response = self.client.get("/admin/ui")
        self.assertEqual(200, response.status_code)
        self.assertIn("Search the current private-markets index", response.text)
        self.assertIn('name="q"', response.text)
        self.assertIn('name="type"', response.text)
        self.assertIn("All results", response.text)
        self.assertIn("Companies", response.text)
        self.assertIn("Funds", response.text)
        self.assertIn("Managers", response.text)
        self.assertIn("/admin/ui/search", response.text)
        self.assertNotIn(">Matched-asset proof</a>", response.text)
        self.assertIn("Experimental surfaces:", response.text)
        self.assertIn("/admin/ui/matched-assets/australiansuper-stable-stage5-proof", response.text)
        self.assertIn("Search is the homepage's lead action", response.text)

    def test_homepage_renders_sql_backed_stats_and_honest_current_period_strip(self) -> None:
        response = self.client.get("/admin/ui")
        self.assertEqual(200, response.status_code)
        with self.SessionLocal() as session:
            loaded_filters = (
                SourceFile.is_current_version.is_(True),
                SourceFile.ingest_status == "loaded",
            )
            expected_stats = {
                "Funds loaded": session.scalar(
                    select(func.count(func.distinct(SourceFile.fund_id))).where(*loaded_filters)
                ),
                "Source files loaded": session.scalar(select(func.count(SourceFile.id)).where(*loaded_filters)),
                "Holding rows loaded": session.scalar(
                    select(func.count(Holding.id))
                    .join(SourceFile, SourceFile.id == Holding.source_file_id)
                    .where(*loaded_filters)
                ),
                "Reviewed companies": session.scalar(
                    select(func.count(func.distinct(Entity.id)))
                    .join(Holding, Holding.entity_id == Entity.id)
                    .join(SourceFile, SourceFile.id == Holding.source_file_id)
                    .where(
                        *loaded_filters,
                        Holding.is_aggregate.is_(False),
                        Entity.entity_type == "company",
                        Entity.confidence_tier == "seeded",
                    )
                ),
                "Reviewed managers": session.scalar(
                    select(func.count(func.distinct(Entity.id)))
                    .join(Holding, Holding.entity_id == Entity.id)
                    .join(SourceFile, SourceFile.id == Holding.source_file_id)
                    .where(
                        *loaded_filters,
                        Holding.is_aggregate.is_(False),
                        Entity.entity_type == "manager",
                        Entity.confidence_tier == "seeded",
                    )
                ),
            }

        for label, value in expected_stats.items():
            self.assertIn(f'<div class="metric-label">{label}</div>', response.text)
            self.assertIn(f'<div class="metric-value">{int(value or 0)}</div>', response.text)

        self.assertIn('<div class="metric-label">Latest reporting period</div>', response.text)
        self.assertIn('<div class="metric-value">31 Dec 2025</div>', response.text)
        self.assertIn("Reviewed companies", response.text)
        self.assertIn("Reviewed managers", response.text)
        self.assertIn("What changed this period", response.text)
        self.assertIn("Change unavailable", response.text)
        self.assertIn("2025-12-31", response.text)
        self.assertIn(
            "Latest period loaded: 31 Dec 2025. Change tracking unlocks once a second reporting period is loaded.",
            response.text,
        )
        self.assertNotIn("No prior loaded period yet", response.text)
        self.assertNotIn("Up ", response.text)
        self.assertNotIn("Down ", response.text)
        self.assertNotIn("Flat vs prior", response.text)

    def test_homepage_renders_curated_links_and_stage5_placeholder(self) -> None:
        response = self.client.get("/admin/ui")
        self.assertEqual(200, response.status_code)
        self.assertIn("Industry Super Holdings Pty Ltd", response.text)
        self.assertIn("IFM Investors Pty Ltd", response.text)
        self.assertIn(f"/admin/ui/companies/{self.industry_super_entity_id}", response.text)
        self.assertIn(f"/admin/ui/managers/{self.ifm_entity_id}", response.text)
        self.assertIn("AustralianSuper Stable matched-asset map proof", response.text)
        self.assertIn("/admin/ui/matched-assets/australiansuper-stable-stage5-proof", response.text)
        self.assertIn("Seven-row proof live", response.text)
        self.assertIn("not comprehensive national, cross-fund, or Cbus map coverage", response.text)
        self.assertIn("confidence, and source-row provenance", response.text)
        self.assertNotIn("mapped asset surface lands in Stage 5", response.text)
        self.assertNotIn("Coming later", response.text)
        self.assertIn("Disclosure completeness is the core rule of the product", response.text)
