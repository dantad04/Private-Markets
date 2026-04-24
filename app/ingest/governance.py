from __future__ import annotations

import csv
from dataclasses import dataclass, replace
from datetime import UTC, datetime
import io

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.base import AdapterParseResult
from adapters.art_qsuper_mapping import EXPECTED_HEADER as ART_QSUPER_EXPECTED_HEADER
from adapters.aware_mapping import EXPECTED_TABLE_1_HEADER
from adapters.cbus_mapping import (
    EXPECTED_HEADER as CBUS_EXPECTED_HEADER,
    SECTION_MAPPINGS as CBUS_SECTION_MAPPINGS,
    TOTAL_SECTION_MAPPINGS as CBUS_TOTAL_SECTION_MAPPINGS,
)
from adapters.sunsuper_schema_identity import AUSTRALIANSUPER_REAL_HEADER
from adapters.sunsuper_schema_mapping import EXPECTED_HEADER as SUNSUPER_SCHEMA_EXPECTED_HEADER
from app.db.models import AdapterMappingVersion, SchemaReviewQueue, SourceFile, TaxonomyMapping


AWARE_MAPPING_VERSION_ID = "aware-stage2-v1"
ART_QSUPER_MAPPING_VERSION_ID = "art-qsuper-stage2-v1"
ART_SUNSUPER_MAPPING_VERSION_ID = "art-sunsuper-stage2-v1"
AUSTRALIANSUPER_MEMBER_DIRECT_MAPPING_VERSION_ID = "australiansuper-stage2-v1"
AUSTRALIANSUPER_MAPPING_VERSION_ID = AUSTRALIANSUPER_MEMBER_DIRECT_MAPPING_VERSION_ID
AUSTRALIANSUPER_STABLE_MAPPING_VERSION_ID = "australiansuper-stage2-stable-v1"
AUSTRALIANSUPER_CONSERVATIVE_MAPPING_VERSION_ID = "australiansuper-stage2-conservative-v1"
UNISUPER_MAPPING_VERSION_ID = "unisuper-stage2-v1"
HOSTPLUS_MAPPING_VERSION_ID = "hostplus-stage2-v1"
CBUS_MAPPING_VERSION_ID = "cbus-stage2-late-v1"


class GovernanceError(Exception):
    """Base error for approved-mapping and schema-governance checks."""


class MissingApprovedMappingError(GovernanceError):
    pass


class SchemaDriftDetectedError(GovernanceError):
    pass


class UnapprovedTaxonomyMappingError(GovernanceError):
    pass


@dataclass(frozen=True)
class ApprovedTaxonomyMappingSeed:
    source_asset_class_raw: str
    source_filter_raw: str | None
    source_sub_filter_raw: str | None
    source_section_raw: str | None
    canonical_asset_class_code: str
    is_aggregate_default: bool
    disclosure_completeness_default: str | None
    notes: str | None


@dataclass(frozen=True)
class ApprovedAdapterMappingSeed:
    id: str
    adapter_key: str
    schema_fingerprint: str
    structural_expectations_json: dict[str, object]
    notes: str
    approved_by: str
    approved_at: datetime
    taxonomy_rows: tuple[ApprovedTaxonomyMappingSeed, ...]


def _retarget_taxonomy_notes(
    taxonomy_rows: tuple[ApprovedTaxonomyMappingSeed, ...],
    *,
    from_label: str,
    to_label: str,
) -> tuple[ApprovedTaxonomyMappingSeed, ...]:
    return tuple(
        replace(row, notes=row.notes.replace(from_label, to_label) if row.notes else None)
        for row in taxonomy_rows
    )


AWARE_APPROVED_MAPPING = ApprovedAdapterMappingSeed(
    id=AWARE_MAPPING_VERSION_ID,
    adapter_key="AwarePhdAdapter",
    schema_fingerprint="0221ce01b8fb64d5b1ef06efaf5b70d8ffaf35cb2e0e163c5c0f4a54b4523139",
    structural_expectations_json={
        "observed_headers": EXPECTED_TABLE_1_HEADER,
        "observed_section_labels": [
            "ASSETS",
            "DERIVATIVES",
            "DERIVATIVES BY ASSET CLASS",
            "DERIVATIVES BY CURRENCY",
        ],
        "observed_tables": [1, 2, 3, 4],
        "observed_internal_external_values": ["EXTERNALLY", "INTERNALLY"],
        "observed_asset_classes": [
            "CASH",
            "FIXED INCOME",
            "FIXED INCOME (PRIVATE DEBT)",
            "LISTED EQUITY",
            "TOTAL INVESTMENT ITEMS",
            "UNLISTED EQUITY",
            "UNLISTED PROPERTY",
        ],
    },
    notes="Approved Stage 2 Aware synthetic vertical-slice mapping.",
    approved_by="repo-seed",
    approved_at=datetime(2026, 4, 19, tzinfo=UTC),
    taxonomy_rows=(
        ApprovedTaxonomyMappingSeed("CASH", None, None, "ASSETS", "cash", False, None, "Table 1 direct holding"),
        ApprovedTaxonomyMappingSeed(
            "FIXED INCOME", "INTERNALLY", None, "ASSETS", "fixed_income", False, None, "Table 1 direct holding"
        ),
        ApprovedTaxonomyMappingSeed(
            "FIXED INCOME", "EXTERNALLY", None, "ASSETS", "fixed_income", False, None, "Table 1 manager rollup"
        ),
        ApprovedTaxonomyMappingSeed(
            "FIXED INCOME (PRIVATE DEBT)",
            "INTERNALLY",
            None,
            "ASSETS",
            "private_debt",
            False,
            None,
            "Table 1 direct holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "LISTED EQUITY", None, None, "ASSETS", "listed_equity", False, None, "Table 1 direct holding"
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED EQUITY", "INTERNALLY", None, "ASSETS", "unlisted_equity", False, None, "Table 1 direct holding"
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED EQUITY", "EXTERNALLY", None, "ASSETS", "unlisted_equity", False, None, "Table 1 manager rollup"
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED PROPERTY",
            "INTERNALLY",
            None,
            "ASSETS",
            "unlisted_property",
            False,
            None,
            "Table 1 direct holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED PROPERTY",
            "EXTERNALLY",
            None,
            "ASSETS",
            "unlisted_property",
            False,
            None,
            "Table 1 manager rollup",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL CASH",
            None,
            None,
            "ASSETS",
            "cash",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL FIXED INCOME INTERNALLY",
            "INTERNALLY",
            None,
            "ASSETS",
            "fixed_income",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL FIXED INCOME (PRIVATE DEBT) INTERNALLY",
            "INTERNALLY",
            None,
            "ASSETS",
            "private_debt",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL FIXED INCOME EXTERNALLY",
            "EXTERNALLY",
            None,
            "ASSETS",
            "fixed_income",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL LISTED EQUITY",
            None,
            None,
            "ASSETS",
            "listed_equity",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL UNLISTED EQUITY INTERNALLY",
            "INTERNALLY",
            None,
            "ASSETS",
            "unlisted_equity",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL UNLISTED EQUITY EXTERNALLY",
            "EXTERNALLY",
            None,
            "ASSETS",
            "unlisted_equity",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL UNLISTED PROPERTY INTERNALLY",
            "INTERNALLY",
            None,
            "ASSETS",
            "unlisted_property",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "SUB TOTAL UNLISTED PROPERTY EXTERNALLY",
            "EXTERNALLY",
            None,
            "ASSETS",
            "unlisted_property",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "TOTAL INVESTMENT ITEMS",
            None,
            None,
            "ASSETS",
            "multi_asset_other",
            True,
            "aggregate_total",
            "Whole-file aggregate total",
        ),
    ),
)


