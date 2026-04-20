from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from fastapi.testclient import TestClient
from sqlalchemy import func, or_, select
from sqlalchemy.orm import sessionmaker

from app.api.admin import get_db_session
from app.api.app import create_app
from app.db.models import (
    Base,
    Entity,
    EntityAlias,
    EntityRelationship,
    Holding,
    HoldingRelationship,
    ReportingPeriod,
)
from app.db.session import get_engine
from app.entity_resolution.deterministic import resolve_entities_deterministically
from app.entity_resolution.ifm_seed import (
    IFM_CANONICAL_NAME,
    ensure_ifm_art_sunsuper_issuer_relationship,
    ensure_ifm_seed,
)
from app.ingest.loader import (
    ingest_art_sunsuper_local_file,
    ingest_australiansuper_local_file,
    ingest_hostplus_local_file,
    ingest_unisuper_local_file,
)


ART_SUNSUPER_FIXTURE_PATH = Path("tests/fixtures/art_sunsuper_synthetic_stable_minimal.csv").resolve()
HOSTPLUS_FIXTURE_PATH = Path("tests/fixtures/hostplus_real_extract.csv").resolve()
UNISUPER_FIXTURE_PATH = Path("tests/fixtures/unisuper_real_extract.csv").resolve()
AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()


class TestIfmWorkedCaseContract(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'ifm_worked_case_contract.db'}"
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
            ifm_entity = ensure_ifm_seed(session)
            resolve_entities_deterministically(session, reporting_period_id=period.id)
            ensure_ifm_art_sunsuper_issuer_relationship(session, ifm_entity_id=ifm_entity.id)
            session.commit()

            cls.ifm_entity_id = ifm_entity.id

    @classmethod
    def tearDownClass(cls) -> None:
        cls.app.dependency_overrides.clear()
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_ifm_canonical_entity_and_aliases_exist_with_single_seeded_issuer_holding_relationship(self) -> None:
        with self.SessionLocal() as session:
            entity = session.get(Entity, self.ifm_entity_id)
            self.assertIsNotNone(entity)
            self.assertEqual(IFM_CANONICAL_NAME, entity.canonical_name)
            self.assertEqual("manager", entity.entity_type)

            aliases = session.scalars(
                select(EntityAlias.alias)
                .where(EntityAlias.entity_id == self.ifm_entity_id)
                .order_by(EntityAlias.alias.asc())
            ).all()
            self.assertEqual(
                ["IFM INVESTORS PTY LIMITED", "IFM Investors", "IFM Investors Pty Ltd"],
                aliases,
            )

            self.assertEqual(
                0,
                session.scalar(
                    select(func.count(EntityRelationship.id)).where(
                        or_(
                            EntityRelationship.from_entity_id == self.ifm_entity_id,
                            EntityRelationship.to_entity_id == self.ifm_entity_id,
                        )
                    )
                ),
            )
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count(HoldingRelationship.id)).where(
                        HoldingRelationship.related_entity_id == self.ifm_entity_id
                    )
                ),
            )

    def test_all_real_ifm_rows_link_to_the_same_canonical_entity_after_deterministic_resolution(self) -> None:
        with self.SessionLocal() as session:
            ifm_holdings = session.scalars(
                select(Holding)
                .where(
                    Holding.raw_name.in_(
                        ["IFM Investors Pty Ltd", "IFM INVESTORS PTY LIMITED", "IFM Investors"]
                    )
                )
                .order_by(Holding.id.asc())
            ).all()

            self.assertEqual(10, len(ifm_holdings))
            self.assertTrue(all(holding.entity_id == self.ifm_entity_id for holding in ifm_holdings))

            unisuper_ownership_row = next(holding for holding in ifm_holdings if holding.source_row_number == 3163)
            self.assertEqual("IFM INVESTORS PTY LIMITED", unisuper_ownership_row.raw_name)
            self.assertEqual("ownership_only", unisuper_ownership_row.disclosure_completeness)
            self.assertEqual(self.ifm_entity_id, unisuper_ownership_row.entity_id)
            self.assertEqual(0.309, float(unisuper_ownership_row.ownership_pct))

    def test_ifm_issuer_holding_relationship_seed_is_idempotent(self) -> None:
        with self.SessionLocal() as session:
            first = ensure_ifm_art_sunsuper_issuer_relationship(session, ifm_entity_id=self.ifm_entity_id)
            second = ensure_ifm_art_sunsuper_issuer_relationship(session, ifm_entity_id=self.ifm_entity_id)
            session.commit()

            self.assertEqual(first.id, second.id)
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count(HoldingRelationship.id)).where(
                        HoldingRelationship.related_entity_id == self.ifm_entity_id,
                        HoldingRelationship.relationship_role == "issuer",
                    )
                ),
            )

    def test_entity_detail_endpoint_returns_ifm_aliases_and_no_relationships(self) -> None:
        response = self.client.get(f"/entities/{self.ifm_entity_id}")
        self.assertEqual(200, response.status_code)

        payload = response.json()
        self.assertEqual(self.ifm_entity_id, payload["entity_id"])
        self.assertEqual(IFM_CANONICAL_NAME, payload["canonical_name"])
        self.assertEqual("manager", payload["entity_type"])
        self.assertEqual(
            ["IFM Investors Pty Ltd", "IFM INVESTORS PTY LIMITED", "IFM Investors"],
            payload["aliases"],
        )
        self.assertEqual([], payload["relationships"])

    def test_cross_adapter_lookup_by_entity_id_returns_ifm_observations_across_real_aliases(self) -> None:
        response = self.client.get("/entities/cross-adapter", params={"entity_id": self.ifm_entity_id})
        self.assertEqual(200, response.status_code)

        payload = response.json()
        self.assertEqual(self.ifm_entity_id, payload["entity_id"])
        self.assertEqual(IFM_CANONICAL_NAME, payload["lookup_name"])
        self.assertGreaterEqual(payload["fund_count"], 4)
        self.assertGreaterEqual(
            set(payload["matched_raw_names"]),
            {"IFM Investors", "IFM Investors Pty Ltd", "IFM INVESTORS PTY LIMITED"},
        )

        observations_by_fund = {}
        for observation in payload["observations"]:
            observations_by_fund.setdefault(observation["fund_code"], []).append(observation)

        self.assertTrue(
            any(
                row["option_name"] == "ART Stable"
                and row["raw_name"] == "IFM Investors Pty Ltd"
                and row["disclosure_completeness"] == "value_only"
                for row in observations_by_fund["art"]
            )
        )
        self.assertTrue(
            any(
                row["option_name"] == "HC High Growth - Class A Option"
                and row["raw_name"] == "IFM Investors Pty Ltd"
                and row["disclosure_completeness"] == "value_only"
                for row in observations_by_fund["hostplus"]
            )
        )
        self.assertTrue(
            any(
                row["option_name"] == "Conservative"
                and row["raw_name"] == "IFM INVESTORS PTY LIMITED"
                and row["disclosure_completeness"] == "ownership_only"
                for row in observations_by_fund["unisuper"]
            )
        )
        self.assertTrue(
            any(
                row["option_name"] == "Stable"
                and row["raw_name"] == "IFM Investors"
                and row["disclosure_completeness"] == "value_only"
                for row in observations_by_fund["australiansuper"]
            )
        )
