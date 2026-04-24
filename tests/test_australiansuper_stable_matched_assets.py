from __future__ import annotations

from datetime import date
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import func, select
from sqlalchemy.orm import sessionmaker

from app.db.models import Base, Entity, Holding, HoldingRelationship, ReportingPeriod
from app.db.session import get_engine
from app.entity_resolution.australiansuper_stable_matched_assets import (
    AUSTRALIANSUPER_STABLE_MATCHED_ASSET_RELATIONSHIP_ROLE,
    AUSTRALIANSUPER_STABLE_MATCHED_ASSET_SOURCE,
    AUSTRALIANSUPER_STABLE_MATCHED_ASSET_TARGET_ROW_NUMBERS,
    ensure_australiansuper_stable_matched_asset_proof,
)
from app.ingest.loader import ingest_australiansuper_local_file


AUSTRALIANSUPER_STABLE_FIXTURE_PATH = Path("tests/fixtures/real/australiansuper/Stable PHD (1).csv").resolve()


class TestAustralianSuperStableMatchedAssetProof(unittest.TestCase):
    @classmethod
    def setUpClass(cls) -> None:
        cls.tempdir = tempfile.TemporaryDirectory()
        cls.database_url = f"sqlite:///{Path(cls.tempdir.name) / 'australiansuper_stable_matched_assets.db'}"
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

            summary = ingest_australiansuper_local_file(
                session,
                fund_code="australiansuper",
                fund_name="AustralianSuper",
                file_path=str(AUSTRALIANSUPER_STABLE_FIXTURE_PATH),
                reporting_period_id=period.id,
            )
            cls.source_file_id = summary.source_file_id
            relationships = ensure_australiansuper_stable_matched_asset_proof(session)
            cls.relationship_ids = [relationship.id for relationship in relationships]
            session.commit()

    @classmethod
    def tearDownClass(cls) -> None:
        cls.engine.dispose()
        cls.tempdir.cleanup()

    def test_seed_creates_exactly_the_seven_target_asset_entities(self) -> None:
        with self.SessionLocal() as session:
            entities = session.scalars(
                select(Entity)
                .where(Entity.entity_type.in_(("property_asset", "infrastructure_asset")))
                .order_by(Entity.canonical_name.asc())
            ).all()

            self.assertEqual(
                [
                    "1200 W Carroll",
                    "1300 W Carroll",
                    "Ala Moana Shopping Centre",
                    "Kingswood",
                    "NSW Ports",
                    "Perth Airport",
                    "Wollert",
                ],
                [entity.canonical_name for entity in entities],
            )
            entity_types = {entity.canonical_name: entity.entity_type for entity in entities}
            self.assertEqual("property_asset", entity_types["1200 W Carroll"])
            self.assertEqual("property_asset", entity_types["Wollert"])
            self.assertEqual("infrastructure_asset", entity_types["NSW Ports"])
            self.assertEqual("infrastructure_asset", entity_types["Perth Airport"])
            self.assertTrue(all(entity.confidence_tier == "seeded" for entity in entities))

    def test_seed_creates_exactly_the_seven_target_holding_relationships(self) -> None:
        with self.SessionLocal() as session:
            rows = session.execute(
                select(
                    Holding.source_row_number,
                    Holding.raw_name,
                    HoldingRelationship.relationship_role,
                    HoldingRelationship.confidence_score,
                    HoldingRelationship.source,
                    Entity.entity_type,
                )
                .join(HoldingRelationship, HoldingRelationship.holding_id == Holding.id)
                .join(Entity, Entity.id == HoldingRelationship.related_entity_id)
                .where(
                    HoldingRelationship.relationship_role == AUSTRALIANSUPER_STABLE_MATCHED_ASSET_RELATIONSHIP_ROLE,
                    HoldingRelationship.source == AUSTRALIANSUPER_STABLE_MATCHED_ASSET_SOURCE,
                )
                .order_by(Holding.source_row_number.asc())
            ).all()

            self.assertEqual(list(AUSTRALIANSUPER_STABLE_MATCHED_ASSET_TARGET_ROW_NUMBERS), [row.source_row_number for row in rows])
            self.assertEqual(
                ["1200 W Carroll", "1300 W Carroll", "Ala Moana Shopping Centre", "Kingswood", "NSW Ports", "Perth Airport", "Wollert"],
                [row.raw_name for row in rows],
            )
            self.assertTrue(all(row.relationship_role == "property_asset_match" for row in rows))
            self.assertTrue(all(str(row.confidence_score) in {"1.0", "1.00000"} for row in rows))
            self.assertEqual(
                ["property_asset", "property_asset", "property_asset", "property_asset", "infrastructure_asset", "infrastructure_asset", "property_asset"],
                [row.entity_type for row in rows],
            )

    def test_seed_is_idempotent_and_does_not_match_non_target_rows(self) -> None:
        with self.SessionLocal() as session:
            ensure_australiansuper_stable_matched_asset_proof(session)
            session.commit()

            relationship_count = session.scalar(
                select(func.count(HoldingRelationship.id)).where(
                    HoldingRelationship.relationship_role == AUSTRALIANSUPER_STABLE_MATCHED_ASSET_RELATIONSHIP_ROLE,
                    HoldingRelationship.source == AUSTRALIANSUPER_STABLE_MATCHED_ASSET_SOURCE,
                )
            )
            entity_count = session.scalar(
                select(func.count(Entity.id)).where(Entity.entity_type.in_(("property_asset", "infrastructure_asset")))
            )
            non_target_relationship_count = session.scalar(
                select(func.count(HoldingRelationship.id))
                .join(Holding, Holding.id == HoldingRelationship.holding_id)
                .where(
                    HoldingRelationship.relationship_role == AUSTRALIANSUPER_STABLE_MATCHED_ASSET_RELATIONSHIP_ROLE,
                    HoldingRelationship.source == AUSTRALIANSUPER_STABLE_MATCHED_ASSET_SOURCE,
                    Holding.source_row_number.not_in(AUSTRALIANSUPER_STABLE_MATCHED_ASSET_TARGET_ROW_NUMBERS),
                )
            )

            self.assertEqual(7, relationship_count)
            self.assertEqual(7, entity_count)
            self.assertEqual(0, non_target_relationship_count)