ART_QSUPER_APPROVED_MAPPING = ApprovedAdapterMappingSeed(
    id=ART_QSUPER_MAPPING_VERSION_ID,
    adapter_key="ArtQsuperPhdAdapter",
    schema_fingerprint="42b9680ea59e47dd5753d4859fac412aefce8d91a2e6f50bfebe93e0717d4e79",
    structural_expectations_json={
        "observed_headers": ART_QSUPER_EXPECTED_HEADER,
        "observed_internal_external_values": ["Externally Managed", "Internally Managed"],
        "observed_asset_classes": [
            "Cash",
            "Cash Total",
            "Derivatives By AssetClass",
            "Derivatives By Currency",
            "Derivatives By Kind",
            "Fixed Income",
            "Listed Infrastructure",
            "Total Investment Items",
            "Unlisted Equity",
            "Unlisted Property",
        ],
    },
    notes="Approved Stage 2 ART-QSuper synthetic vertical-slice mapping.",
    approved_by="repo-seed",
    approved_at=datetime(2026, 4, 19, tzinfo=UTC),
    taxonomy_rows=(
        ApprovedTaxonomyMappingSeed("Cash", None, None, None, "cash", False, None, "Direct cash row"),
        ApprovedTaxonomyMappingSeed(
            "Fixed Income",
            "Externally Managed",
            None,
            None,
            "fixed_income",
            False,
            None,
            "Externally managed bond exposure",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Infrastructure",
            None,
            None,
            None,
            "listed_infrastructure",
            False,
            None,
            "Direct listed infrastructure row",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Equity",
            "Internally Managed",
            None,
            None,
            "unlisted_equity",
            False,
            None,
            "Internally managed private equity exposure",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Equity",
            "Externally Managed",
            None,
            None,
            "unlisted_equity",
            False,
            None,
            "Externally managed private equity manager or vehicle row",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Property",
            "Internally Managed",
            None,
            None,
            "unlisted_property",
            False,
            None,
            "Internally managed private property exposure",
        ),
        ApprovedTaxonomyMappingSeed(
            "Cash Total",
            None,
            None,
            None,
            "cash",
            True,
            "aggregate_total",
            "Aggregate subtotal row",
        ),
        ApprovedTaxonomyMappingSeed(
            "Total Investment Items",
            None,
            None,
            None,
            "multi_asset_other",
            True,
            "aggregate_total",
            "Whole-file aggregate total",
        ),
    ),
)


ART_SUNSUPER_APPROVED_MAPPING = ApprovedAdapterMappingSeed(
    id=ART_SUNSUPER_MAPPING_VERSION_ID,
    adapter_key="ArtSunsuperPhdAdapter",
    schema_fingerprint="212487dd7cc3263a5b3aa79f763c6f4f82a4a1b393751fb5cd7dbfc77e930ace",
    structural_expectations_json={
        "observed_headers": SUNSUPER_SCHEMA_EXPECTED_HEADER,
        "observed_asset_classes": [
            "Fixed Income",
            "Listed Equity",
            "Listed Infrastructure",
            "Private Equity",
        ],
        "observed_filters": [
            "All Assets",
            "Derivatives",
            "Externally Managed",
            "Private Equity",
        ],
        "observed_name_types": [
            "Asset",
            "Corporate",
            "Exposure",
            "Fund Vehicle",
            "Manager",
        ],
    },
    notes="Approved Stage 2 narrow ART-Sunsuper synthetic slice using the shared Sunsuper schema.",
    approved_by="repo-seed",
    approved_at=datetime(2026, 4, 19, tzinfo=UTC),
    taxonomy_rows=(
        ApprovedTaxonomyMappingSeed(
            "Fixed Income",
            "Externally Managed",
            None,
            None,
            "fixed_income",
            False,
            None,
            "Manager-style value-bearing row",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Infrastructure",
            "All Assets",
            None,
            None,
            "listed_infrastructure",
            False,
            None,
            "Direct all-assets row",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Infrastructure",
            "Externally Managed",
            None,
            None,
            "listed_infrastructure",
            False,
            None,
            "Manager-style listed infrastructure row used for ambiguity review coverage",
        ),
        ApprovedTaxonomyMappingSeed(
            "Private Equity",
            "All Assets",
            None,
            None,
            "unlisted_equity",
            False,
            None,
            "Ownership-only row on all-assets view",
        ),
        ApprovedTaxonomyMappingSeed(
            "Private Equity",
            "Private Equity",
            None,
            None,
            "unlisted_equity",
            False,
            "name_only",
            "Private-equity vehicle row",
        ),
    ),
)


