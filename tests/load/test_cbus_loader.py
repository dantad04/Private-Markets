from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import select
from sqlalchemy.orm import sessionmaker

from app.db.models import (
    AdapterMappingVersion,
    Base,
    Holding,
    InvestmentOption,
    ReportingPeriod,
    SchemaReviewQueue,
    SourceFile,
    TaxonomyMapping,
)
from app.db.session import get_engine
from app.ingest.governance import CBUS_MAPPING_VERSION_ID
from app.ingest.loader import ingest_cbus_local_file


FIXTURE_PATH = Path("tests/fixtures/real/cbus/super-high-growth__1_.csv").resolve()


class TestCbusLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_cbus.db'}"
        self.engine = get_engine(self.database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_ingest_cbus_real_file_loads_idempotently_and_backfills_period(self) -> None:
        with self.SessionLocal() as session:
            first = ingest_cbus_local_file(
                session,
                fund_code="cbus",
                fund_name="Cbus",
                file_path=str(FIXTURE_PATH),
            )
            session.commit()

            self.assertEqual(2249, first.rows_staged)
            self.assertEqual(2249, first.rows_inserted)
            self.assertEqual(0, first.rows_skipped_existing)
            self.assertEqual([], first.warnings)

            source_file = session.get(SourceFile, first.source_file_id)
            self.assertEqual("CbusPhdAdapter", source_file.adapter_key)
            self.assertEqual(CBUS_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(0, source_file.encoding_replacement_count)
            self.assertEqual(first.investment_option_id, source_file.investment_option_id)

            period = session.get(ReportingPeriod, first.reporting_period_id)
            self.assertEqual(date(2025, 12, 31), period.period_end_date)
            option = session.get(InvestmentOption, first.investment_option_id)
            self.assertEqual("CBUS_HIGH_GROWTH_ACCUMULATION_OPTION", option.source_option_code)
            self.assertEqual("High Growth Accumulation Option", option.source_option_name)

            self.assertEqual(2249, session.query(Holding).count())
            self.assertIsNotNone(session.get(AdapterMappingVersion, CBUS_MAPPING_VERSION_ID))
            taxonomy_rows = session.scalars(
                select(TaxonomyMapping).where(TaxonomyMapping.mapping_version == CBUS_MAPPING_VERSION_ID)
            ).all()
            self.assertEqual(30, len(taxonomy_rows))
            taxonomy_lookup = {
                (row.source_asset_class_raw, row.source_filter_raw, row.is_aggregate_default): row
                for row in taxonomy_rows
            }
            self.assertEqual(
                "unlisted_property",
                taxonomy_lookup[("Unlisted property internal", "internal", False)].canonical_asset_class_code,
            )
            self.assertEqual(
                "aggregate_total",
                taxonomy_lookup[("Table 1 TOTAL", None, True)].disclosure_completeness_default,
            )
            self.assertEqual(0, session.query(SchemaReviewQueue).count())

            counts = Counter(
                row[0]
                for row in session.execute(select(Holding.disclosure_completeness)).all()
            )
            self.assertEqual(
                Counter(
                    {
                        "fully_disclosed": 2068,
                        "value_only": 122,
                        "ownership_only": 36,
                        "aggregate_total": 15,
                        "name_only": 8,
                    }
                ),
                counts,
            )

            property_address_rows = session.scalars(
                select(Holding).where(
                    Holding.source_asset_class_raw == "Unlisted property internal",
                    Holding.is_aggregate.is_(False),
                    Holding.address.is_not(None),
                )
            ).all()
            self.assertEqual(29, len(property_address_rows))

            cbus_prop_r3 = session.scalar(
                select(Holding).where(
                    Holding.raw_name == "CBUS Prop R3 Pty Ltd North Sydney",
                    Holding.source_row_number == 2195,
                )
            )
            self.assertEqual("ownership_only", cbus_prop_r3.disclosure_completeness)
            self.assertEqual(
                "East Walker St, North Sydney. 173-179 Walker St and 11-17 Hampden St, North Sydney",
                cbus_prop_r3.address,
            )

            private_debt = session.scalar(
                select(Holding).where(
                    Holding.raw_name == "ANCORA BIDCO PTY LTD",
                    Holding.source_row_number == 75,
                )
            )
            self.assertEqual("name_only", private_debt.disclosure_completeness)

        with self.SessionLocal() as session:
            second = ingest_cbus_local_file(
                session,
                fund_code="cbus",
                fund_name="Cbus",
                file_path=str(FIXTURE_PATH),
            )
            session.commit()

            self.assertEqual(2249, second.rows_staged)
            self.assertEqual(0, second.rows_inserted)
            self.assertEqual(2249, second.rows_skipped_existing)
            self.assertEqual(2249, session.query(Holding).count())


if __name__ == "__main__":
    unittest.main()
