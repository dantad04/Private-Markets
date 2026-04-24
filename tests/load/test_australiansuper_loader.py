from __future__ import annotations

from datetime import date
from decimal import Decimal
from pathlib import Path
import tempfile
import unittest

from sqlalchemy import func, select
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
    AUSTRALIANSUPER_BALANCED_MAPPING_VERSION_ID,
    AUSTRALIANSUPER_CASH_MAPPING_VERSION_ID,
    AUSTRALIANSUPER_CONSERVATIVE_MAPPING_VERSION_ID,
    AUSTRALIANSUPER_DIVERSIFIED_FIXED_INTEREST_MAPPING_VERSION_ID,
    AUSTRALIANSUPER_HIGH_GROWTH_MAPPING_VERSION_ID,
    AUSTRALIANSUPER_INDEXED_DIVERSIFIED_MAPPING_VERSION_ID,
    AUSTRALIANSUPER_INTERNATIONAL_SHARES_MAPPING_VERSION_ID,
    AUSTRALIANSUPER_MAPPING_VERSION_ID,
    AUSTRALIANSUPER_SOCIALLY_AWARE_MAPPING_VERSION_ID,
    AUSTRALIANSUPER_STABLE_MAPPING_VERSION_ID,
)
from app.ingest.loader import ingest_australiansuper_local_file


FIXTURE_DIR = Path("tests/fixtures/real/australiansuper").resolve()
MEMBER_DIRECT_PATH = FIXTURE_DIR / "Member Direct PHD (1).csv"
STABLE_PATH = FIXTURE_DIR / "Stable PHD (1).csv"
CONSERVATIVE_PATH = FIXTURE_DIR / "Conservative PHD (1).csv"
BALANCED_PATH = FIXTURE_DIR / "Balanced PHD (6).csv"
HIGH_GROWTH_PATH = FIXTURE_DIR / "High Growth PHD (2).csv"
CASH_PATH = FIXTURE_DIR / "Cash PHD (1).csv"
DIVERSIFIED_FIXED_INTEREST_PATH = FIXTURE_DIR / "Diversified Fixed Interest PHD (1).csv"
INDEXED_DIVERSIFIED_PATH = FIXTURE_DIR / "Indexed Diversified PHD (1).csv"
INTERNATIONAL_SHARES_PATH = FIXTURE_DIR / "International Shares PHD.csv"
SOCIALLY_AWARE_PATH = FIXTURE_DIR / "Socially Aware PHD.csv"

SOURCE_URLS = {
    MEMBER_DIRECT_PATH: "https://www.australiansuper.com/-/media/australian-super/files/investments/phd/superannuation/member-direct-phd.csv",
    STABLE_PATH: "https://www.australiansuper.com/-/media/australian-super/files/investments/phd/superannuation/stable-phd.csv",
    CONSERVATIVE_PATH: "https://www.australiansuper.com/-/media/australian-super/files/investments/phd/superannuation/conservative-phd.csv",
    BALANCED_PATH: "https://www.australiansuper.com/-/media/australian-super/files/investments/phd/superannuation/balanced-phd.csv",
    HIGH_GROWTH_PATH: "https://www.australiansuper.com/-/media/australian-super/files/investments/phd/superannuation/high-growth-phd.csv",
    CASH_PATH: "https://www.australiansuper.com/-/media/australian-super/files/investments/phd/superannuation/cash-phd.csv",
    DIVERSIFIED_FIXED_INTEREST_PATH: "https://www.australiansuper.com/-/media/australian-super/files/investments/phd/superannuation/diversified-fixed-interest-phd.csv",
    INDEXED_DIVERSIFIED_PATH: "https://www.australiansuper.com/-/media/australian-super/files/investments/phd/superannuation/indexed-diversified-phd.csv",
    INTERNATIONAL_SHARES_PATH: "https://www.australiansuper.com/-/media/australian-super/files/investments/phd/superannuation/international-shares-phd.csv",
    SOCIALLY_AWARE_PATH: "https://www.australiansuper.com/-/media/australian-super/files/investments/phd/superannuation/socially-aware-phd.csv",
}

LATEST_PERIOD_BATCH_CASES = (
    (MEMBER_DIRECT_PATH, "Member Direct", AUSTRALIANSUPER_MAPPING_VERSION_ID, 564, 0, 0),
    (STABLE_PATH, "Stable", AUSTRALIANSUPER_STABLE_MAPPING_VERSION_ID, 4023, 17, 194),
    (CONSERVATIVE_PATH, "Conservative Balanced", AUSTRALIANSUPER_CONSERVATIVE_MAPPING_VERSION_ID, 4023, 17, 194),
    (BALANCED_PATH, "Balanced", AUSTRALIANSUPER_BALANCED_MAPPING_VERSION_ID, 3920, 17, 185),
    (HIGH_GROWTH_PATH, "High Growth", AUSTRALIANSUPER_HIGH_GROWTH_MAPPING_VERSION_ID, 3919, 17, 185),
)