AUSTRALIANSUPER_APPROVED_MAPPING = ApprovedAdapterMappingSeed(
    id=AUSTRALIANSUPER_MEMBER_DIRECT_MAPPING_VERSION_ID,
    adapter_key="AustralianSuperPhdAdapter",
    schema_fingerprint="c481c669d86f58bb9f7ed95eceb6a814872a91747b96b7aa17253cb7c324e2d6",
    structural_expectations_json={
        "observed_headers": AUSTRALIANSUPER_REAL_HEADER,
        "observed_asset_classes": [
            "Cash",
            "Fixed Income",
            "Listed Alternatives",
            "Listed Equity",
            "Listed Infrastructure",
            "Listed Property",
        ],
        "observed_filters": [
            "All Assets",
            "Internally Managed",
            "Listed",
        ],
        "observed_name_types": [
            "Name",
            "Name of Institution",
            "Name of Issuer/Counterparty",
            "Total",
        ],
        "observed_option_codes": ["AR2O"],
        "observed_option_names": ["Member Direct"],
    },
    notes=(
        "Approved Stage 2 AustralianSuper narrow slice using the real Member Direct file and a thin "
        "fund-specific adapter. Broader AustralianSuper option shapes remain pending additional mapping approval."
    ),
    approved_by="repo-seed",
    approved_at=datetime(2026, 4, 19, tzinfo=UTC),
    taxonomy_rows=(
        ApprovedTaxonomyMappingSeed(
            "Listed Equity",
            "Listed",
            None,
            None,
            "listed_equity",
            False,
            None,
            "Official AustralianSuper Member Direct listed-equity holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Property",
            "Listed",
            None,
            None,
            "listed_property",
            False,
            None,
            "Official AustralianSuper Member Direct listed-property holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Alternatives",
            "Listed",
            None,
            None,
            "alternatives",
            False,
            None,
            "Official AustralianSuper Member Direct listed-alternatives holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Infrastructure",
            "Listed",
            None,
            None,
            "listed_infrastructure",
            False,
            None,
            "Official AustralianSuper Member Direct listed-infrastructure holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "Fixed Income",
            "All Assets",
            None,
            None,
            "fixed_income",
            False,
            None,
            "Official AustralianSuper Member Direct fixed-income issuer holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "Fixed Income",
            "Internally Managed",
            None,
            None,
            "fixed_income",
            False,
            None,
            "Official AustralianSuper Member Direct internally managed fixed-income slice",
        ),
        ApprovedTaxonomyMappingSeed(
            "Cash",
            "All Assets",
            None,
            None,
            "cash",
            False,
            None,
            "Official AustralianSuper Member Direct cash holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Alternatives",
            "Listed",
            None,
            None,
            "alternatives",
            True,
            "aggregate_total",
            "Official AustralianSuper Member Direct listed-alternatives total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Cash",
            "All Assets",
            None,
            None,
            "cash",
            True,
            "aggregate_total",
            "Official AustralianSuper Member Direct cash total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Equity",
            "Listed",
            None,
            None,
            "listed_equity",
            True,
            "aggregate_total",
            "Official AustralianSuper Member Direct listed-equity total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Fixed Income",
            "All Assets",
            None,
            None,
            "fixed_income",
            True,
            "aggregate_total",
            "Official AustralianSuper Member Direct fixed-income total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Infrastructure",
            "Listed",
            None,
            None,
            "listed_infrastructure",
            True,
            "aggregate_total",
            "Official AustralianSuper Member Direct listed-infrastructure total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Property",
            "Listed",
            None,
            None,
            "listed_property",
            True,
            "aggregate_total",
            "Official AustralianSuper Member Direct listed-property total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Fixed Income",
            "Internally Managed",
            None,
            None,
            "fixed_income",
            True,
            "aggregate_total",
            "Official AustralianSuper Member Direct internally managed fixed-income total",
        ),
    ),
)


