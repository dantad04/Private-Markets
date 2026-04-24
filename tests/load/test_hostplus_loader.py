from __future__ import annotations

from collections import Counter
from datetime import date
from pathlib import Path
import csv
import io
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
from app.ingest.governance import HOSTPLUS_MAPPING_VERSION_ID, SchemaDriftDetectedError
from app.ingest.governance import (
    HOSTPLUS_AUSTRALIAN_SHARES_INDEXED_MAPPING_VERSION_ID,
    HOSTPLUS_AUSTRALIAN_SHARES_MAPPING_VERSION_ID,
    HOSTPLUS_CASH_MAPPING_VERSION_ID,
    HOSTPLUS_INDEXED_HIGH_GROWTH_MAPPING_VERSION_ID,
    HOSTPLUS_INTERNATIONAL_SHARES_MAPPING_VERSION_ID,
    HOSTPLUS_SRI_HIGH_GROWTH_MAPPING_VERSION_ID,
)
from app.ingest.loader import ingest_hostplus_local_file


FIXTURE_PATH = Path("tests/fixtures/hostplus_real_extract.csv").resolve()
HOSTPLUS_FIXTURE_DIR = Path("tests/fixtures/real/hostplus").resolve()
AUSTRALIAN_SHARES_PATH = HOSTPLUS_FIXTURE_DIR / "australian-shares.csv"
AUSTRALIAN_SHARES_INDEXED_PATH = HOSTPLUS_FIXTURE_DIR / "australian-shares-indexed.csv"
CASH_PATH = HOSTPLUS_FIXTURE_DIR / "cash.csv"
INDEXED_HIGH_GROWTH_PATH = HOSTPLUS_FIXTURE_DIR / "indexed-high-growth.csv"
INTERNATIONAL_SHARES_PATH = HOSTPLUS_FIXTURE_DIR / "international-shares.csv"
SRI_HIGH_GROWTH_PATH = HOSTPLUS_FIXTURE_DIR / "sri-high-growth.csv"

SOURCE_URLS = {
    AUSTRALIAN_SHARES_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Australian%20Shares.csv",
    AUSTRALIAN_SHARES_INDEXED_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Australian%20Shares%20-%20Indexed.csv",
    CASH_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Cash.csv",
    INDEXED_HIGH_GROWTH_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Indexed%20High%20Growth.csv",
    INTERNATIONAL_SHARES_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/International%20Shares.csv",
    SRI_HIGH_GROWTH_PATH: "https://hostplus.com.au/content/dam/hostplus-program/site/resources/investments/investment-holdings/accumulation-investment-holdings/Socially%20Responsible%20Investment%20(SRI)%20-%20High%20Growth.csv",
}

LATEST_PERIOD_BATCH_CASES = (
    (
        AUSTRALIAN_SHARES_PATH,
        "HC Australian Shares - Class A Option",
        HOSTPLUS_AUSTRALIAN_SHARES_MAPPING_VERSION_ID,
        343,
        Counter({"value_only": 339, "aggregate_total": 4}),
    ),
    (
        AUSTRALIAN_SHARES_INDEXED_PATH,
        "HC Australian Shares - Indexed - Class A Option",
        HOSTPLUS_AUSTRALIAN_SHARES_INDEXED_MAPPING_VERSION_ID,
        215,
        Counter({"value_only": 212, "aggregate_total": 3}),
    ),
    (
        CASH_PATH,
        "HC Cash - Class A Option",
        HOSTPLUS_CASH_MAPPING_VERSION_ID,
        5,
        Counter({"value_only": 3, "aggregate_total": 2}),
    ),
    (
        INDEXED_HIGH_GROWTH_PATH,
        "HC Indexed High Growth - Class A Option",
        HOSTPLUS_INDEXED_HIGH_GROWTH_MAPPING_VERSION_ID,
        2531,
        Counter({"value_only": 2525, "aggregate_total": 4, "name_only": 2}),
    ),
    (
        INTERNATIONAL_SHARES_PATH,
        "HC International Shares - Class A Option",
        HOSTPLUS_INTERNATIONAL_SHARES_MAPPING_VERSION_ID,
        2856,
        Counter({"value_only": 2823, "name_only": 29, "aggregate_total": 4}),
    ),
    (
        SRI_HIGH_GROWTH_PATH,
        "HC SRI High Growth - Class A Option",
        HOSTPLUS_SRI_HIGH_GROWTH_MAPPING_VERSION_ID,
        565,
        Counter({"value_only": 560, "aggregate_total": 4, "name_only": 1}),
    ),
)


