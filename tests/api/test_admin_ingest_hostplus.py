from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import Base, Holding, ReportingPeriod, SourceFile
from app.db.session import get_engine
from app.ingest.governance import (
    HOSTPLUS_AUSTRALIAN_SHARES_INDEXED_MAPPING_VERSION_ID,
    HOSTPLUS_AUSTRALIAN_SHARES_MAPPING_VERSION_ID,
    HOSTPLUS_BALANCED_MAPPING_VERSION_ID,
    HOSTPLUS_BONDS_INDEXED_MAPPING_VERSION_ID,
    HOSTPLUS_BONDS_MAPPING_VERSION_ID,
    HOSTPLUS_CASH_MAPPING_VERSION_ID,
    HOSTPLUS_CONSERVATIVE_MAPPING_VERSION_ID,
    HOSTPLUS_DEFENSIVE_MAPPING_VERSION_ID,
    HOSTPLUS_GROWTH_MAPPING_VERSION_ID,
    HOSTPLUS_INDEXED_BALANCED_MAPPING_VERSION_ID,
    HOSTPLUS_INDEXED_CONSERVATIVE_MAPPING_VERSION_ID,
    HOSTPLUS_INDEXED_DEFENSIVE_MAPPING_VERSION_ID,
    HOSTPLUS_INDEXED_GROWTH_MAPPING_VERSION_ID,
    HOSTPLUS_INDEXED_HIGH_GROWTH_MAPPING_VERSION_ID,
    HOSTPLUS_INDEXED_STABLE_MAPPING_VERSION_ID,
    HOSTPLUS_INTERNATIONAL_SHARES_MAPPING_VERSION_ID,
    HOSTPLUS_MAPPING_VERSION_ID,
    HOSTPLUS_SRI_BALANCED_MAPPING_VERSION_ID,
    HOSTPLUS_SRI_DEFENSIVE_MAPPING_VERSION_ID,
    HOSTPLUS_SRI_HIGH_GROWTH_MAPPING_VERSION_ID,
    HOSTPLUS_STABLE_MAPPING_VERSION_ID,
)


FIXTURE_PATH = Path("tests/fixtures/hostplus_real_extract.csv").resolve()
HOSTPLUS_FIXTURE_DIR = Path("tests/fixtures/real/hostplus").resolve()
AUSTRALIAN_SHARES_PATH = HOSTPLUS_FIXTURE_DIR / "australian-shares.csv"
AUSTRALIAN_SHARES_INDEXED_PATH = HOSTPLUS_FIXTURE_DIR / "australian-shares-indexed.csv"
CASH_PATH = HOSTPLUS_FIXTURE_DIR / "cash.csv"
INDEXED_HIGH_GROWTH_PATH = HOSTPLUS_FIXTURE_DIR / "indexed-high-growth.csv"
INTERNATIONAL_SHARES_PATH = HOSTPLUS_FIXTURE_DIR / "international-shares.csv"
SRI_HIGH_GROWTH_PATH = HOSTPLUS_FIXTURE_DIR / "sri-high-growth.csv"
BALANCED_PATH = HOSTPLUS_FIXTURE_DIR / "balanced.csv"
CONSERVATIVE_PATH = HOSTPLUS_FIXTURE_DIR / "conservative.csv"
DEFENSIVE_PATH = HOSTPLUS_FIXTURE_DIR / "defensive.csv"
GROWTH_PATH = HOSTPLUS_FIXTURE_DIR / "growth.csv"
STABLE_PATH = HOSTPLUS_FIXTURE_DIR / "stable.csv"
SRI_BALANCED_PATH = HOSTPLUS_FIXTURE_DIR / "sri-balanced.csv"
SRI_DEFENSIVE_PATH = HOSTPLUS_FIXTURE_DIR / "sri-defensive.csv"
BONDS_PATH = HOSTPLUS_FIXTURE_DIR / "bonds.csv"
BONDS_INDEXED_PATH = HOSTPLUS_FIXTURE_DIR / "bonds-indexed.csv"
INDEXED_BALANCED_PATH = HOSTPLUS_FIXTURE_DIR / "indexed-balanced.csv"
INDEXED_CONSERVATIVE_PATH = HOSTPLUS_FIXTURE_DIR / "indexed-conservative.csv"
INDEXED_DEFENSIVE_PATH = HOSTPLUS_FIXTURE_DIR / "indexed-defensive.csv"
INDEXED_GROWTH_PATH = HOSTPLUS_FIXTURE_DIR / "indexed-growth.csv"
INDEXED_STABLE_PATH = HOSTPLUS_FIXTURE_DIR / "indexed-stable.csv"