AUSTRALIANSUPER_STABLE_APPROVED_MAPPING = ApprovedAdapterMappingSeed(
    id=AUSTRALIANSUPER_STABLE_MAPPING_VERSION_ID,
    adapter_key="AustralianSuperPhdAdapter",
    schema_fingerprint="9155b44a6c15c0e694f43fef3402dc4840c3937803c8606f27318c5699afb413",
    structural_expectations_json={
        "observed_headers": AUSTRALIANSUPER_REAL_HEADER,
        "observed_asset_classes": [
            "Cash",
            "Fixed Income",
            "Listed Alternatives",
            "Listed Equity",
            "Listed Infrastructure",
            "Listed Property",
            "Private Debt",
            "Private Equity",
            "Unlisted Alternatives",
            "Unlisted Equity",
            "Unlisted Infrastructure",
            "Unlisted Property",
        ],
        "observed_filters": [
            "All Assets",
            "Externally Managed",
            "Fixed Income Private Debt",
            "Internally Managed",
            "Listed",
            "Private Equity",
        ],
        "observed_name_types": [
            "Asset Class",
            "Currency Exposure",
            "Kind of Derivatives",
            "Name",
            "Name of Fund Manager",
            "Name of Institution",
            "Name of Issuer/Counterparty",
            "Total",
        ],
        "observed_option_codes": ["ARST"],
        "observed_option_names": ["Stable"],
    },
    notes=(
        "Approved Stage 2 AustralianSuper Stable slice using the real Stable file and the thin "
        "fund-specific adapter. Member Direct and Conservative Balanced are approved; Socially "
        "Aware remains gated pending its own mapping approval."
    ),
    approved_by="repo-seed",
    approved_at=datetime(2026, 4, 20, tzinfo=UTC),
    taxonomy_rows=(
        ApprovedTaxonomyMappingSeed(
            "Cash",
            "All Assets",
            None,
            None,
            "cash",
            False,
            None,
            "Official AustralianSuper Stable cash institution holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "Fixed Income",
            "All Assets",
            None,
            None,
            "fixed_income",
            False,
            None,
            "Official AustralianSuper Stable fixed-income issuer holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "Fixed Income",
            "Externally Managed",
            None,
            None,
            "fixed_income",
            False,
            None,
            "Official AustralianSuper Stable externally managed fixed-income slice",
        ),
        ApprovedTaxonomyMappingSeed(
            "Fixed Income",
            "Internally Managed",
            None,
            None,
            "fixed_income",
            False,
            None,
            "Official AustralianSuper Stable internally managed fixed-income slice",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Alternatives",
            "Listed",
            None,
            None,
            "alternatives",
            False,
            None,
            "Official AustralianSuper Stable listed-alternatives holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Equity",
            "Listed",
            None,
            None,
            "listed_equity",
            False,
            None,
            "Official AustralianSuper Stable listed-equity holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Infrastructure",
            "Listed",
            None,
            None,
            "listed_infrastructure",
            False,
            None,
            "Official AustralianSuper Stable listed-infrastructure holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Property",
            "Listed",
            None,
            None,
            "listed_property",
            False,
            None,
            "Official AustralianSuper Stable listed-property holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "Private Debt",
            "Fixed Income Private Debt",
            None,
            None,
            "private_debt",
            False,
            "name_only",
            "Official AustralianSuper Stable private-debt name-only disclosure",
        ),
        ApprovedTaxonomyMappingSeed(
            "Private Equity",
            "Private Equity",
            None,
            None,
            "unlisted_equity",
            False,
            "name_only",
            "Official AustralianSuper Stable private-equity name-only disclosure",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Alternatives",
            "Internally Managed",
            None,
            None,
            "alternatives",
            False,
            "name_only",
            "Official AustralianSuper Stable unlisted-alternatives name-only disclosure",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Equity",
            "Externally Managed",
            None,
            None,
            "unlisted_equity",
            False,
            None,
            "Official AustralianSuper Stable externally managed unlisted-equity slice",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Equity",
            "Internally Managed",
            None,
            None,
            "unlisted_equity",
            False,
            "ownership_only",
            "Official AustralianSuper Stable internally managed unlisted-equity ownership slice",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Infrastructure",
            "All Assets",
            None,
            None,
            "unlisted_infrastructure",
            False,
            "name_only",
            "Official AustralianSuper Stable all-assets unlisted-infrastructure metadata row",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Infrastructure",
            "Externally Managed",
            None,
            None,
            "unlisted_infrastructure",
            False,
            None,
            "Official AustralianSuper Stable externally managed unlisted-infrastructure slice",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Infrastructure",
            "Internally Managed",
            None,
            None,
            "unlisted_infrastructure",
            False,
            "ownership_only",
            "Official AustralianSuper Stable internally managed unlisted-infrastructure ownership slice",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Property",
            "All Assets",
            None,
            None,
            "unlisted_property",
            False,
            "name_only",
            "Official AustralianSuper Stable all-assets unlisted-property metadata row",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Property",
            "Externally Managed",
            None,
            None,
            "unlisted_property",
            False,
            None,
            "Official AustralianSuper Stable externally managed unlisted-property slice",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Property",
            "Internally Managed",
            None,
            None,
            "unlisted_property",
            False,
            "ownership_only",
            "Official AustralianSuper Stable internally managed unlisted-property ownership slice",
        ),
        ApprovedTaxonomyMappingSeed(
            "Cash",
            "All Assets",
            None,
            None,
            "cash",
            True,
            "aggregate_total",
            "Official AustralianSuper Stable cash total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Fixed Income",
            "Externally Managed",
            None,
            None,
            "fixed_income",
            True,
            "aggregate_total",
            "Official AustralianSuper Stable externally managed fixed-income total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Fixed Income",
            "Internally Managed",
            None,
            None,
            "fixed_income",
            True,
            "aggregate_total",
            "Official AustralianSuper Stable internally managed fixed-income total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Alternatives",
            "Listed",
            None,
            None,
            "alternatives",
            True,
            "aggregate_total",
            "Official AustralianSuper Stable listed-alternatives total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Equity",
            "Listed",
            None,
            None,
            "listed_equity",
            True,
            "aggregate_total",
            "Official AustralianSuper Stable listed-equity total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Infrastructure",
            "Listed",
            None,
            None,
            "listed_infrastructure",
            True,
            "aggregate_total",
            "Official AustralianSuper Stable listed-infrastructure total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Listed Property",
            "Listed",
            None,
            None,
            "listed_property",
            True,
            "aggregate_total",
            "Official AustralianSuper Stable listed-property total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Alternatives",
            "Internally Managed",
            None,
            None,
            "alternatives",
            True,
            "aggregate_total",
            "Official AustralianSuper Stable internally managed unlisted-alternatives total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Equity",
            "Externally Managed",
            None,
            None,
            "unlisted_equity",
            True,
            "aggregate_total",
            "Official AustralianSuper Stable externally managed unlisted-equity total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Equity",
            "Internally Managed",
            None,
            None,
            "unlisted_equity",
            True,
            "aggregate_total",
            "Official AustralianSuper Stable internally managed unlisted-equity total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Infrastructure",
            "Externally Managed",
            None,
            None,
            "unlisted_infrastructure",
            True,
            "aggregate_total",
            "Official AustralianSuper Stable externally managed unlisted-infrastructure total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Infrastructure",
            "Internally Managed",
            None,
            None,
            "unlisted_infrastructure",
            True,
            "aggregate_total",
            "Official AustralianSuper Stable internally managed unlisted-infrastructure total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Property",
            "Externally Managed",
            None,
            None,
            "unlisted_property",
            True,
            "aggregate_total",
            "Official AustralianSuper Stable externally managed unlisted-property total",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Property",
            "Internally Managed",
            None,
            None,
            "unlisted_property",
            True,
            "aggregate_total",
            "Official AustralianSuper Stable internally managed unlisted-property total",
        ),
    ),
)


AUSTRALIANSUPER_CONSERVATIVE_APPROVED_MAPPING = ApprovedAdapterMappingSeed(
    id=AUSTRALIANSUPER_CONSERVATIVE_MAPPING_VERSION_ID,
    adapter_key="AustralianSuperPhdAdapter",
    schema_fingerprint=AUSTRALIANSUPER_STABLE_APPROVED_MAPPING.schema_fingerprint,
    structural_expectations_json={
        **AUSTRALIANSUPER_STABLE_APPROVED_MAPPING.structural_expectations_json,
        "observed_option_codes": ["ARYO"],
        "observed_option_names": ["Conservative Balanced"],
    },
    notes=(
        "Approved Stage 2 AustralianSuper Conservative Balanced slice using the real "
        "Conservative file and the thin fund-specific adapter. Member Direct and Stable are "
        "approved; Socially Aware remains gated pending its own mapping approval."
    ),
    approved_by="repo-seed",
    approved_at=datetime(2026, 4, 20, tzinfo=UTC),
    taxonomy_rows=_retarget_taxonomy_notes(
        AUSTRALIANSUPER_STABLE_APPROVED_MAPPING.taxonomy_rows,
        from_label="Stable",
        to_label="Conservative Balanced",
    ),
)