def mutate_fixture(mutator, output_path: Path) -> Path:
    with FIXTURE_PATH.open("r", encoding="utf-8", errors="replace", newline="") as handle:
        rows = list(csv.reader(handle))
    mutator(rows)
    output = io.StringIO()
    writer = csv.writer(output, lineterminator="\n")
    writer.writerows(rows)
    output_path.write_text(output.getvalue(), encoding="utf-8")
    return output_path


class TestHostPlusLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_hostplus.db'}"
        self.engine = get_engine(self.database_url)
        Base.metadata.create_all(self.engine)
        self.SessionLocal = sessionmaker(bind=self.engine, autoflush=False, autocommit=False, future=True)

    def tearDown(self) -> None:
        self.engine.dispose()
        self.tempdir.cleanup()

    def _create_reporting_period(self) -> int:
        with self.SessionLocal() as session:
            period = ReportingPeriod(
                period_end_date=date(2025, 12, 31),
                disclosure_due_date=date(2026, 3, 31),
                label="2025-12-31",
                source_cycle="semi_annual",
            )
            session.add(period)
            session.commit()
            return period.id

    def test_ingest_hostplus_local_file_loads_single_option_source_file(self) -> None:
        reporting_period_id = self._create_reporting_period()

        with self.SessionLocal() as session:
            summary = ingest_hostplus_local_file(
                session,
                fund_code="hostplus",
                fund_name="Hostplus",
                file_path=str(FIXTURE_PATH),
                reporting_period_id=reporting_period_id,
            )
            session.commit()

            self.assertEqual(3215, summary.rows_staged)
            self.assertEqual(3215, summary.rows_inserted)
            self.assertEqual(0, summary.rows_skipped_existing)
            self.assertIsNotNone(summary.investment_option_id)
            self.assertEqual(
                ["Decoded Host-Plus source using UTF-8 errors='replace'; replacement_count=3"],
                summary.warnings,
            )

            source_file = session.get(SourceFile, summary.source_file_id)
            self.assertEqual("HostPlusPhdStateMachineAdapter", source_file.adapter_key)
            self.assertEqual(HOSTPLUS_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(summary.investment_option_id, source_file.investment_option_id)
            self.assertEqual(3215, session.query(Holding).count())
            self.assertEqual(1, session.query(InvestmentOption).count())
            self.assertIsNotNone(session.get(AdapterMappingVersion, HOSTPLUS_MAPPING_VERSION_ID))
            self.assertGreater(session.query(TaxonomyMapping).count(), 0)
            self.assertEqual(0, session.query(SchemaReviewQueue).count())

            industry_super_holdings = session.scalar(
                select(Holding).where(
                    Holding.raw_name == "Industry Super Holdings",
                    Holding.source_row_number == 3184,
                )
            )
            self.assertEqual(0.1317, float(industry_super_holdings.ownership_pct))
            self.assertIsNone(industry_super_holdings.value_aud)
            self.assertEqual("ownership_only", industry_super_holdings.disclosure_completeness)

            ifm_row = session.scalar(
                select(Holding).where(
                    Holding.raw_name == "IFM Investors Pty Ltd",
                    Holding.source_row_number == 3209,
                )
            )
            self.assertEqual(4642022, float(ifm_row.value_aud))
            self.assertEqual("value_only", ifm_row.disclosure_completeness)

    def test_ingest_latest_period_mapping_only_batch_files(self) -> None:
        reporting_period_id = self._create_reporting_period()

        with self.SessionLocal() as session:
            source_file_ids: list[int] = []
            for file_path, option_name, mapping_version_id, expected_rows, expected_completeness in (
                LATEST_PERIOD_BATCH_CASES
            ):
                summary = ingest_hostplus_local_file(
                    session,
                    fund_code="hostplus",
                    fund_name="Hostplus",
                    file_path=str(file_path),
                    reporting_period_id=reporting_period_id,
                    source_url=SOURCE_URLS[file_path],
                )

                self.assertEqual(expected_rows, summary.rows_staged)
                self.assertEqual(expected_rows, summary.rows_inserted)
                self.assertEqual(
                    ["Decoded Host-Plus source using UTF-8 errors='replace'; replacement_count=3"],
                    summary.warnings,
                )
                source_file = session.get(SourceFile, summary.source_file_id)
                self.assertEqual("HostPlusPhdStateMachineAdapter", source_file.adapter_key)
                self.assertEqual(mapping_version_id, source_file.mapping_version_id)
                self.assertEqual(SOURCE_URLS[file_path], source_file.source_url)
                self.assertEqual(3, source_file.encoding_replacement_count)
                option = session.get(InvestmentOption, summary.investment_option_id)
                self.assertEqual(option_name, option.source_option_name)
                period = session.get(ReportingPeriod, summary.reporting_period_id)
                self.assertEqual(date(2025, 12, 31), period.period_end_date)
                source_file_ids.append(summary.source_file_id)

                option_counts = Counter(
                    row[0]
                    for row in session.execute(
                        select(Holding.disclosure_completeness).where(
                            Holding.source_file_id == summary.source_file_id
                        )
                    ).all()
                )
                self.assertEqual(expected_completeness, option_counts)

            session.commit()

            self.assertEqual(sum(case[3] for case in LATEST_PERIOD_BATCH_CASES), session.query(Holding).count())
            self.assertEqual(0, session.query(SchemaReviewQueue).count())
            self.assertEqual(
                0,
                session.query(Holding)
                .filter(
                    Holding.source_file_id.in_(source_file_ids),
                    Holding.source_asset_class_raw.in_(
                        ["Fixed Income", "Unlisted Property", "Unlisted Infrastructure"]
                    ),
                )
                .count(),
            )
            self.assertFalse(
                session.query(Holding)
                .filter(
                    Holding.source_file_id.in_(source_file_ids),
                    Holding.raw_name.in_(["Forwards", "Futures", "Swaps", "AUD"]),
                )
                .first()
            )

            source_urls = {source_file.source_url for source_file in session.query(SourceFile).all()}
            self.assertEqual({SOURCE_URLS[file_path] for file_path, *_rest in LATEST_PERIOD_BATCH_CASES}, source_urls)
            self.assertFalse(any(source_url.endswith("/High%20Growth.csv") for source_url in source_urls))
            self.assertFalse(any("Defined%20Benefit" in source_url for source_url in source_urls))
            self.assertFalse(any("retirement" in source_url.casefold() or "pension" in source_url.casefold() for source_url in source_urls))

    def test_unknown_scope_variant_queues_review_but_file_still_loads(self) -> None:
        reporting_period_id = self._create_reporting_period()
        mutated_path = mutate_fixture(
            lambda rows: rows.__setitem__(3179, ["Held directly or by associated entities or by Trusts", "", "", "", ""]),
            Path(self.tempdir.name) / "hostplus_unknown_scope.csv",
        )

        with self.SessionLocal() as session:
            summary = ingest_hostplus_local_file(
                session,
                fund_code="hostplus",
                fund_name="Hostplus",
                file_path=str(mutated_path),
                reporting_period_id=reporting_period_id,
            )
            session.commit()

            self.assertEqual(3215, summary.rows_inserted)
            self.assertIn("unapproved scope modifier", " ".join(summary.warnings))
            self.assertEqual("loaded", session.get(SourceFile, summary.source_file_id).ingest_status)
            self.assertEqual(1, session.query(SchemaReviewQueue).count())
            review_item = session.query(SchemaReviewQueue).one()
            self.assertEqual("unapproved_scope_modifier", review_item.review_reason)

    def test_header_drift_blocks_ingest_and_queues_schema_review(self) -> None:
        reporting_period_id = self._create_reporting_period()
        mutated_path = mutate_fixture(
            lambda rows: rows.__setitem__(6, ["Name of Institution", "Currency", "", "Value (AUD)", "Weighting (BPS)"]),
            Path(self.tempdir.name) / "hostplus_header_drift.csv",
        )

        with self.SessionLocal() as session:
            with self.assertRaises(SchemaDriftDetectedError) as ctx:
                ingest_hostplus_local_file(
                    session,
                    fund_code="hostplus",
                    fund_name="Hostplus",
                    file_path=str(mutated_path),
                    reporting_period_id=reporting_period_id,
                )
            session.commit()

            self.assertIn("drift detected", str(ctx.exception))
            self.assertEqual(1, session.query(SchemaReviewQueue).count())
            review_item = session.query(SchemaReviewQueue).one()
            self.assertEqual("schema_drift", review_item.review_reason)
