from __future__ import annotations

from datetime import date, datetime
from decimal import Decimal
from pathlib import Path
import unittest

from adapters.australian_retirement_trust_real_16col import (
    AustralianRetirementTrustReal16ColumnPhdAdapter,
)
from adapters.australian_retirement_trust_real_16col_mapping import (
    ADAPTER_KEY,
    APPROVED_SCHEMA_FINGERPRINT,
)
from adapters.base import SourceFileMetadata


FIXTURE_PATH = Path("tests/fixtures/australian_retirement_trust_real_16col_minimal.csv")


def make_contract_metadata() -> SourceFileMetadata:
    return SourceFileMetadata(
        source_file_id="contract-fixture-art-real-16col",
        fund_id="art",
        suspected_adapter_key=ADAPTER_KEY,
        reporting_period_id=None,
        source_url=(
            "https://files.australianretirementtrust.com.au/phd/super/diversified/"
            "Diversified_High_Growth_Superannuation.csv?v="
        ),
        checksum="contract-fixture-art-real-16col-sha256-placeholder",
        received_at=datetime(2026, 4, 25, 0, 0, 0),
        fund_code="art",
    )


def _decimal_string(value: Decimal | None) -> str | None:
    if value is None:
        return None
    return format(value, "f").rstrip("0").rstrip(".") if "." in format(value, "f") else format(value, "f")


def _date_string(value: date) -> str:
    return value.isoformat()