UNISUPER_APPROVED_MAPPING = ApprovedAdapterMappingSeed(
    id=UNISUPER_MAPPING_VERSION_ID,
    adapter_key="UniSuperPhdStateMachineAdapter",
    schema_fingerprint="7dc5e32ce188c76fae55f3f4a1c0f09d79eb55ceb9c27a378cb905f222b31cb5",
    structural_expectations_json={
        "observed_headers": [
            [
                "ASSET CLASS",
                "",
                "",
                "ACTUAL ASSET ALLOCATION (% OF TOTAL ASSETS (INCLUDING DERIVATIVES) IN THE INVESTMENT OPTION)",
                "EFFECT OF DERIVATIVE EXPOSURE (% OF TOTAL ASSETS ( INCLUDING DERIVATIVES) ON THE INVESTMENT OPTION)",
            ],
            [
                "CURRENCY EXPOSURE",
                "",
                "",
                "ACTUAL CURRENCY EXPOSURE (% OF TOTAL ASSETS AND DERIVATIVES UNDER MANAGEMENT)",
                "EFFECT OF DERIVATIVES EXPOSURE (% OF ASSETS AND DERIVATIVES UNDER MANAGEMENT )",
            ],
            ["KIND OF DERIVATIVE", "", "", "VALUE (AUD)", "WEIGHTING %"],
            ["NAME OF FUND MANAGER", "", "", "VALUE (AUD)", "WEIGHTING %"],
            ["NAME OF FUND MANAGER", "", "", "VALUE (AUD)", "WEIGHTING (%)"],
            ["NAME OF INSTITUTION", "", "CURRENCY", "VALUE (AUD)", "WEIGHTING (%)"],
            ["NAME OF ISSUER/COUNTERPARTY", "", "", "VALUE (AUD)", "WEIGHTING (%)"],
            ["NAME/KIND OF INVESTMENT ITEM", "", "", "VALUE (AUD)", "WEIGHTING %"],
            ["NAME/KIND OF INVESTMENT ITEM", "", "% OWNERSHIP", "VALUE (AUD)", "WEIGHTING (%)"],
            ["NAME/KIND OF INVESTMENT ITEM", "ADDRESS", "% OF PROPERTY HELD", "VALUE (AUD)", "WEIGHTING (%)"],
            ["NAME/KIND OF INVESTMENT ITEM", "SECURITY IDENTIFIER", "UNITS HELD", "VALUE (AUD)", "WEIGHTING %"],
            ["NAME/KIND OF INVESTMENT ITEM", "SECURITY IDENTIFIER", "UNITS HELD", "VALUE (AUD)", "WEIGHTING (%)"],
        ],
        "observed_section_labels": [
            "ASSETS",
            "CASH",
            "DERIVATIVES BY ASSET CLASS",
            "DERIVATIVES BY CURRENCY",
            "DERIVATIVES BY KIND OF DERIVATIVE",
            "FIXED INCOME",
            "LISTED ALTERNATIVES",
            "LISTED EQUITY",
            "LISTED INFRASTRUCTURE",
            "LISTED PROPERTY",
            "TABLE 1",
            "TABLE 2",
            "TABLE 3",
            "TABLE 4",
            "UNLISTED ALTERNATIVES",
            "UNLISTED EQUITY",
            "UNLISTED INFRASTRUCTURE",
            "UNLISTED PROPERTY",
        ],
        "observed_tables": [1, 2, 3, 4],
        "observed_internal_external_values": ["Externally Managed", "Internally Managed"],
        "observed_asset_classes": [
            "CASH",
            "FIXED INCOME",
            "LISTED ALTERNATIVES",
            "LISTED EQUITY",
            "LISTED INFRASTRUCTURE",
            "LISTED PROPERTY",
            "UNLISTED ALTERNATIVES",
            "UNLISTED EQUITY",
            "UNLISTED INFRASTRUCTURE",
            "UNLISTED PROPERTY",
        ],
        "observed_scope_modifiers": [
            "Held directly or by associated entities or PSTs",
            "Held directly or by associated entities or by PSTs",
            "Held directly or by associated entity or by PSTs",
        ],
    },
    notes="Approved Stage 2 UniSuper state-machine mapping seeded from the real-file extract.",
    approved_by="repo-seed",
    approved_at=datetime(2026, 4, 19, tzinfo=UTC),
    taxonomy_rows=(
        ApprovedTaxonomyMappingSeed("CASH", None, None, None, "cash", False, None, "Cash row"),
        ApprovedTaxonomyMappingSeed("CASH", None, None, None, "cash", True, "aggregate_total", "Cash total"),
        ApprovedTaxonomyMappingSeed(
            "FIXED INCOME",
            "Internally Managed",
            None,
            None,
            "fixed_income",
            False,
            None,
            "Fixed-income issuer row",
        ),
        ApprovedTaxonomyMappingSeed(
            "FIXED INCOME",
            "Externally Managed",
            None,
            None,
            "fixed_income",
            False,
            None,
            "Fixed-income manager row",
        ),
        ApprovedTaxonomyMappingSeed(
            "FIXED INCOME",
            "Internally Managed",
            None,
            None,
            "fixed_income",
            True,
            "aggregate_total",
            "Fixed-income internal total",
        ),
        ApprovedTaxonomyMappingSeed(
            "FIXED INCOME",
            "Externally Managed",
            None,
            None,
            "fixed_income",
            True,
            "aggregate_total",
            "Fixed-income external total",
        ),
        ApprovedTaxonomyMappingSeed(
            "LISTED EQUITY",
            None,
            None,
            None,
            "listed_equity",
            False,
            None,
            "Listed-equity row",
        ),
        ApprovedTaxonomyMappingSeed(
            "LISTED EQUITY",
            None,
            None,
            None,
            "listed_equity",
            True,
            "aggregate_total",
            "Listed-equity total",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED EQUITY",
            "Internally Managed",
            None,
            None,
            "unlisted_equity",
            False,
            None,
            "Unlisted-equity direct row",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED EQUITY",
            "Externally Managed",
            None,
            None,
            "unlisted_equity",
            False,
            None,
            "Unlisted-equity manager row",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED EQUITY",
            "Internally Managed",
            None,
            None,
            "unlisted_equity",
            True,
            "aggregate_total",
            "Unlisted-equity internal total",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED EQUITY",
            "Externally Managed",
            None,
            None,
            "unlisted_equity",
            True,
            "aggregate_total",
            "Unlisted-equity external total",
        ),
        ApprovedTaxonomyMappingSeed(
            "LISTED PROPERTY",
            None,
            None,
            None,
            "listed_property",
            False,
            None,
            "Listed-property row",
        ),
        ApprovedTaxonomyMappingSeed(
            "LISTED PROPERTY",
            None,
            None,
            None,
            "listed_property",
            True,
            "aggregate_total",
            "Listed-property total",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED PROPERTY",
            "Internally Managed",
            None,
            None,
            "unlisted_property",
            False,
            None,
            "Unlisted-property direct row",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED PROPERTY",
            "Externally Managed",
            None,
            None,
            "unlisted_property",
            False,
            None,
            "Unlisted-property manager row",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED PROPERTY",
            "Internally Managed",
            None,
            None,
            "unlisted_property",
            True,
            "aggregate_total",
            "Unlisted-property internal total",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED PROPERTY",
            "Externally Managed",
            None,
            None,
            "unlisted_property",
            True,
            "aggregate_total",
            "Unlisted-property external total",
        ),
        ApprovedTaxonomyMappingSeed(
            "LISTED INFRASTRUCTURE",
            None,
            None,
            None,
            "listed_infrastructure",
            False,
            None,
            "Listed-infrastructure row",
        ),
        ApprovedTaxonomyMappingSeed(
            "LISTED INFRASTRUCTURE",
            None,
            None,
            None,
            "listed_infrastructure",
            True,
            "aggregate_total",
            "Listed-infrastructure total",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED INFRASTRUCTURE",
            "Internally Managed",
            None,
            None,
            "unlisted_infrastructure",
            False,
            None,
            "Unlisted-infrastructure direct row",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED INFRASTRUCTURE",
            "Externally Managed",
            None,
            None,
            "unlisted_infrastructure",
            False,
            None,
            "Unlisted-infrastructure manager row",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED INFRASTRUCTURE",
            "Internally Managed",
            None,
            None,
            "unlisted_infrastructure",
            True,
            "aggregate_total",
            "Unlisted-infrastructure internal total",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED INFRASTRUCTURE",
            "Externally Managed",
            None,
            None,
            "unlisted_infrastructure",
            True,
            "aggregate_total",
            "Unlisted-infrastructure external total",
        ),
        ApprovedTaxonomyMappingSeed(
            "LISTED ALTERNATIVES",
            None,
            None,
            None,
            "alternatives",
            False,
            None,
            "Listed-alternatives row",
        ),
        ApprovedTaxonomyMappingSeed(
            "LISTED ALTERNATIVES",
            None,
            None,
            None,
            "alternatives",
            True,
            "aggregate_total",
            "Listed-alternatives total",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED ALTERNATIVES",
            "Internally Managed",
            None,
            None,
            "alternatives",
            False,
            None,
            "Unlisted-alternatives direct row",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED ALTERNATIVES",
            "Externally Managed",
            None,
            None,
            "alternatives",
            False,
            None,
            "Unlisted-alternatives manager row",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED ALTERNATIVES",
            "Internally Managed",
            None,
            None,
            "alternatives",
            True,
            "aggregate_total",
            "Unlisted-alternatives internal total",
        ),
        ApprovedTaxonomyMappingSeed(
            "UNLISTED ALTERNATIVES",
            "Externally Managed",
            None,
            None,
            "alternatives",
            True,
            "aggregate_total",
            "Unlisted-alternatives external total",
        ),
        ApprovedTaxonomyMappingSeed(
            "TOTAL INVESTMENT ITEMS",
            None,
            None,
            None,
            "multi_asset_other",
            True,
            "aggregate_total",
            "Whole-option aggregate total",
        ),
    ),
)