SOURCE_URLS = {
    AUSTRALIAN_SHARES_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Australian%20Shares.csv",
    AUSTRALIAN_SHARES_INDEXED_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Australian%20Shares%20-%20Indexed.csv",
    CASH_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Cash.csv",
    INDEXED_HIGH_GROWTH_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Indexed%20High%20Growth.csv",
    INTERNATIONAL_SHARES_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/International%20Shares.csv",
    SRI_HIGH_GROWTH_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Socially%20Responsible%20Investment%20(SRI)%20-%20High%20Growth.csv",
    BALANCED_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Balanced.csv",
    CONSERVATIVE_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Conservative.csv",
    DEFENSIVE_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Defensive.csv",
    GROWTH_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Growth.csv",
    STABLE_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Stable.csv",
    SRI_BALANCED_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Socially%20Responsible%20Investment%20(SRI)%20-%20Balanced.csv",
    SRI_DEFENSIVE_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Socially%20Responsible%20Investment%20(SRI)%20-%20Defensive.csv",
    BONDS_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Bonds.csv",
    BONDS_INDEXED_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Bonds%20-%20Indexed.csv",
    INDEXED_BALANCED_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Indexed%20Balanced.csv",
    INDEXED_CONSERVATIVE_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Indexed%20Conservative.csv",
    INDEXED_DEFENSIVE_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Indexed%20Defensive.csv",
    INDEXED_GROWTH_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Indexed%20Growth.csv",
    INDEXED_STABLE_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Indexed%20Stable.csv",
}

BATCH_CASES = (
    (AUSTRALIAN_SHARES_PATH, SOURCE_URLS[AUSTRALIAN_SHARES_PATH], HOSTPLUS_AUSTRALIAN_SHARES_MAPPING_VERSION_ID, 343),
    (
        AUSTRALIAN_SHARES_INDEXED_PATH,
        SOURCE_URLS[AUSTRALIAN_SHARES_INDEXED_PATH],
        HOSTPLUS_AUSTRALIAN_SHARES_INDEXED_MAPPING_VERSION_ID,
        215,
    ),
    (CASH_PATH, SOURCE_URLS[CASH_PATH], HOSTPLUS_CASH_MAPPING_VERSION_ID, 5),
    (
        INDEXED_HIGH_GROWTH_PATH,
        SOURCE_URLS[INDEXED_HIGH_GROWTH_PATH],
        HOSTPLUS_INDEXED_HIGH_GROWTH_MAPPING_VERSION_ID,
        2531,
    ),
    (
        INTERNATIONAL_SHARES_PATH,
        SOURCE_URLS[INTERNATIONAL_SHARES_PATH],
        HOSTPLUS_INTERNATIONAL_SHARES_MAPPING_VERSION_ID,
        2856,
    ),
    (
        SRI_HIGH_GROWTH_PATH,
        SOURCE_URLS[SRI_HIGH_GROWTH_PATH],
        HOSTPLUS_SRI_HIGH_GROWTH_MAPPING_VERSION_ID,
        565,
    ),
)

CORE_DIVERSIFIED_CASES = (
    (BALANCED_PATH, SOURCE_URLS[BALANCED_PATH], HOSTPLUS_BALANCED_MAPPING_VERSION_ID, 3308, 5),
    (CONSERVATIVE_PATH, SOURCE_URLS[CONSERVATIVE_PATH], HOSTPLUS_CONSERVATIVE_MAPPING_VERSION_ID, 3308, 5),
    (DEFENSIVE_PATH, SOURCE_URLS[DEFENSIVE_PATH], HOSTPLUS_DEFENSIVE_MAPPING_VERSION_ID, 3274, 5),
    (GROWTH_PATH, SOURCE_URLS[GROWTH_PATH], HOSTPLUS_GROWTH_MAPPING_VERSION_ID, 3285, 5),
    (STABLE_PATH, SOURCE_URLS[STABLE_PATH], HOSTPLUS_STABLE_MAPPING_VERSION_ID, 3308, 5),
    (SRI_BALANCED_PATH, SOURCE_URLS[SRI_BALANCED_PATH], HOSTPLUS_SRI_BALANCED_MAPPING_VERSION_ID, 597, 0),
    (SRI_DEFENSIVE_PATH, SOURCE_URLS[SRI_DEFENSIVE_PATH], HOSTPLUS_SRI_DEFENSIVE_MAPPING_VERSION_ID, 588, 0),
)

