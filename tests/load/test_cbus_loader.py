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
    CanonicalAssetClass,
    Holding,
    InvestmentOption,
    ReportingPeriod,
    SchemaReviewQueue,
    SourceFile,
    TaxonomyMapping,
)
from app.db.session import get_engine
from app.ingest.governance import (
    CBUS_AUSTRALIAN_SHARES_MAPPING_VERSION_ID,
    CBUS_CASH_MAPPING_VERSION_ID,
    CBUS_MAPPING_VERSION_ID,
    CBUS_OVERSEAS_SHARES_MAPPING_VERSION_ID,
    CBUS_PROPERTY_MAPPING_VERSION_ID,
)
from app.ingest.loader import ingest_cbus_local_file


FIXTURE_PATH = Path("tests/fixtures/real/cbus/super-high-growth__1_.csv").resolve()
PROPERTY_PATH = Path("tests/fixtures/real/cbus/super-property__1_.csv").resolve()
OVERSEAS_SHARES_PATH = Path("tests/fixtures/real/cbus/super-overseas-shares.csv").resolve()
AUSTRALIAN_SHARES_PATH = Path("tests/fixtures/real/cbus/super-australian-shares__1_.csv").resolve()
CASH_PATH = Path("tests/fixtures/real/cbus/super-cash.csv").resolve()

SOURCE_URLS = {
    PROPERTY_PATH: "https://www.cbussuper.com.au/content/dam/cbus/files/governance/investment-holdings/super-property.csv",
    OVERSEAS_SHARES_PATH: "https://www.cbussuper.com.au/content/dam/cbus/files/governance/investment-holdings/super-overseas-shares.csv",
    AUSTRALIAN_SHARES_PATH: "https://www.cbussuper.com.au/content/dam/cbus/files/governance/investment-holdings/super-australian-shares.csv",
    CASH_PATH: "https://www.cbussuper.com.au/content/dam/cbus/files/governance/investment-holdings/super-cash.csv",
}

BATCH_1_CASES = (
    (PROPERTY_PATH, "Property Accumulation Option", CBUS_PROPERTY_MAPPING_VERSION_ID, 106, 13, 58, 16),
    (OVERSEAS_SHARES_PATH, "Overseas Shares Accumulation Option", CBUS_OVERSEAS_SHARES_MAPPING_VERSION_ID, 1421, 14, 14, 0),
    (
        AUSTRALIAN_SHARES_PATH,
        "Australian Shares Accumulation Option",
        CBUS_AUSTRALIAN_SHARES_MAPPING_VERSION_ID,
        353,
        14,
        36,
        0,
    ),
    (CASH_PATH, "Cash Accumulation Option", CBUS_CASH_MAPPING_VERSION_ID, 16, 3, 0, 0),
)


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

    def test_ingest_cbus_latest_period_batch_1_files(self) -> None:
        with self.SessionLocal() as session:
            source_file_ids: list[int] = []
            for (
                file_path,
                option_name,
                mapping_version_id,
                expected_rows,
                _expected_skips,
                _expected_property_infrastructure_rows,
                _expected_address_backed_property_infrastructure_rows,
            ) in BATCH_1_CASES:
                summary = ingest_cbus_local_file(
                    session,
                    fund_code="cbus",
                    fund_name="Cbus",
                    file_path=str(file_path),
                    source_url=SOURCE_URLS[file_path],
                )

                self.assertEqual(expected_rows, summary.rows_staged)
                self.assertEqual(expected_rows, summary.rows_inserted)
                source_file = session.get(SourceFile, summary.source_file_id)
                self.assertEqual("CbusPhdAdapter", source_file.adapter_key)
                self.assertEqual(mapping_version_id, source_file.mapping_version_id)
                self.assertEqual(SOURCE_URLS[file_path], source_file.source_url)
                option = session.get(InvestmentOption, summary.investment_option_id)
                self.assertEqual(option_name, option.source_option_name)
                period = session.get(ReportingPeriod, summary.reporting_period_id)
                self.assertEqual(date(2025, 12, 31), period.period_end_date)
                source_file_ids.append(summary.source_file_id)

            session.commit()

            self.assertEqual(sum(case[3] for case in BATCH_1_CASES), session.query(Holding).count())
            self.assertEqual(0, session.query(SchemaReviewQueue).count())
            self.assertEqual(
                0,
                session.query(Holding)
                .filter(Holding.source_file_id.in_(source_file_ids), Holding.source_asset_class_raw == "Derivatives")
                .count(),
            )
            self.assertFalse(
                session.query(Holding)
                .filter(
                    Holding.source_file_id.in_(source_file_ids),
                    Holding.raw_name.in_(["Futures", "FX Forwards", "Derivatives TOTAL", "AUD"]),
                )
                .first()
            )

            for (
                _file_path,
                option_name,
                _mapping_version_id,
                expected_rows,
                _expected_skips,
                expected_property_infrastructure_rows,
                expected_address_backed_property_infrastructure_rows,
            ) in BATCH_1_CASES:
                option = session.scalar(
                    select(InvestmentOption).where(InvestmentOption.source_option_name == option_name)
                )
                option_holdings = session.scalars(select(Holding).where(Holding.source_option_id == option.id)).all()
                self.assertEqual(expected_rows, len(option_holdings))
                property_infrastructure_rows = [
                    holding
                    for holding in option_holdings
                    if session.get(CanonicalAssetClass, holding.canonical_asset_class_id).code
                    in {
                        "listed_property",
                        "unlisted_property",
                        "listed_infrastructure",
                        "unlisted_infrastructure",
                    }
                    and not holding.is_aggregate
                ]
                self.assertEqual(expected_property_infrastructure_rows, len(property_infrastructure_rows))
                self.assertEqual(
                    expected_address_backed_property_infrastructure_rows,
                    len([holding for holding in property_infrastructure_rows if holding.address]),
                )

            source_urls = {source_file.source_url.lower() for source_file in session.query(SourceFile).all()}
            self.assertFalse(any("super-high-growth" in source_url for source_url in source_urls))
            self.assertFalse(any("super-conservative" in source_url for source_url in source_urls))
            self.assertFalse(any("super-growth" in source_url for source_url in source_urls))
            self.assertFalse(any("super-diversified-fixed-interest" in source_url for source_url in source_urls))
            self.assertFalse(any("super-indexed-diversified" in source_url for source_url in source_urls))
            self.assertFalse(any("retirement" in source_url or "pension" in source_url for source_url in source_urls))


if __name__ == "__main__":
    unittest.main()