HOSTPLUS_APPROVED_MAPPING = ApprovedAdapterMappingSeed(
    id=HOSTPLUS_MAPPING_VERSION_ID,
    adapter_key="HostPlusPhdStateMachineAdapter",
    schema_fingerprint="abd48bab0474bf5ada8c5e571b5215b5b3d55b97b881bfb8ba11eaa9dc68be59",
    structural_expectations_json={
        "observed_headers": [
            [
                "ASSET CLASS",
                "",
                "",
                "ACTUAL ASSET ALLOCATION (% OF ASSETS (INCLUDING DERIVATIVES) IN THE INVESTMENT OPTION)",
                "EFFECT OF DERIVATIVES EXPOSURE (% OF ASSETS (INCLUDING DERIVATIVES) IN THE INVESTMENT OPTION)",
            ],
            [
                "CURRENCY EXPOSURE",
                "",
                "",
                "ACTUAL CURRENCY EXPOSURE (% OF ASSETS (INCLUDING DERIVATIVES) IN THE INVESTMENT OPTION)",
                "EFFECT OF DERIVATIVES EXPOSURE (% OF ASSETS (INCLUDING DERIVATIVES) IN THE INVESTMENT OPTION)",
            ],
            ["KIND OF DERIVATIVE", "", "", "VALUE (AUD)", "WEIGHTING (%)"],
            ["NAME OF FUND MANAGER", "", "", "VALUE (AUD)", "WEIGHTING (%)"],
            ["NAME OF INSTITUTION", "CURRENCY", "", "VALUE (AUD)", "WEIGHTING (%)"],
            ["NAME/KIND OF INVESTMENT ITEM", "", "% OWNERSHIP", "VALUE (AUD)", "WEIGHTING (%)"],
            ["NAME/KIND OF INVESTMENT ITEM", "SECURITY IDENTIFIER", "UNITS HELD", "VALUE (AUD)", "WEIGHTING (%)"],
        ],
        "observed_section_labels": [
            "CASH",
            "HOSTPLUS",
            "LISTED EQUITY",
            "TABLE 1",
            "TABLE 2",
            "TABLE 3",
            "TABLE 4",
            "TOTAL INVESTMENT ITEMS",
            "UNLISTED EQUITY",
        ],
        "observed_tables": [1, 2, 3, 4],
        "observed_internal_external_values": ["Externally Managed", "Internally Managed"],
        "observed_asset_classes": ["Cash", "Listed Equity", "Unlisted Equity"],
    },
    notes=(
        "Approved Stage 2 Host-Plus mapping seeded from the real single-option file. "
        "UTF-8 replacement baseline is 3 for the known em-dash corruption points."
    ),
    approved_by="repo-seed",
    approved_at=datetime(2026, 4, 19, tzinfo=UTC),
    taxonomy_rows=(
        ApprovedTaxonomyMappingSeed("Cash", None, None, None, "cash", False, None, "Table 1 cash holding"),
        ApprovedTaxonomyMappingSeed(
            "Listed Equity",
            None,
            None,
            None,
            "listed_equity",
            False,
            None,
            "Table 1 listed security holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Equity",
            "Internally Managed",
            None,
            None,
            "unlisted_equity",
            False,
            None,
            "Table 1 internally managed ownership holding",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Equity",
            "Externally Managed",
            None,
            None,
            "unlisted_equity",
            False,
            None,
            "Table 1 externally managed fund-manager rollup",
        ),
        ApprovedTaxonomyMappingSeed("Cash", None, None, None, "cash", True, "aggregate_total", "Cash total row"),
        ApprovedTaxonomyMappingSeed(
            "Listed Equity",
            None,
            None,
            None,
            "listed_equity",
            True,
            "aggregate_total",
            "Listed equity total row",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Equity",
            "Internally Managed",
            None,
            None,
            "unlisted_equity",
            True,
            "aggregate_total",
            "Internally managed unlisted equity total row",
        ),
        ApprovedTaxonomyMappingSeed(
            "Unlisted Equity",
            "Externally Managed",
            None,
            None,
            "unlisted_equity",
            True,
            "aggregate_total",
            "Externally managed unlisted equity total row",
        ),
        ApprovedTaxonomyMappingSeed(
            "TOTAL INVESTMENT ITEMS",
            None,
            None,
            None,
            "multi_asset_other",
            True,
            "aggregate_total",
            "Whole-option aggregate total",
        ),
    ),
)