RESIDUAL_SUPER_CASES = (
    (BONDS_PATH, SOURCE_URLS[BONDS_PATH], HOSTPLUS_BONDS_MAPPING_VERSION_ID, 13),
    (BONDS_INDEXED_PATH, SOURCE_URLS[BONDS_INDEXED_PATH], HOSTPLUS_BONDS_INDEXED_MAPPING_VERSION_ID, 5),
    (INDEXED_BALANCED_PATH, SOURCE_URLS[INDEXED_BALANCED_PATH], HOSTPLUS_INDEXED_BALANCED_MAPPING_VERSION_ID, 2536),
    (
        INDEXED_CONSERVATIVE_PATH,
        SOURCE_URLS[INDEXED_CONSERVATIVE_PATH],
        HOSTPLUS_INDEXED_CONSERVATIVE_MAPPING_VERSION_ID,
        2536,
    ),
    (INDEXED_DEFENSIVE_PATH, SOURCE_URLS[INDEXED_DEFENSIVE_PATH], HOSTPLUS_INDEXED_DEFENSIVE_MAPPING_VERSION_ID, 2536),
    (INDEXED_GROWTH_PATH, SOURCE_URLS[INDEXED_GROWTH_PATH], HOSTPLUS_INDEXED_GROWTH_MAPPING_VERSION_ID, 2533),
    (INDEXED_STABLE_PATH, SOURCE_URLS[INDEXED_STABLE_PATH], HOSTPLUS_INDEXED_STABLE_MAPPING_VERSION_ID, 2536),
)


