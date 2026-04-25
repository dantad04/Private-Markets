from __future__ import annotations

from datetime import UTC, date, datetime
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import (
    Base,
    CanonicalAssetClass,
    Entity,
    Fund,
    Holding,
    InvestmentOption,
    ReportingPeriod,
    SourceFile,
)
from app.db.session import get_engine
from app.read_models import get_demo_entity_explorer


class TestDemoDiscoveryLayer(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'demo_discovery.db'}"
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
            cls._seed_demo_fixture(session)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.tempdir.cleanup()

    @classmethod
    def _seed_demo_fixture(cls, session) -> None:
        period = ReportingPeriod(
            period_end_date=date(2025, 12, 31),
            disclosure_due_date=date(2026, 3, 31),
            label="2025-12-31",
            source_cycle="semi_annual",
        )
        session.add(period)
        session.flush()

        asset_classes = {}
        for code, label in (
            ("unlisted_equity", "Unlisted Equity"),
            ("unlisted_infrastructure", "Unlisted Infrastructure"),
            ("unlisted_property", "Unlisted Property"),
        ):
            asset_class = CanonicalAssetClass(code=code, label=label)
            session.add(asset_class)
            asset_classes[code] = asset_class
        session.flush()

        funds: dict[str, Fund] = {}
        options: dict[tuple[str, str], InvestmentOption] = {}
        source_files: dict[tuple[str, str], SourceFile] = {}
        for fund_code, fund_name, option_code, option_name in (
            ("alpha", "Alpha Super", "alpha-growth", "Alpha Growth"),
            ("alpha", "Alpha Super", "alpha-balanced", "Alpha Balanced"),
            ("beta", "Beta Super", "beta-growth", "Beta Growth"),
            ("aware", "Aware Super", "aware-growth", "Aware Growth"),
        ):
            fund = funds.get(fund_code)
            if fund is None:
                fund = Fund(code=fund_code, name=fund_name)
                session.add(fund)
                session.flush()
                funds[fund_code] = fund
            option = InvestmentOption(
                fund_id=fund.id,
                source_option_code=option_code,
                source_option_name=option_name,
            )
            session.add(option)
            session.flush()
            options[(fund_code, option_code)] = option
            source_file = SourceFile(
                fund_id=fund.id,
                investment_option_id=option.id,
                adapter_key=f"demo-{fund_code}-{option_code}",
                source_url=f"https://example.test/{fund_code}/{option_code}.csv",
                checksum=f"{fund_code}-{option_code}".ljust(64, "0")[:64],
                reporting_period_id=period.id,
                ingest_status="loaded",
                received_at=datetime(2026, 1, 10, tzinfo=UTC),
                is_current_version=True,
            )
            session.add(source_file)
            session.flush()
            source_files[(fund_code, option_code)] = source_file

        entities = {
            "alpha": Entity(
                entity_type="company",
                canonical_name="Alpha Value Pty Ltd",
                confidence_tier="seeded",
            ),
            "beta": Entity(
                entity_type="manager",
                canonical_name="Beta Multi Fund Manager Pty Ltd",
                confidence_tier="seeded",
            ),
            "gamma": Entity(
                entity_type="company",
                canonical_name="Gamma Multi Option Pty Ltd",
                confidence_tier="seeded",
            ),
            "delta": Entity(
                entity_type="asset",
                canonical_name="Delta Row Count Trust",
                confidence_tier="seeded",
            ),
            "epsilon": Entity(
                entity_type="company",
                canonical_name="Epsilon Ownership Pty Ltd",
                confidence_tier="seeded",
            ),
            "kappa": Entity(
                entity_type="asset",
                canonical_name="Kappa Carry Trust",
                confidence_tier="seeded",
            ),
            "ifm": Entity(
                entity_type="manager",
                canonical_name="IFM Investors Pty Ltd",
                confidence_tier="seeded",
            ),
            "industry": Entity(
                entity_type="company",
                canonical_name="Industry Super Holdings Pty Ltd",
                confidence_tier="seeded",
            ),
        }
        session.add_all(entities.values())
        for index in range(55):
            entities[f"paged-{index:02d}"] = Entity(
                entity_type="asset",
                canonical_name=f"Paged Entity {index:02d}",
                confidence_tier="seeded",
            )
            session.add(entities[f"paged-{index:02d}"])
        session.flush()

        row_number = 1

        def add_holding(
            *,
            entity_key: str,
            raw_name: str,
            fund_code: str,
            option_code: str,
            disclosure: str,
            asset_class_code: str,
            value_aud: Decimal | None = None,
            ownership_pct: Decimal | None = None,
            manager_key: str | None = None,
            issuer_key: str | None = None,
        ) -> None:
            nonlocal row_number
            fund = funds[fund_code]
            option = options[(fund_code, option_code)]
            source_file = source_files[(fund_code, option_code)]
            holding = Holding(
                source_file_id=source_file.id,
                source_fund_id=fund.id,
                source_option_id=option.id,
                reporting_period_id=period.id,
                entity_id=entities[entity_key].id,
                manager_entity_id=entities[manager_key].id if manager_key else None,
                issuer_entity_id=entities[issuer_key].id if issuer_key else None,
                raw_name=raw_name,
                value_aud=value_aud,
                ownership_pct=ownership_pct,
                is_aggregate=False,
                disclosure_completeness=disclosure,
                canonical_asset_class_id=asset_classes[asset_class_code].id,
                source_asset_class_raw=asset_classes[asset_class_code].label,
                source_row_hash=f"demo-row-{row_number}",
                source_row_number=row_number,
                raw_payload_json={"raw_name": raw_name},
                parse_warning_flags=[],
                metadata_attached_from_row_numbers=[],
            )
            row_number += 1
            session.add(holding)

        add_holding(
            entity_key="alpha",
            raw_name="Alpha Value Pty Ltd",
            fund_code="alpha",
            option_code="alpha-growth",
            disclosure="fully_disclosed",
            asset_class_code="unlisted_equity",
            value_aud=Decimal("5000"),
        )
        add_holding(
            entity_key="kappa",
            raw_name="Kappa Carry Trust",
            fund_code="beta",
            option_code="beta-growth",
            disclosure="value_only",
            asset_class_code="unlisted_property",
            value_aud=Decimal("100"),
            manager_key="beta",
        )
        add_holding(
            entity_key="kappa",
            raw_name="Kappa Carry Trust Alpha",
            fund_code="alpha",
            option_code="alpha-growth",
            disclosure="value_only",
            asset_class_code="unlisted_property",
            value_aud=Decimal("50"),
            manager_key="beta",
        )

        for fund_code, option_code in (
            ("alpha", "alpha-growth"),
            ("alpha", "alpha-balanced"),
            ("beta", "beta-growth"),
        ):
            add_holding(
                entity_key="gamma",
                raw_name="Gamma Multi Option Pty Ltd",
                fund_code=fund_code,
                option_code=option_code,
                disclosure="value_only",
                asset_class_code="unlisted_equity",
                value_aud=Decimal("10"),
            )

        for index in range(4):
            add_holding(
                entity_key="delta",
                raw_name=f"Delta Row Count Trust {index}",
                fund_code="alpha",
                option_code="alpha-growth",
                disclosure="name_only",
                asset_class_code="unlisted_property",
            )

        for raw_name, ownership_pct in (
            ("RUMIN8", Decimal("0.15")),
            ("FSSSP", Decimal("1.0")),
            ("Epsilon Sidecar", Decimal("0.20")),
        ):
            add_holding(
                entity_key="epsilon",
                raw_name=raw_name,
                fund_code="aware",
                option_code="aware-growth",
                disclosure="ownership_only",
                asset_class_code="unlisted_infrastructure",
                ownership_pct=ownership_pct,
            )

        add_holding(
            entity_key="ifm",
            raw_name="IFM Investors Pty Ltd",
            fund_code="alpha",
            option_code="alpha-balanced",
            disclosure="value_only",
            asset_class_code="unlisted_infrastructure",
            value_aud=Decimal("59"),
        )
        add_holding(
            entity_key="industry",
            raw_name="Industry Super Holdings Pty Ltd",
            fund_code="alpha",
            option_code="alpha-balanced",
            disclosure="fully_disclosed",
            asset_class_code="unlisted_equity",
            value_aud=Decimal("250"),
            ownership_pct=Decimal("0.05"),
        )

        for index in range(55):
            add_holding(
                entity_key=f"paged-{index:02d}",
                raw_name=f"Paged Entity {index:02d}",
                fund_code="alpha",
                option_code="alpha-growth",
                disclosure="name_only",
                asset_class_code="unlisted_property",
                value_aud=Decimal("0"),
            )

    def test_demo_dashboard_renders_search_stats_curated_links_and_entry_points(self) -> None:
        response = self.client.get("/demo")
        self.assertEqual(200, response.status_code)
        self.assertIn("Explore the current private-markets corpus", response.text)
        self.assertIn('name="q"', response.text)
        self.assertIn('name="type"', response.text)
        self.assertIn("Funds loaded", response.text)
        self.assertIn("Source files loaded", response.text)
        self.assertIn("Holding rows loaded", response.text)
        self.assertIn("Reviewed companies", response.text)
        self.assertIn("Reviewed managers", response.text)
        self.assertIn("Latest reporting period", response.text)
        self.assertIn("IFM Investors", response.text)
        self.assertIn("Industry Super Holdings", response.text)
        self.assertIn("RUMIN8", response.text)
        self.assertIn("FSSSP", response.text)
        self.assertNotIn("HARRISON AI", response.text)
        self.assertIn("Experimental seven-row coordinate proof — not full coverage.", response.text)
        self.assertIn("/demo/entities?type=company", response.text)
        self.assertIn("/demo/entities?type=manager", response.text)
        self.assertIn("/admin/ui/source-files", response.text)
        self.assertIn("/demo/entities?sort=value_aud_desc", response.text)
        self.assertIn(
            "Latest period loaded: 31 Dec 2025. Change tracking unlocks once a second reporting period is loaded.",
            response.text,
        )

    def test_sort_options_return_expected_descending_order(self) -> None:
        expected_first_by_sort = {
            "value_aud_desc": "Alpha Value Pty Ltd",
            "fund_count_desc": "Beta Multi Fund Manager Pty Ltd",
            "option_count_desc": "Gamma Multi Option Pty Ltd",
            "row_count_desc": "Delta Row Count Trust",
            "ownership_count_desc": "Epsilon Ownership Pty Ltd",
        }
        with self.SessionLocal() as session:
            for sort_key, expected_name in expected_first_by_sort.items():
                explorer = get_demo_entity_explorer(session, sort=sort_key)
                self.assertGreaterEqual(explorer.total_rows, 1)
                self.assertEqual(expected_name, explorer.rows[0].entity_name)

    def test_filters_narrow_results_by_type_disclosure_fund_and_asset_class(self) -> None:
        with self.SessionLocal() as session:
            managers = get_demo_entity_explorer(session, entity_type="manager", sort="fund_count_desc")
            self.assertTrue(managers.rows)
            self.assertTrue(all(row.entity_type == "manager" for row in managers.rows))
            self.assertEqual("Beta Multi Fund Manager Pty Ltd", managers.rows[0].entity_name)

            ownership_only = get_demo_entity_explorer(
                session,
                disclosure_completeness=["ownership_only"],
            )
            self.assertEqual(["Epsilon Ownership Pty Ltd"], [row.entity_name for row in ownership_only.rows])

            aware_only = get_demo_entity_explorer(session, fund=["aware"])
            self.assertEqual(["Epsilon Ownership Pty Ltd"], [row.entity_name for row in aware_only.rows])

            infrastructure_only = get_demo_entity_explorer(
                session,
                canonical_asset_class=["unlisted_infrastructure"],
            )
            self.assertIn(
                "Epsilon Ownership Pty Ltd",
                [row.entity_name for row in infrastructure_only.rows],
            )
            self.assertNotIn(
                "Delta Row Count Trust",
                [row.entity_name for row in infrastructure_only.rows],
            )

    def test_pagination_round_trips_query_params(self) -> None:
        response = self.client.get("/demo/entities", params={"sort": "value_aud_desc", "page": 2})
        self.assertEqual(200, response.status_code)
        self.assertIn("Page <code>2</code>", response.text)
        self.assertIn("Paged Entity", response.text)
        self.assertIn("sort=value_aud_desc", response.text)
        self.assertIn("page=1", response.text)

    def test_unknown_sort_key_is_rejected(self) -> None:
        response = self.client.get("/demo/entities", params={"sort": "not_a_sort"})
        self.assertEqual(400, response.status_code)
        self.assertIn("Unknown entity explorer sort key", response.text)

    def test_disclosure_mix_counts_match_underlying_group_counts(self) -> None:
        with self.SessionLocal() as session:
            explorer = get_demo_entity_explorer(
                session,
                disclosure_completeness=["ownership_only"],
            )
            row = explorer.rows[0]
            disclosure_mix = dict(row.disclosure_mix)
            self.assertEqual(3, row.row_count)
            self.assertEqual(3, row.ownership_count)
            self.assertEqual({"ownership_only": 3}, disclosure_mix)

        response = self.client.get(
            "/demo/entities",
            params={"disclosure_completeness": "ownership_only"},
        )
        self.assertEqual(200, response.status_code)
        self.assertIn("Ownership only", response.text)
        self.assertIn('<span class="badge-count">3</span>', response.text)

    def test_single_role_manager_page_has_no_multi_role_banner(self) -> None:
        with self.SessionLocal() as session:
            beta_manager_id = session.scalar(
                select(Entity.id).where(Entity.canonical_name == "Beta Multi Fund Manager Pty Ltd")
            )
        self.assertIsNotNone(beta_manager_id)

        response = self.client.get(f"/admin/ui/managers/{beta_manager_id}")
        self.assertEqual(200, response.status_code)
        self.assertIn("Disclosed as manager", response.text)
        self.assertNotIn("Disclosed as held entity", response.text)
        self.assertNotIn("Disclosed as issuer", response.text)
        self.assertNotIn("This entity is observed in multiple roles", response.text)

    def test_top_nav_links_resolve_from_touched_pages(self) -> None:
        with self.SessionLocal() as session:
            company_id = session.scalar(
                select(Entity.id).where(Entity.canonical_name == "Alpha Value Pty Ltd")
            )
            manager_id = session.scalar(
                select(Entity.id).where(Entity.canonical_name == "Beta Multi Fund Manager Pty Ltd")
            )
        self.assertIsNotNone(company_id)
        self.assertIsNotNone(manager_id)

        expected_nav_links = [
            ('href="http://testserver/demo"', "Home"),
            ('href="http://testserver/admin/ui/search"', "Search"),
            ('href="http://testserver/demo/entities?type=company"', "Companies"),
            ('href="http://testserver/demo/entities?type=manager"', "Managers"),
            ('href="http://testserver/admin/ui/source-files"', "Funds"),
        ]
        page_paths = [
            "/demo",
            "/demo/entities?type=company",
            "/admin/ui/search",
            f"/admin/ui/companies/{company_id}",
            f"/admin/ui/managers/{manager_id}",
            "/admin/ui/source-files",
            "/admin/ui/matched-assets/australiansuper-stable-stage5-proof",
        ]
        for page_path in page_paths:
            response = self.client.get(page_path)
            self.assertEqual(200, response.status_code, page_path)
            for href, label in expected_nav_links:
                self.assertIn(href, response.text, page_path)
                self.assertIn(f">{label}</a>", response.text, page_path)
            self.assertNotIn(">Matched-asset proof</a>", response.text)

        for href, _label in expected_nav_links:
            path = href.removeprefix('href="http://testserver').removesuffix('"')
            self.assertEqual(200, self.client.get(path).status_code, path)