CBUS_APPROVED_MAPPING = ApprovedAdapterMappingSeed(
    id=CBUS_MAPPING_VERSION_ID,
    adapter_key="CbusPhdAdapter",
    schema_fingerprint="841a5229926cf6dc5073eeac34fe7d217560b16feb630f6ce8f01d35c9326be5",
    structural_expectations_json={
        "observed_headers": [CBUS_EXPECTED_HEADER],
        "observed_section_labels": [
            "ASSETS",
            "DERIVATIVES",
            "DERIVATIVES BY ASSET CLASS",
            "DERIVATIVES BY CURRENCY",
        ],
        "observed_tables": [1, 2, 3, 4],
        "observed_internal_external_values": ["external", "internal"],
        "observed_asset_classes": sorted(
            {
                mapping.source_asset_class_raw
                for mapping in (*CBUS_SECTION_MAPPINGS.values(), *CBUS_TOTAL_SECTION_MAPPINGS.values())
            }
        ),
        "observed_option_names": ["High Growth Accumulation Option"],
    },
    notes=(
        "Approved Stage 2 late-add Cbus mapping seeded from the verified real "
        "High Growth Accumulation Option file for 2025-12-31."
    ),
    approved_by="repo-seed",
    approved_at=datetime(2026, 4, 24, tzinfo=UTC),
    taxonomy_rows=tuple(
        ApprovedTaxonomyMappingSeed(
            mapping.source_asset_class_raw,
            mapping.source_subclass_raw,
            None,
            None,
            mapping.canonical_asset_class_code,
            mapping.is_aggregate,
            "aggregate_total" if mapping.is_aggregate else None,
            (
                "Cbus Stage 2 late-add aggregate mapping"
                if mapping.is_aggregate
                else "Cbus Stage 2 late-add section mapping"
            ),
        )
        for mapping in (*CBUS_SECTION_MAPPINGS.values(), *CBUS_TOTAL_SECTION_MAPPINGS.values())
    ),
)


APPROVED_MAPPING_SEEDS: dict[str, tuple[ApprovedAdapterMappingSeed, ...]] = {
    AWARE_APPROVED_MAPPING.adapter_key: (AWARE_APPROVED_MAPPING,),
    ART_QSUPER_APPROVED_MAPPING.adapter_key: (ART_QSUPER_APPROVED_MAPPING,),
    ART_SUNSUPER_APPROVED_MAPPING.adapter_key: (ART_SUNSUPER_APPROVED_MAPPING,),
    AUSTRALIANSUPER_APPROVED_MAPPING.adapter_key: (
        AUSTRALIANSUPER_APPROVED_MAPPING,
        AUSTRALIANSUPER_STABLE_APPROVED_MAPPING,
        AUSTRALIANSUPER_CONSERVATIVE_APPROVED_MAPPING,
    ),
    UNISUPER_APPROVED_MAPPING.adapter_key: (UNISUPER_APPROVED_MAPPING,),
    HOSTPLUS_APPROVED_MAPPING.adapter_key: (HOSTPLUS_APPROVED_MAPPING,),
    CBUS_APPROVED_MAPPING.adapter_key: (CBUS_APPROVED_MAPPING,),
}


def _approved_mapping_seeds_for(adapter_key: str) -> tuple[ApprovedAdapterMappingSeed, ...]:
    seeds = APPROVED_MAPPING_SEEDS.get(adapter_key)
    if seeds is None:
        raise MissingApprovedMappingError(f"No approved mapping seed is configured for adapter {adapter_key!r}")
    return seeds


def _ensure_seed_seeded(session: Session, *, seed: ApprovedAdapterMappingSeed) -> AdapterMappingVersion:
    mapping_version = session.get(AdapterMappingVersion, seed.id)
    if mapping_version is None:
        mapping_version = AdapterMappingVersion(
            id=seed.id,
            adapter_key=seed.adapter_key,
            schema_fingerprint=seed.schema_fingerprint,
            structural_expectations_json=seed.structural_expectations_json,
            notes=seed.notes,
            approved_by=seed.approved_by,
            approved_at=seed.approved_at,
            is_active=True,
        )
        session.add(mapping_version)
        session.flush()

    existing_rows = session.scalars(
        select(TaxonomyMapping).where(
            TaxonomyMapping.adapter_key == seed.adapter_key,
            TaxonomyMapping.mapping_version == seed.id,
        )
    ).all()
    if not existing_rows:
        for row in seed.taxonomy_rows:
            session.add(
                TaxonomyMapping(
                    adapter_key=seed.adapter_key,
                    mapping_version=seed.id,
                    source_asset_class_raw=row.source_asset_class_raw,
                    source_filter_raw=row.source_filter_raw,
                    source_sub_filter_raw=row.source_sub_filter_raw,
                    source_section_raw=row.source_section_raw,
                    canonical_asset_class_code=row.canonical_asset_class_code,
                    is_aggregate_default=row.is_aggregate_default,
                    disclosure_completeness_default=row.disclosure_completeness_default,
                    notes=row.notes,
                    approved_by=seed.approved_by,
                    approved_at=seed.approved_at,
                )
            )
        session.flush()

    return mapping_version


def ensure_approved_mapping_seeded(session: Session, *, adapter_key: str) -> AdapterMappingVersion:
    mapping_versions = [
        _ensure_seed_seeded(session, seed=seed)
        for seed in _approved_mapping_seeds_for(adapter_key)
    ]
    return mapping_versions[0]