class TestAdminHostPlusIngestEndpoint(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_hostplus_api.db'}"
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

    def test_admin_ingest_local_file_hostplus_endpoint(self) -> None:
        response = self.client.post(
            "/admin/ingest/local-file/hostplus",
            json={
                "file_path": str(FIXTURE_PATH),
                "fund_code": "hostplus",
                "fund_name": "Hostplus",
                "reporting_period_id": self.reporting_period_id,
            },
        )
        self.assertEqual(200, response.status_code)
        payload = response.json()
        self.assertEqual(3215, payload["rows_staged"])
        self.assertEqual(3215, payload["rows_inserted"])
        self.assertIsNotNone(payload["investment_option_id"])
        self.assertEqual(
            ["Decoded Host-Plus source using UTF-8 errors='replace'; replacement_count=3"],
            payload["warnings"],
        )

        with self.SessionLocal() as session:
            source_file = session.get(SourceFile, payload["source_file_id"])
            self.assertEqual("HostPlusPhdStateMachineAdapter", source_file.adapter_key)
            self.assertEqual(HOSTPLUS_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(payload["investment_option_id"], source_file.investment_option_id)

        listing = self.client.get("/admin/source-files")
        self.assertEqual(200, listing.status_code)
        self.assertEqual("HostPlusPhdStateMachineAdapter", listing.json()[0]["adapter_key"])
        self.assertEqual(3215, listing.json()[0]["rows_loaded"])
        self.assertEqual(3, listing.json()[0]["encoding_replacement_count"])

        detail = self.client.get(f"/admin/source-files/{payload['source_file_id']}", params={"page": 1, "size": 200})
        self.assertEqual(200, detail.status_code)
        self.assertEqual("HC High Growth - Class A Option", detail.json()["holdings"][0]["source_option_name"])

        admin_ui_detail = self.client.get(f"/admin/ui/source-files/{payload['source_file_id']}", params={"page": 1, "size": 200})
        self.assertEqual(200, admin_ui_detail.status_code)
        self.assertIn("HOSTPLUS_HC_HIGH_GROWTH_CLASS_A_OPTION", admin_ui_detail.text)

        entity_detail = self.client.get("/entities/by-name", params={"name": "Citigroup Inc"})
        self.assertEqual(200, entity_detail.status_code)
        self.assertEqual(38, entity_detail.json()["observation_count"])
        self.assertEqual(
            {"HC High Growth - Class A Option"},
            {row["option_name"] for row in entity_detail.json()["observations"]},
        )
        self.assertEqual(
            {"AUD", "USD"},
            {row["currency_raw"] for row in entity_detail.json()["observations"] if row["currency_raw"] in {"AUD", "USD"}},
        )

    def test_admin_ingest_latest_period_batch_uses_mapping_seeds_and_source_urls(self) -> None:
        for file_path, source_url, mapping_version_id, expected_rows in BATCH_CASES:
            with self.subTest(file=file_path.name):
                response = self.client.post(
                    "/admin/ingest/local-file/hostplus",
                    json={
                        "file_path": str(file_path),
                        "fund_code": "hostplus",
                        "fund_name": "Hostplus",
                        "reporting_period_id": self.reporting_period_id,
                        "source_url": source_url,
                    },
                )
                self.assertEqual(200, response.status_code)
                payload = response.json()
                self.assertEqual(expected_rows, payload["rows_staged"])
                self.assertEqual(expected_rows, payload["rows_inserted"])
                self.assertEqual(0, payload["rows_skipped_existing"])
                self.assertEqual(
                    ["Decoded Host-Plus source using UTF-8 errors='replace'; replacement_count=3"],
                    payload["warnings"],
                )

                with self.SessionLocal() as session:
                    source_file = session.get(SourceFile, payload["source_file_id"])
                    self.assertEqual("HostPlusPhdStateMachineAdapter", source_file.adapter_key)
                    self.assertEqual(mapping_version_id, source_file.mapping_version_id)
                    self.assertEqual(source_url, source_file.source_url)
                    self.assertEqual(3, source_file.encoding_replacement_count)

        with self.SessionLocal() as session:
            self.assertEqual(sum(case[3] for case in BATCH_CASES), session.query(Holding).count())
            source_urls = {source_file.source_url for source_file in session.query(SourceFile).all()}
            self.assertEqual({case[1] for case in BATCH_CASES}, source_urls)
            self.assertFalse(any(source_url.endswith("/High%20Growth.csv") for source_url in source_urls))
            self.assertFalse(any("Defined%20Benefit" in source_url for source_url in source_urls))
            self.assertFalse(any("retirement" in source_url.casefold() or "pension" in source_url.casefold() for source_url in source_urls))

    def test_admin_ingest_core_diversified_batch_uses_extension_mapping_seeds(self) -> None:
        source_file_ids: list[int] = []
        for file_path, source_url, mapping_version_id, expected_rows, expected_address_rows in CORE_DIVERSIFIED_CASES:
            with self.subTest(file=file_path.name):
                response = self.client.post(
                    "/admin/ingest/local-file/hostplus",
                    json={
                        "file_path": str(file_path),
                        "fund_code": "hostplus",
                        "fund_name": "Hostplus",
                        "reporting_period_id": self.reporting_period_id,
                        "source_url": source_url,
                    },
                )
                self.assertEqual(200, response.status_code)
                payload = response.json()
                self.assertEqual(expected_rows, payload["rows_staged"])
                self.assertEqual(expected_rows, payload["rows_inserted"])
                self.assertEqual(0, payload["rows_skipped_existing"])
                self.assertEqual(
                    ["Decoded Host-Plus source using UTF-8 errors='replace'; replacement_count=3"],
                    payload["warnings"],
                )

                with self.SessionLocal() as session:
                    source_file = session.get(SourceFile, payload["source_file_id"])
                    self.assertEqual("HostPlusPhdStateMachineAdapter", source_file.adapter_key)
                    self.assertEqual(mapping_version_id, source_file.mapping_version_id)
                    self.assertEqual(source_url, source_file.source_url)
                    self.assertEqual(3, source_file.encoding_replacement_count)
                    self.assertEqual(
                        expected_address_rows,
                        session.query(Holding)
                        .filter(Holding.source_file_id == payload["source_file_id"], Holding.address.is_not(None))
                        .count(),
                    )
                source_file_ids.append(payload["source_file_id"])

        with self.SessionLocal() as session:
            self.assertEqual(sum(case[3] for case in CORE_DIVERSIFIED_CASES), session.query(Holding).count())
            self.assertEqual(
                0,
                session.query(Holding)
                .filter(
                    Holding.source_file_id.in_(source_file_ids),
                    Holding.raw_name.in_(["Forwards", "Futures", "Swaps", "AUD"]),
                )
                .count(),
            )
            self.assertEqual(
                0,
                session.query(Holding)
                .filter(
                    Holding.source_file_id.in_(source_file_ids),
                    Holding.raw_name.in_(
                        ["Fixed Income", "Unlisted Property", "Unlisted Infrastructure", "Unlisted Alternatives"]
                    ),
                )
                .count(),
            )
            source_urls = {source_file.source_url for source_file in session.query(SourceFile).all()}
            self.assertEqual({case[1] for case in CORE_DIVERSIFIED_CASES}, source_urls)
            self.assertFalse(any(source_url.endswith("/High%20Growth.csv") for source_url in source_urls))
            self.assertFalse(any("Bonds" in source_url or "Indexed" in source_url for source_url in source_urls))
            self.assertFalse(any("Defined%20Benefit" in source_url for source_url in source_urls))
            self.assertFalse(any("retirement" in source_url.casefold() or "pension" in source_url.casefold() for source_url in source_urls))

    def test_admin_ingest_residual_super_batch_uses_completion_mapping_seeds(self) -> None:
        source_file_ids: list[int] = []
        for file_path, source_url, mapping_version_id, expected_rows in RESIDUAL_SUPER_CASES:
            with self.subTest(file=file_path.name):
                response = self.client.post(
                    "/admin/ingest/local-file/hostplus",
                    json={
                        "file_path": str(file_path),
                        "fund_code": "hostplus",
                        "fund_name": "Hostplus",
                        "reporting_period_id": self.reporting_period_id,
                        "source_url": source_url,
                    },
                )
                self.assertEqual(200, response.status_code)
                payload = response.json()
                self.assertEqual(expected_rows, payload["rows_staged"])
                self.assertEqual(expected_rows, payload["rows_inserted"])
                self.assertEqual(0, payload["rows_skipped_existing"])
                self.assertEqual(
                    ["Decoded Host-Plus source using UTF-8 errors='replace'; replacement_count=3"],
                    payload["warnings"],
                )

                with self.SessionLocal() as session:
                    source_file = session.get(SourceFile, payload["source_file_id"])
                    self.assertEqual("HostPlusPhdStateMachineAdapter", source_file.adapter_key)
                    self.assertEqual(mapping_version_id, source_file.mapping_version_id)
                    self.assertEqual(source_url, source_file.source_url)
                    self.assertEqual(3, source_file.encoding_replacement_count)
                    self.assertEqual(
                        0,
                        session.query(Holding)
                        .filter(Holding.source_file_id == payload["source_file_id"], Holding.address.is_not(None))
                        .count(),
                    )
                source_file_ids.append(payload["source_file_id"])

        with self.SessionLocal() as session:
            self.assertEqual(sum(case[3] for case in RESIDUAL_SUPER_CASES), session.query(Holding).count())
            self.assertEqual(
                0,
                session.query(Holding)
                .filter(
                    Holding.source_file_id.in_(source_file_ids),
                    Holding.raw_name.in_(["Forwards", "Futures", "Swaps", "AUD"]),
                )
                .count(),
            )
            self.assertEqual(
                0,
                session.query(Holding)
                .filter(
                    Holding.source_file_id.in_(source_file_ids),
                    Holding.source_asset_class_raw.in_(
                        ["Unlisted Property", "Unlisted Infrastructure", "Unlisted Alternatives"]
                    ),
                )
                .count(),
            )
            source_urls = {source_file.source_url for source_file in session.query(SourceFile).all()}
            self.assertEqual({case[1] for case in RESIDUAL_SUPER_CASES}, source_urls)
            self.assertFalse(any(source_url.endswith("/High%20Growth.csv") for source_url in source_urls))
            self.assertFalse(any("Defined%20Benefit" in source_url for source_url in source_urls))
            self.assertFalse(any("retirement" in source_url.casefold() or "pension" in source_url.casefold() for source_url in source_urls))