LATEST_PERIOD_BATCH_2_CASES = (
    (CASH_PATH, "Cash", AUSTRALIANSUPER_CASH_MAPPING_VERSION_ID, 87, 11, 8),
    (
        DIVERSIFIED_FIXED_INTEREST_PATH,
        "Diversified Fixed Interest",
        AUSTRALIANSUPER_DIVERSIFIED_FIXED_INTEREST_MAPPING_VERSION_ID,
        1178,
        15,
        15,
    ),
    (INDEXED_DIVERSIFIED_PATH, "Index Diversified", AUSTRALIANSUPER_INDEXED_DIVERSIFIED_MAPPING_VERSION_ID, 2217, 16, 28),
    (
        INTERNATIONAL_SHARES_PATH,
        "International Shares",
        AUSTRALIANSUPER_INTERNATIONAL_SHARES_MAPPING_VERSION_ID,
        2164,
        16,
        14,
    ),
    (SOCIALLY_AWARE_PATH, "Socially Aware", AUSTRALIANSUPER_SOCIALLY_AWARE_MAPPING_VERSION_ID, 822, 15, 44),
)


class TestAustralianSuperLoader(unittest.TestCase):
    def setUp(self) -> None:
        self.tempdir = tempfile.TemporaryDirectory()
        self.database_url = f"sqlite:///{Path(self.tempdir.name) / 'stage2_australiansuper.db'}"
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

    def test_ingest_member_direct_official_file(self) -> None:
        reporting_period_id = self._create_reporting_period()

        with self.SessionLocal() as session:
            summary = ingest_australiansuper_local_file(
                session,
                fund_code="australiansuper",
                fund_name="AustralianSuper",
                file_path=str(MEMBER_DIRECT_PATH),
                reporting_period_id=reporting_period_id,
                source_url=SOURCE_URLS[MEMBER_DIRECT_PATH],
            )
            session.commit()

            self.assertEqual(564, summary.rows_staged)
            self.assertEqual(564, summary.rows_inserted)
            self.assertEqual(0, summary.rows_skipped_existing)

            source_file = session.get(SourceFile, summary.source_file_id)
            self.assertEqual("AustralianSuperPhdAdapter", source_file.adapter_key)
            self.assertEqual(SOURCE_URLS[MEMBER_DIRECT_PATH], source_file.source_url)
            self.assertEqual(AUSTRALIANSUPER_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(564, session.query(Holding).count())
            self.assertIsNotNone(session.get(AdapterMappingVersion, AUSTRALIANSUPER_MAPPING_VERSION_ID))
            self.assertGreater(session.query(TaxonomyMapping).count(), 0)
            self.assertEqual(0, session.query(SchemaReviewQueue).count())

            morella_row = session.scalar(
                select(Holding).where(
                    Holding.raw_name == "Morella Corporation Ltd",
                    Holding.source_file_id == summary.source_file_id,
                )
            )
            morella_asset_code = session.scalar(
                select(CanonicalAssetClass.code).where(CanonicalAssetClass.id == morella_row.canonical_asset_class_id)
            )
            self.assertEqual("listed_equity", morella_asset_code)
            self.assertEqual("BNSMZ47", morella_row.security_identifier_value)
            self.assertEqual("fully_disclosed", morella_row.disclosure_completeness)
            self.assertEqual(1, len(morella_row.raw_payload_json))
            self.assertEqual(2, morella_row.raw_payload_json[0]["source_row_number"])
            self.assertEqual(
                ["AR2O", "Member Direct", "Equity", "Listed"],
                morella_row.raw_payload_json[0]["payload"][:4],
            )
            self.assertEqual("Morella Corporation Ltd", morella_row.raw_payload_json[0]["payload"][5])
            self.assertEqual("BNSMZ47", morella_row.raw_payload_json[0]["payload"][9])
            self.assertEqual("27255.189", morella_row.raw_payload_json[0]["payload"][14])

            total_row = session.scalar(
                select(Holding).where(Holding.source_row_number == 551, Holding.source_file_id == summary.source_file_id)
            )
            self.assertTrue(total_row.is_aggregate)
            self.assertEqual("aggregate_total", total_row.disclosure_completeness)
            self.assertEqual(Decimal("2844353758"), total_row.value_aud)
            self.assertEqual("Listed Equity", total_row.source_asset_class_raw)
            self.assertEqual("Listed", total_row.source_subclass_raw)

    def test_ingest_stable_official_file_with_real_duplicate_view_merge(self) -> None:
        reporting_period_id = self._create_reporting_period()

        with self.SessionLocal() as session:
            summary = ingest_australiansuper_local_file(
                session,
                fund_code="australiansuper",
                fund_name="AustralianSuper",
                file_path=str(STABLE_PATH),
                reporting_period_id=reporting_period_id,
                source_url=SOURCE_URLS[STABLE_PATH],
            )
            session.commit()

            self.assertEqual(4023, summary.rows_staged)
            self.assertEqual(4023, summary.rows_inserted)
            self.assertEqual(0, summary.rows_skipped_existing)

            source_file = session.get(SourceFile, summary.source_file_id)
            self.assertEqual("loaded", source_file.ingest_status)
            self.assertEqual(SOURCE_URLS[STABLE_PATH], source_file.source_url)
            self.assertEqual(AUSTRALIANSUPER_STABLE_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(4023, session.query(Holding).count())
            self.assertIsNotNone(session.get(AdapterMappingVersion, AUSTRALIANSUPER_STABLE_MAPPING_VERSION_ID))
            self.assertEqual(194, session.query(SchemaReviewQueue).count())

            ifm_row = session.scalar(
                select(Holding).where(Holding.source_row_number == 3420, Holding.source_file_id == summary.source_file_id)
            )
            self.assertEqual("IFM Investors", ifm_row.raw_name)
            self.assertEqual("$100m to $300m", ifm_row.value_band_raw)
            self.assertEqual([3999], ifm_row.metadata_attached_from_row_numbers)
            self.assertEqual([3420, 3999], [entry["source_row_number"] for entry in ifm_row.raw_payload_json])

            ausgrid_row = session.scalar(
                select(Holding).where(Holding.source_row_number == 3386, Holding.source_file_id == summary.source_file_id)
            )
            self.assertEqual("ownership_only", ausgrid_row.disclosure_completeness)
            self.assertEqual("Electricity", ausgrid_row.classification_raw)
            self.assertEqual([3988], ausgrid_row.metadata_attached_from_row_numbers)

            self.assertEqual(0, session.query(Holding).filter(Holding.source_asset_class_raw == "Derivatives").count())

            first_review_item = session.query(SchemaReviewQueue).order_by(SchemaReviewQueue.id.asc()).first()
            self.assertEqual("ambiguous_duplicate_group", first_review_item.review_reason)

    def test_ingest_conservative_official_file_uses_the_same_approved_shape_as_stable(self) -> None:
        reporting_period_id = self._create_reporting_period()

        with self.SessionLocal() as session:
            summary = ingest_australiansuper_local_file(
                session,
                fund_code="australiansuper",
                fund_name="AustralianSuper",
                file_path=str(CONSERVATIVE_PATH),
                reporting_period_id=reporting_period_id,
                source_url=SOURCE_URLS[CONSERVATIVE_PATH],
            )
            session.commit()

            self.assertEqual(4023, summary.rows_staged)
            self.assertEqual(4023, summary.rows_inserted)
            self.assertEqual(0, summary.rows_skipped_existing)

            source_file = session.get(SourceFile, summary.source_file_id)
            self.assertEqual("loaded", source_file.ingest_status)
            self.assertEqual(SOURCE_URLS[CONSERVATIVE_PATH], source_file.source_url)
            self.assertEqual(AUSTRALIANSUPER_CONSERVATIVE_MAPPING_VERSION_ID, source_file.mapping_version_id)
            self.assertEqual(4023, session.query(Holding).count())
            self.assertIsNotNone(session.get(AdapterMappingVersion, AUSTRALIANSUPER_CONSERVATIVE_MAPPING_VERSION_ID))
            self.assertEqual(194, session.query(SchemaReviewQueue).count())

            merged_row = session.scalar(
                select(Holding).where(Holding.source_row_number == 3368, Holding.source_file_id == summary.source_file_id)
            )
            self.assertEqual("1200 W Carroll", merged_row.raw_name)
            self.assertEqual("Office", merged_row.classification_raw)
            self.assertEqual("< $2m", merged_row.value_band_raw)
            self.assertEqual([3877], merged_row.metadata_attached_from_row_numbers)
            self.assertEqual([3368, 3877], [entry["source_row_number"] for entry in merged_row.raw_payload_json])

            self.assertEqual(0, session.query(Holding).filter(Holding.source_asset_class_raw == "Derivatives").count())

    def test_ingest_first_five_file_latest_period_batch(self) -> None:
        reporting_period_id = self._create_reporting_period()

        with self.SessionLocal() as session:
            source_file_ids: list[int] = []
            for file_path, _option_name, mapping_version_id, expected_rows, _skipped_rows, _review_count in (
                LATEST_PERIOD_BATCH_CASES
            ):
                summary = ingest_australiansuper_local_file(
                    session,
                    fund_code="australiansuper",
                    fund_name="AustralianSuper",
                    file_path=str(file_path),
                    reporting_period_id=reporting_period_id,
                    source_url=SOURCE_URLS[file_path],
                )

                self.assertEqual(expected_rows, summary.rows_staged)
                self.assertEqual(expected_rows, summary.rows_inserted)
                source_file = session.get(SourceFile, summary.source_file_id)
                self.assertEqual("AustralianSuperPhdAdapter", source_file.adapter_key)
                self.assertEqual(mapping_version_id, source_file.mapping_version_id)
                self.assertEqual(SOURCE_URLS[file_path], source_file.source_url)
                source_file_ids.append(summary.source_file_id)

            session.flush()

            holdings_by_option = dict(
                session.execute(
                    select(InvestmentOption.source_option_name, func.count(Holding.id))
                    .join(Holding, Holding.source_option_id == InvestmentOption.id)
                    .where(Holding.source_file_id.in_(source_file_ids))
                    .group_by(InvestmentOption.source_option_name)
                ).all()
            )
            self.assertEqual(
                {
                    option_name: expected_rows
                    for _file_path, option_name, _mapping_version_id, expected_rows, _skipped_rows, _review_count in (
                        LATEST_PERIOD_BATCH_CASES
                    )
                },
                holdings_by_option,
            )
            self.assertEqual(
                0,
                session.query(Holding)
                .filter(Holding.source_file_id.in_(source_file_ids), Holding.source_asset_class_raw == "Derivatives")
                .count(),
            )
            self.assertEqual(
                sum(review_count for *_prefix, review_count in LATEST_PERIOD_BATCH_CASES),
                session.query(SchemaReviewQueue).count(),
            )
            source_filenames = {Path(source_file.source_url).name for source_file in session.query(SourceFile).all()}
            self.assertFalse(
                {
                    "cash-phd.csv",
                    "diversified-fixed-interest-phd.csv",
                    "indexed-diversified-phd.csv",
                    "international-shares-phd.csv",
                    "socially-aware-phd.csv",
                    "australian-shares-phd.csv",
                }
                & source_filenames
            )

    def test_ingest_second_five_file_latest_period_batch(self) -> None:
        reporting_period_id = self._create_reporting_period()

        with self.SessionLocal() as session:
            source_file_ids: list[int] = []
            for file_path, _option_name, mapping_version_id, expected_rows, _skipped_rows, _review_count in (
                LATEST_PERIOD_BATCH_2_CASES
            ):
                summary = ingest_australiansuper_local_file(
                    session,
                    fund_code="australiansuper",
                    fund_name="AustralianSuper",
                    file_path=str(file_path),
                    reporting_period_id=reporting_period_id,
                    source_url=SOURCE_URLS[file_path],
                )

                self.assertEqual(expected_rows, summary.rows_staged)
                self.assertEqual(expected_rows, summary.rows_inserted)
                source_file = session.get(SourceFile, summary.source_file_id)
                self.assertEqual("AustralianSuperPhdAdapter", source_file.adapter_key)
                self.assertEqual(mapping_version_id, source_file.mapping_version_id)
                self.assertEqual(SOURCE_URLS[file_path], source_file.source_url)
                source_file_ids.append(summary.source_file_id)

            session.flush()

            holdings_by_option = dict(
                session.execute(
                    select(InvestmentOption.source_option_name, func.count(Holding.id))
                    .join(Holding, Holding.source_option_id == InvestmentOption.id)
                    .where(Holding.source_file_id.in_(source_file_ids))
                    .group_by(InvestmentOption.source_option_name)
                ).all()
            )
            self.assertEqual(
                {
                    option_name: expected_rows
                    for _file_path, option_name, _mapping_version_id, expected_rows, _skipped_rows, _review_count in (
                        LATEST_PERIOD_BATCH_2_CASES
                    )
                },
                holdings_by_option,
            )
            self.assertEqual(
                0,
                session.query(Holding)
                .filter(Holding.source_file_id.in_(source_file_ids), Holding.source_asset_class_raw == "Derivatives")
                .count(),
            )
            self.assertEqual(
                sum(review_count for *_prefix, review_count in LATEST_PERIOD_BATCH_2_CASES),
                session.query(SchemaReviewQueue).count(),
            )
            source_urls = {source_file.source_url.lower() for source_file in session.query(SourceFile).all()}
            self.assertFalse(any("australian-shares" in source_url for source_url in source_urls))
            self.assertFalse(any("retirement" in source_url for source_url in source_urls))
