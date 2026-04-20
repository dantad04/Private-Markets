from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

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
from app.entity_resolution.industry_super_holdings_seed import (
    INDUSTRY_SUPER_HOLDINGS_CANONICAL_NAME,
    INDUSTRY_SUPER_HOLDINGS_OBSERVED_ALIASES,
    ensure_industry_super_holdings_seed,
)
from app.ingest.loader import (
    ingest_art_qsuper_local_file,
    ingest_art_sunsuper_local_file,
    ingest_australiansuper_local_file,
    ingest_hostplus_local_file,
    ingest_unisuper_local_file,
)
from app.read_models import get_cross_adapter_holdings_by_entity_id


ART_SUNSUPER_FIXTURE_PATH = Path("tests/fixtures/art_sunsuper_synthetic_stable_minimal.csv").resolve()
ART_QSUPER_FIXTURE_PATH = Path("tests/fixtures/art_qsuper_synthetic_balanced_minimal.csv").resolve()
HOSTPLUS_FIXTURE_PATH = Path("tests/fixtures/hostplus_real_extract.csv").resolve()
UNISUPER_FIXTURE_PATH = Path("tests/fixtures/unisuper_real_extract.csv").resolve()
AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()
OBSERVED_NAME_SOURCE_PATHS = (
    ART_SUNSUPER_FIXTURE_PATH,
    ART_QSUPER_FIXTURE_PATH,
    HOSTPLUS_FIXTURE_PATH,
    UNISUPER_FIXTURE_PATH,
    AUSTRALIANSUPER_STABLE_FIXTURE_PATH,
)
UNRESOLVED_UNISUPER_DISCOUNT_NAME = "INDUSTRY SUPER HOLDINGS PTY LTD 7.5% MINORITY DISCOUNT"
ALIASES_TO_SOURCE_PATHS = {
    "Industry Super Holdings": HOSTPLUS_FIXTURE_PATH,
    "Industry Super Holdings Pty Ltd": ART_QSUPER_FIXTURE_PATH,
    "Industry Super Holdings Pty Ltd F/P": AUSTRALIANSUPER_STABLE_FIXTURE_PATH,
}


class TestIndustrySuperHoldingsSeed(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'industry_super_holdings_seed.db'}"
        cls.engine = get_engine(cls.database_url)
        Base.metadata.create_all(cls.engine)
        cls.SessionLocal = sessionmaker(bind=cls.engine, autoflush=False, autocommit=False, future=True)

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
            cls.entity_id = entity.id
            cls.period_id = period.id
            cls.resolution_summary = resolve_entities_deterministically(session, reporting_period_id=period.id)
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_canonical_seed_exists_with_real_observed_aliases_only(self) -> None:
        with self.SessionLocal() as session:
            entity = session.get(Entity, self.entity_id)
            self.assertIsNotNone(entity)
            self.assertEqual(INDUSTRY_SUPER_HOLDINGS_CANONICAL_NAME, entity.canonical_name)
            self.assertEqual("company", entity.entity_type)
            self.assertIsNone(entity.abn)

            aliases = session.scalars(
                select(EntityAlias.alias)
                .where(EntityAlias.entity_id == self.entity_id)
                .order_by(EntityAlias.alias.asc())
            ).all()
            self.assertEqual(
                [
                    "Industry Super Holdings",
                    "Industry Super Holdings Pty Ltd",
                    "Industry Super Holdings Pty Ltd F/P",
                ],
                aliases,
            )

            for alias in aliases:
                self.assertIn(alias, ALIASES_TO_SOURCE_PATHS[alias].read_text(errors="ignore"))
            self.assertNotIn("MINORITY DISCOUNT", " ".join(aliases))

    def test_seed_is_idempotent(self) -> None:
        with self.SessionLocal() as session:
            first = ensure_industry_super_holdings_seed(session)
            second = ensure_industry_super_holdings_seed(session)
            session.commit()

            self.assertEqual(first.id, second.id)
            self.assertEqual(
                1,
                session.scalar(
                    select(func.count(Entity.id)).where(
                        Entity.canonical_name == INDUSTRY_SUPER_HOLDINGS_CANONICAL_NAME
                    )
                ),
            )
            self.assertEqual(
                len(INDUSTRY_SUPER_HOLDINGS_OBSERVED_ALIASES),
                session.scalar(
                    select(func.count(EntityAlias.id)).where(EntityAlias.entity_id == first.id)
                ),
            )

    def test_exact_name_resolution_links_safe_rows_and_leaves_discount_variant_unresolved(self) -> None:
        with self.SessionLocal() as session:
            linked_rows = session.execute(
                select(Holding.raw_name, func.count(Holding.id))
                .where(Holding.entity_id == self.entity_id)
                .group_by(Holding.raw_name)
                .order_by(Holding.raw_name.asc())
            ).all()

            self.assertEqual(
                [
                    ("Industry Super Holdings", 1),
                    ("Industry Super Holdings Pty Ltd", 2),
                    ("Industry Super Holdings Pty Ltd F/P", 2),
                ],
                linked_rows,
            )
            self.assertEqual(5, self.resolution_summary.exact_name_auto_links)

            unresolved_discount_count = session.scalar(
                select(func.count(Holding.id)).where(
                    Holding.raw_name == UNRESOLVED_UNISUPER_DISCOUNT_NAME,
                    Holding.entity_id.is_(None),
                )
            )
            self.assertEqual(1, unresolved_discount_count)

    def test_no_relationship_rows_are_created_and_no_cross_fund_total_is_computed(self) -> None:
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

            read_model = get_cross_adapter_holdings_by_entity_id(session, entity_id=self.entity_id)
            self.assertIsNotNone(read_model)
            self.assertEqual(self.entity_id, read_model.entity_id)
            self.assertEqual(5, read_model.observation_count)
            self.assertEqual(3, read_model.fund_count)
            self.assertFalse(hasattr(read_model, "total_ownership_pct"))
            self.assertEqual(
                {
                    ("art", "ART Balanced", Decimal("0.1432")),
                    ("art", "ART Stable", Decimal("0.18")),
                    ("hostplus", "HC High Growth - Class A Option", Decimal("0.1317")),
                    ("australiansuper", "Stable", Decimal("0.0018")),
                    ("australiansuper", "Stable", None),
                },
                {
                    (item.fund_code, item.option_name, item.ownership_pct)
                    for item in read_model.observations
                },
            )
