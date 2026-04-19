from __future__ import annotations

from pathlib import Path
import tempfile
import unittest

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import AdapterMappingVersion, Base, Holding, SchemaReviewQueue, SourceFile, TaxonomyMapping
from app.db.session import get_engine
from app.ingest.governance import ART_QSUPER_MAPPING_VERSION_ID, SchemaDriftDetectedError
from app.ingest.loader import ingest_art_qsuper_local_file


FIXTURE_PATH = Path("tests/fixtures/art_qsuper_synthetic_balanced_minimal.csv").resolve()


class TestArtQsuperLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_art_qsuper.db'}"
        self.engine = get_engine(self.database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_ingest_art_qsuper_local_file_loads_idempotently_and_persists_mapping_version(self) -> None:
        with self.SessionLocal() as session:
            first = ingest_art_qsuper_local_file(
                session,
                fund_code="art",
                fund_name="ART",
                file_path=str(FIXTURE_PATH),
            )
            session.commit()
            self.assertEqual(8, first.rows_staged)
            self.assertEqual(8, first.rows_inserted)
            self.assertEqual(0, first.rows_skipped_existing)

            source_file = session.get(SourceFile, first.source_file_id)
            self.assertEqual("ArtQsuperPhdAdapter", source_file.adapter_key)
            self.assertEqual(ART_QSUPER_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(8, session.query(Holding).count())
            self.assertIsNotNone(session.get(AdapterMappingVersion, ART_QSUPER_MAPPING_VERSION_ID))
            self.assertGreater(session.query(TaxonomyMapping).count(), 0)
            self.assertEqual(2, session.query(Holding).filter(Holding.is_aggregate.is_(True)).count())
            self.assertEqual(
                0,
                session.query(Holding)
                .filter(Holding.raw_name.in_(["Equity Futures", "Listed Equity", "USD"]))
                .count(),
            )

        with self.SessionLocal() as session:
            second = ingest_art_qsuper_local_file(
                session,
                fund_code="art",
                fund_name="ART",
                file_path=str(FIXTURE_PATH),
            )
            session.commit()
            self.assertEqual(8, second.rows_staged)
            self.assertEqual(0, second.rows_inserted)
            self.assertEqual(8, second.rows_skipped_existing)
            self.assertEqual(8, session.query(Holding).count())

    def test_schema_drift_blocks_ingest_and_queues_review_item(self) -> None:
        drifted_path = Path(self.tempdir.name) / "art_qsuper_drifted.csv"
        drifted_text = FIXTURE_PATH.read_text(encoding="utf-8").replace(
            "Externally Managed,ART CORE BOND FUND",
            "External Mandate,ART CORE BOND FUND",
            1,
        )
        drifted_path.write_text(drifted_text, encoding="utf-8")

        with self.SessionLocal() as session:
            with self.assertRaises(SchemaDriftDetectedError):
                ingest_art_qsuper_local_file(
                    session,
                    fund_code="art",
                    fund_name="ART",
                    file_path=str(drifted_path),
                )

            review_item = session.query(SchemaReviewQueue).one()
            self.assertEqual("schema_drift", review_item.review_reason)
            self.assertEqual("ArtQsuperPhdAdapter", review_item.adapter_key)
            self.assertIn("observed_internal_external_values", review_item.drift_summary_json)

            source_file = session.get(SourceFile, review_item.source_file_id)
            self.assertEqual("review_required", source_file.ingest_status)
            self.assertEqual(ART_QSUPER_MAPPING_VERSION_ID, source_file.mapping_version_id)

    def test_ingest_art_qsuper_persists_encoding_replacement_count(self) -> None:
        broken_bytes = FIXTURE_PATH.read_bytes().replace(b"Blackbird Ventures Growth I", b"Blackbird Ventur\xC0s Growth I", 1)
        broken_path = Path(self.tempdir.name) / "art_qsuper_replacement.csv"
        broken_path.write_bytes(broken_bytes)

        with self.SessionLocal() as session:
            summary = ingest_art_qsuper_local_file(
                session,
                fund_code="art",
                fund_name="ART",
                file_path=str(broken_path),
            )
            session.commit()
            source_file = session.get(SourceFile, summary.source_file_id)
            self.assertEqual(1, source_file.encoding_replacement_count)
            row = session.scalar(
                select(Holding).where(Holding.source_row_number == 7, Holding.source_file_id == summary.source_file_id)
            )
            self.assertIn("\ufffd", row.raw_name)
