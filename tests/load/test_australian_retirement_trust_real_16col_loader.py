from __future__ import annotations

from datetime import date
from decimal import Decimal
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
    SourceFile,
    TaxonomyMapping,
)
from app.db.session import get_engine
from app.ingest.governance import AUSTRALIAN_RETIREMENT_TRUST_REAL_16COL_MAPPING_VERSION_ID
from app.ingest.loader import ingest_australian_retirement_trust_real_16col_local_file


FIXTURE_PATH = Path("tests/fixtures/australian_retirement_trust_real_16col_minimal.csv").resolve()
OFFICIAL_SOURCE_URL = (
    "https://files.australianretirementtrust.com.au/phd/super/diversified/"
    "Diversified_High_Growth_Superannuation.csv?v="
)


class TestAustralianRetirementTrustReal16ColumnLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_art_real_16col.db'}"
        self.engine = get_engine(self.database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tempdir.cleanup()

    def test_ingest_art_real_16col_fixture_persists_mapping_and_option_key(self) -> None:
        with self.SessionLocal() as session:
            first = ingest_australian_retirement_trust_real_16col_local_file(
                session,
                fund_code="art",
                fund_name="Australian Retirement Trust",
                file_path=str(FIXTURE_PATH),
                source_url=OFFICIAL_SOURCE_URL,
            )
            session.commit()

            self.assertEqual(27, first.rows_staged)
            self.assertEqual(27, first.rows_inserted)
            self.assertEqual(0, first.rows_skipped_existing)
            self.assertEqual(
                "b08a08c11dbab46a70545220c2217fce074b23bfc2d135f8e035aab136e3bd6b",
                first.schema_fingerprint,
            )

            source_file = session.get(SourceFile, first.source_file_id)
            self.assertEqual("australian_retirement_trust_real_16col", source_file.adapter_key)
            self.assertEqual(AUSTRALIAN_RETIREMENT_TRUST_REAL_16COL_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(OFFICIAL_SOURCE_URL, source_file.source_url)

            period = session.get(ReportingPeriod, first.reporting_period_id)
            self.assertEqual(date(2025, 12, 31), period.period_end_date)

            option = session.get(InvestmentOption, first.investment_option_id)
            # ART real 16-column files have no source option-code column. This
            # persisted key is raw OptionName, used because the DB option key is
            # non-null, and must not be interpreted as a true source code.
            self.assertEqual("Diversified_High_Growth_Superannuation", option.source_option_code)
            self.assertEqual("Diversified High Growth Superannuation", option.source_option_name)
            self.assertEqual("Diversified High Growth Superannuation", option.canonical_option_name)

            self.assertIsNotNone(
                session.get(AdapterMappingVersion, AUSTRALIAN_RETIREMENT_TRUST_REAL_16COL_MAPPING_VERSION_ID)
            )
            self.assertEqual(26, session.query(TaxonomyMapping).count())
            self.assertEqual(27, session.query(Holding).count())
            self.assertEqual(14, session.query(Holding).filter(Holding.is_aggregate.is_(True)).count())
            self.assertEqual(
                0,
                session.query(Holding)
                .filter(Holding.raw_name.in_(["SWAPS", "AUD", "EQUITIES"]))
                .count(),
            )

            zero_ownership = session.scalar(
                select(Holding).where(
                    Holding.raw_name == "LENDI GROUP",
                    Holding.source_file_id == first.source_file_id,
                )
            )
            self.assertEqual(Decimal("0E-9"), zero_ownership.ownership_pct)

        with self.SessionLocal() as session:
            second = ingest_australian_retirement_trust_real_16col_local_file(
                session,
                fund_code="art",
                fund_name="Australian Retirement Trust",
                file_path=str(FIXTURE_PATH),
                source_url=OFFICIAL_SOURCE_URL,
            )
            session.commit()

            self.assertEqual(27, second.rows_staged)
            self.assertEqual(0, second.rows_inserted)
            self.assertEqual(27, second.rows_skipped_existing)
            self.assertEqual(27, session.query(Holding).count())