class TestAustralianRetirementTrustReal16ColumnContract(unittest.TestCase):
    maxDiff = None

    def test_minimal_fixture_contract(self) -> None:
        result = AustralianRetirementTrustReal16ColumnPhdAdapter().parse(
            make_contract_metadata(),
            FIXTURE_PATH.read_bytes(),
        )

        actual = {
            "schema_fingerprint": result.schema_fingerprint,
            "adapter_warnings": result.adapter_warnings,
            "structural_metadata_subset": {
                "observed_options": result.structural_metadata["observed_options"],
                "observed_option_names": result.structural_metadata["observed_option_names"],
                "observed_reporting_dates": result.structural_metadata["observed_reporting_dates"],
                "skipped_portfolio_posture_rows": result.structural_metadata["skipped_portfolio_posture_rows"],
                "skipped_portfolio_posture_rows_by_type": result.structural_metadata[
                    "skipped_portfolio_posture_rows_by_type"
                ],
                "total_rows_aggregate": result.structural_metadata["total_rows_aggregate"],
                "total_rows_emitted": result.structural_metadata["total_rows_emitted"],
            },
            "disclosure_completeness_counts": result.parse_statistics["disclosure_completeness_counts"],
            "canonical_asset_class_counts": result.parse_statistics["canonical_asset_class_counts"],
            "holdings_projection": [
                {
                    "row": record.source_row_number,
                    "date": _date_string(record.reporting_period_date),
                    "option_code": record.source_option_code,
                    "option_name": record.source_option_name_raw,
                    "type": record.source_asset_class_raw,
                    "canonical": record.canonical_asset_class_code,
                    "aggregate": record.is_aggregate,
                    "name": record.raw_name,
                    "value": _decimal_string(record.value_aud),
                    "ownership": _decimal_string(record.ownership_pct),
                    "units": _decimal_string(record.units),
                    "weighting": _decimal_string(record.weighting_pct),
                    "currency": record.currency_raw,
                    "identifier": record.security_identifier_value,
                    "completeness": record.disclosure_completeness,
                }
                for record in result.holdings
            ],
        }

        self.assertEqual(
            {
                "schema_fingerprint": APPROVED_SCHEMA_FINGERPRINT,
                "adapter_warnings": [],
                "structural_metadata_subset": {
                    "observed_options": ["Diversified_High_Growth_Superannuation"],
                    "observed_option_names": ["Diversified High Growth Superannuation"],
                    "observed_reporting_dates": ["31 December 2025"],
                    "skipped_portfolio_posture_rows": 17,
                    "skipped_portfolio_posture_rows_by_type": {
                        "Derivatives By AssetClass": 7,
                        "Derivatives By Currency": 4,
                        "Derivatives By Kind": 6,
                    },
                    "total_rows_aggregate": 14,
                    "total_rows_emitted": 27,
                },
                "disclosure_completeness_counts": {
                    "aggregate_total": 14,
                    "fully_disclosed": 3,
                    "name_only": 1,
                    "ownership_only": 2,
                    "value_only": 7,
                },
                "canonical_asset_class_counts": {
                    "alternatives": 2,
                    "cash": 2,
                    "fixed_income": 4,
                    "listed_equity": 2,
                    "listed_infrastructure": 2,
                    "listed_property": 2,
                    "multi_asset_other": 2,
                    "unlisted_equity": 5,
                    "unlisted_infrastructure": 4,
                    "unlisted_property": 2,
                },
                "holdings_projection": [
                    {"row": 2, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Cash", "canonical": "cash", "aggregate": False, "name": "COMMONWEALTH BANK OF AUSTRALIA", "value": "107144524", "ownership": None, "units": None, "weighting": "0.0127", "currency": "AUD", "identifier": None, "completeness": "value_only"},
                    {"row": 3, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Cash", "canonical": "cash", "aggregate": True, "name": None, "value": "120460561", "ownership": None, "units": None, "weighting": "0.0143", "currency": None, "identifier": None, "completeness": "aggregate_total"},
                    {"row": 4, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Fixed Income Externally Managed", "canonical": "fixed_income", "aggregate": False, "name": "STATE STREET INVESTMENT MANAGEMENT", "value": "-99270", "ownership": None, "units": None, "weighting": "-0.0001", "currency": None, "identifier": None, "completeness": "value_only"},
                    {"row": 5, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Fixed Income Externally Managed", "canonical": "fixed_income", "aggregate": True, "name": None, "value": "1261704603", "ownership": None, "units": None, "weighting": "0.9849", "currency": None, "identifier": None, "completeness": "aggregate_total"},
                    {"row": 6, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Fixed Income Internally Managed", "canonical": "fixed_income", "aggregate": False, "name": "BANK OF CHINA LTD.", "value": "542645265", "ownership": None, "units": None, "weighting": "0.0883", "currency": None, "identifier": None, "completeness": "value_only"},
                    {"row": 7, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Fixed Income Internally Managed", "canonical": "fixed_income", "aggregate": True, "name": None, "value": "1429467395", "ownership": None, "units": None, "weighting": "0.2327", "currency": None, "identifier": None, "completeness": "aggregate_total"},
                    {"row": 8, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Listed Equity", "canonical": "listed_equity", "aggregate": False, "name": "COMMONWEALTH BANK OF AUSTRALIA", "value": "817467971", "ownership": None, "units": "5091038", "weighting": "0.0968", "currency": None, "identifier": "CBA AU", "completeness": "fully_disclosed"},
                    {"row": 9, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Listed Equity", "canonical": "listed_equity", "aggregate": True, "name": None, "value": "7553206437", "ownership": None, "units": None, "weighting": "0.8943", "currency": None, "identifier": None, "completeness": "aggregate_total"},
                    {"row": 10, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Unlisted Equity Externally Managed", "canonical": "unlisted_equity", "aggregate": False, "name": "PARTNERS GROUP AG", "value": "71857811", "ownership": None, "units": None, "weighting": "0.1109", "currency": None, "identifier": None, "completeness": "value_only"},
                    {"row": 11, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Unlisted Equity Externally Managed", "canonical": "unlisted_equity", "aggregate": True, "name": None, "value": "190432391", "ownership": None, "units": None, "weighting": "0.294", "currency": None, "identifier": None, "completeness": "aggregate_total"},
                    {"row": 12, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Unlisted Equity Internally Managed", "canonical": "unlisted_equity", "aggregate": False, "name": "LENDI GROUP", "value": None, "ownership": "0", "units": None, "weighting": None, "currency": None, "identifier": None, "completeness": "ownership_only"},
                    {"row": 13, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Unlisted Equity Internally Managed", "canonical": "unlisted_equity", "aggregate": False, "name": "FUTURE VEHICLE", "value": None, "ownership": None, "units": None, "weighting": None, "currency": None, "identifier": None, "completeness": "name_only"},
                    {"row": 14, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Unlisted Equity Internally Managed", "canonical": "unlisted_equity", "aggregate": True, "name": None, "value": "142608", "ownership": None, "units": None, "weighting": "0", "currency": None, "identifier": None, "completeness": "aggregate_total"},
                    {"row": 15, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Listed Property", "canonical": "listed_property", "aggregate": False, "name": "GOODMAN GROUP", "value": "12345", "ownership": None, "units": "1000", "weighting": "0.0001", "currency": None, "identifier": "GMG AU", "completeness": "fully_disclosed"},
                    {"row": 16, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Listed Property", "canonical": "listed_property", "aggregate": True, "name": None, "value": "567130090", "ownership": None, "units": None, "weighting": "0.0671", "currency": None, "identifier": None, "completeness": "aggregate_total"},
                    {"row": 17, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Unlisted Property Externally Managed", "canonical": "unlisted_property", "aggregate": False, "name": "MIRVAC FUNDS MANAGEMENT LTD", "value": "15238805", "ownership": None, "units": None, "weighting": "0.0235", "currency": None, "identifier": None, "completeness": "value_only"},
                    {"row": 18, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Unlisted Property Externally Managed", "canonical": "unlisted_property", "aggregate": True, "name": None, "value": "129885202", "ownership": None, "units": None, "weighting": "0.2005", "currency": None, "identifier": None, "completeness": "aggregate_total"},
                    {"row": 19, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Listed Infrastructure", "canonical": "listed_infrastructure", "aggregate": False, "name": "TRANSURBAN GROUP", "value": "136053038", "ownership": None, "units": "9574457", "weighting": "0.0161", "currency": None, "identifier": "TCL AU", "completeness": "fully_disclosed"},
                    {"row": 20, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Listed Infrastructure", "canonical": "listed_infrastructure", "aggregate": True, "name": None, "value": "204255377", "ownership": None, "units": None, "weighting": "0.0242", "currency": None, "identifier": None, "completeness": "aggregate_total"},
                    {"row": 21, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Unlisted Infrastructure Internally Managed", "canonical": "unlisted_infrastructure", "aggregate": False, "name": "PERTH AIRPORT", "value": None, "ownership": "0.07", "units": None, "weighting": None, "currency": None, "identifier": None, "completeness": "ownership_only"},
                    {"row": 22, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Unlisted Infrastructure Internally Managed", "canonical": "unlisted_infrastructure", "aggregate": True, "name": None, "value": "315819520", "ownership": None, "units": None, "weighting": "0.0255", "currency": None, "identifier": None, "completeness": "aggregate_total"},
                    {"row": 23, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Unlisted Infrastructure Externally Managed", "canonical": "unlisted_infrastructure", "aggregate": False, "name": "QIC LIMITED", "value": "41666014", "ownership": None, "units": None, "weighting": "0.0643", "currency": None, "identifier": None, "completeness": "value_only"},
                    {"row": 24, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Unlisted Infrastructure Externally Managed", "canonical": "unlisted_infrastructure", "aggregate": True, "name": None, "value": "175488001", "ownership": None, "units": None, "weighting": "0.2708", "currency": None, "identifier": None, "completeness": "aggregate_total"},
                    {"row": 25, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Unlisted Alternatives Externally Managed", "canonical": "alternatives", "aggregate": False, "name": "BAIN CAPITAL", "value": "10832705", "ownership": None, "units": None, "weighting": "0.0167", "currency": None, "identifier": None, "completeness": "value_only"},
                    {"row": 26, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "Unlisted Alternatives Externally Managed", "canonical": "alternatives", "aggregate": True, "name": None, "value": "30225025", "ownership": None, "units": None, "weighting": "0.0466", "currency": None, "identifier": None, "completeness": "aggregate_total"},
                    {"row": 27, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "AssetTotal", "canonical": "multi_asset_other", "aggregate": True, "name": None, "value": "8445052465", "ownership": None, "units": None, "weighting": "0.9999", "currency": None, "identifier": None, "completeness": "aggregate_total"},
                    {"row": 45, "date": "2025-12-31", "option_code": None, "option_name": "Diversified High Growth Superannuation", "type": "OptionTotal", "canonical": "multi_asset_other", "aggregate": True, "name": None, "value": "8445978090", "ownership": None, "units": None, "weighting": "1", "currency": None, "identifier": None, "completeness": "aggregate_total"},
                ],
            },
            actual,
        )