def enforce_approved_mapping(
    session: Session,
    *,
    source_file: SourceFile,
    parse_result: AdapterParseResult,
    raw_bytes: bytes,
    source_section_raw: str | None = None,
) -> str:
    mapping_versions = [
        _ensure_seed_seeded(session, seed=seed)
        for seed in _approved_mapping_seeds_for(source_file.adapter_key)
    ]
    best_drift_match: tuple[AdapterMappingVersion, dict[str, object]] | None = None
    best_taxonomy_match: tuple[AdapterMappingVersion, dict[str, object]] | None = None

    for mapping_version in mapping_versions:
        drift_summary = _build_structural_drift_summary(mapping_version, parse_result)
        if drift_summary:
            if best_drift_match is None or _summary_score(drift_summary) < _summary_score(best_drift_match[1]):
                best_drift_match = (mapping_version, drift_summary)
            continue

        taxonomy_summary = _build_taxonomy_validation_summary(
            session,
            mapping_version_id=mapping_version.id,
            parse_result=parse_result,
            source_section_raw=source_section_raw,
        )
        if taxonomy_summary:
            if best_taxonomy_match is None or _summary_score(taxonomy_summary) < _summary_score(best_taxonomy_match[1]):
                best_taxonomy_match = (mapping_version, taxonomy_summary)
            continue

        source_file.mapping_version_id = mapping_version.id
        return mapping_version.id

    if best_taxonomy_match is not None:
        mapping_version, taxonomy_summary = best_taxonomy_match
        source_file.mapping_version_id = mapping_version.id
        source_file.ingest_status = "review_required"
        create_schema_review_queue_item(
            session,
            source_file=source_file,
            approved_mapping_version_id=mapping_version.id,
            review_reason="unapproved_taxonomy_mapping",
            observed_schema_fingerprint=parse_result.schema_fingerprint,
            drift_summary_json=taxonomy_summary,
            raw_bytes=raw_bytes,
        )
        session.flush()
        raise UnapprovedTaxonomyMappingError(
            f"{source_file.adapter_key} emitted rows not covered by approved taxonomy mapping {mapping_version.id}"
        )

    if best_drift_match is None:
        raise MissingApprovedMappingError(f"No approved mapping seed is configured for adapter {source_file.adapter_key!r}")

    mapping_version, drift_summary = best_drift_match
    source_file.mapping_version_id = mapping_version.id
    source_file.ingest_status = "review_required"
    create_schema_review_queue_item(
        session,
        source_file=source_file,
        approved_mapping_version_id=mapping_version.id,
        review_reason="schema_drift",
        observed_schema_fingerprint=parse_result.schema_fingerprint,
        drift_summary_json=drift_summary,
        raw_bytes=raw_bytes,
    )
    session.flush()
    raise SchemaDriftDetectedError(
        f"{source_file.adapter_key} drift detected against approved mapping {mapping_version.id}"
    )


def create_schema_review_queue_item(
    session: Session,
    *,
    source_file: SourceFile,
    approved_mapping_version_id: str | None,
    review_reason: str,
    observed_schema_fingerprint: str | None,
    drift_summary_json: dict[str, object],
    raw_bytes: bytes,
) -> None:
    session.add(
        SchemaReviewQueue(
            adapter_key=source_file.adapter_key,
            source_file_id=source_file.id,
            source_url=source_file.source_url,
            checksum=source_file.checksum,
            observed_schema_fingerprint=observed_schema_fingerprint,
            approved_mapping_version_id=approved_mapping_version_id,
            review_reason=review_reason,
            status="open",
            drift_summary_json=drift_summary_json,
            sample_rows_json=_sample_rows(raw_bytes),
        )
    )


def _build_structural_drift_summary(
    mapping_version: AdapterMappingVersion,
    parse_result: AdapterParseResult,
) -> dict[str, object]:
    expected = mapping_version.structural_expectations_json
    actual = parse_result.structural_metadata
    summary: dict[str, object] = {}

    if parse_result.schema_fingerprint != mapping_version.schema_fingerprint:
        summary["schema_fingerprint"] = {
            "expected": mapping_version.schema_fingerprint,
            "actual": parse_result.schema_fingerprint,
        }

    for key in (
        "observed_headers",
        "observed_section_labels",
        "observed_tables",
        "observed_internal_external_values",
        "observed_asset_classes",
        "observed_filters",
        "observed_name_types",
    ):
        if expected.get(key) != actual.get(key):
            summary[key] = {
                "expected": expected.get(key),
                "actual": actual.get(key),
            }

    for key in ("observed_option_codes", "observed_option_names"):
        if key not in expected:
            continue
        if expected.get(key) != actual.get(key):
            summary[key] = {
                "expected": expected.get(key),
                "actual": actual.get(key),
            }

    return summary


def _build_taxonomy_validation_summary(
    session: Session,
    *,
    mapping_version_id: str,
    parse_result: AdapterParseResult,
    source_section_raw: str | None,
) -> dict[str, object]:
    rows = session.scalars(
        select(TaxonomyMapping).where(TaxonomyMapping.mapping_version == mapping_version_id)
    ).all()
    # The taxonomy key is intentionally adapter-agnostic:
    # raw class label + optional adapter-specific qualifier + section + aggregate flag.
    # Aware uses section labels and management scope; ART-QSuper only uses the qualifier.
    mapping_lookup = {
        (
            row.source_asset_class_raw,
            row.source_filter_raw,
            row.source_section_raw,
            row.is_aggregate_default,
        ): row
        for row in rows
    }

    mismatches: list[dict[str, object]] = []
    for record in parse_result.holdings:
        mapping_row = mapping_lookup.get(
            (
                record.source_asset_class_raw,
                record.source_subclass_raw,
                source_section_raw,
                record.is_aggregate,
            )
        )
        if mapping_row is None:
            mismatches.append(
                {
                    "reason": "missing_mapping",
                    "source_row_number": record.source_row_number,
                    "source_asset_class_raw": record.source_asset_class_raw,
                    "source_subclass_raw": record.source_subclass_raw,
                    "is_aggregate": record.is_aggregate,
                }
            )
            continue
        if mapping_row.canonical_asset_class_code != record.canonical_asset_class_code:
            mismatches.append(
                {
                    "reason": "canonical_asset_class_mismatch",
                    "source_row_number": record.source_row_number,
                    "source_asset_class_raw": record.source_asset_class_raw,
                    "source_subclass_raw": record.source_subclass_raw,
                    "expected": mapping_row.canonical_asset_class_code,
                    "actual": record.canonical_asset_class_code,
                }
            )
        if mapping_row.disclosure_completeness_default and (
            mapping_row.disclosure_completeness_default != record.disclosure_completeness
        ):
            mismatches.append(
                {
                    "reason": "disclosure_completeness_mismatch",
                    "source_row_number": record.source_row_number,
                    "source_asset_class_raw": record.source_asset_class_raw,
                    "expected": mapping_row.disclosure_completeness_default,
                    "actual": record.disclosure_completeness,
                }
            )

    if not mismatches:
        return {}
    return {"taxonomy_mismatches": mismatches[:10]}


def _summary_score(summary: dict[str, object]) -> int:
    score = len(summary)
    for value in summary.values():
        if isinstance(value, dict):
            score += len(value)
        elif isinstance(value, list):
            score += len(value)
    return score


def _sample_rows(raw_bytes: bytes) -> list[list[str]]:
    rows = list(csv.reader(io.StringIO(raw_bytes.decode("utf-8", errors="replace"))))
    samples: list[list[str]] = []
    for row in rows:
        if not any(cell.strip() for cell in row):
            continue
        samples.append(row)
        if len(samples) == 20:
            break
    return samples
