from __future__ import annotations

from dataclasses import dataclass
from datetime import date


ADAPTER_KEY = "australian_retirement_trust_real_16col"
MAPPING_VERSION_ID = "art-stage2-real-2025-12-31-v1"
APPROVED_SCHEMA_FINGERPRINT = "b08a08c11dbab46a70545220c2217fce074b23bfc2d135f8e035aab136e3bd6b"
APPROVED_REPORTING_DATE_RAW = "31 December 2025"
APPROVED_REPORTING_DATE = date(2025, 12, 31)
EXPECTED_DERIVATIVE_POSTURE_ROWS_PER_FILE = 17

EXPECTED_HEADER = [
    "AsAtDate",
    "OptionName",
    "Type",
    "Name",
    "Currency",
    "SecurityIdentifier",
    "UnitsHeld",
    "Address",
    "Ownership",
    "Value",
    "Weighting",
    "ActualExposure",
    "EffectOfExposure",
    "TotalValue",
    "TotalWeighting",
    "TotalActualExposure",
]

DERIVATIVE_POSTURE_TYPES = {
    "Derivatives By Kind",
    "Derivatives By AssetClass",
    "Derivatives By Currency",
}

AGGREGATE_TOTAL_TYPES = {
    "AssetTotal",
    "OptionTotal",
}


@dataclass(frozen=True)
class AssetClassMappingRule:
    canonical_code: str


def _key(value: str) -> str:
    return value.strip().casefold()


ART_REAL_16COL_TYPE_MAPPINGS: dict[str, AssetClassMappingRule] = {
    _key("Cash"): AssetClassMappingRule("cash"),
    _key("Fixed Income Externally Managed"): AssetClassMappingRule("fixed_income"),
    _key("Fixed Income Internally Managed"): AssetClassMappingRule("fixed_income"),
    _key("Listed Equity"): AssetClassMappingRule("listed_equity"),
    _key("Unlisted Equity Externally Managed"): AssetClassMappingRule("unlisted_equity"),
    _key("Unlisted Equity Internally Managed"): AssetClassMappingRule("unlisted_equity"),
    _key("Listed Property"): AssetClassMappingRule("listed_property"),
    _key("Unlisted Property Externally Managed"): AssetClassMappingRule("unlisted_property"),
    _key("Listed Infrastructure"): AssetClassMappingRule("listed_infrastructure"),
    _key("Unlisted Infrastructure Internally Managed"): AssetClassMappingRule("unlisted_infrastructure"),
    _key("Unlisted Infrastructure Externally Managed"): AssetClassMappingRule("unlisted_infrastructure"),
    _key("Unlisted Alternatives Externally Managed"): AssetClassMappingRule("alternatives"),
    _key("AssetTotal"): AssetClassMappingRule("multi_asset_other"),
    _key("OptionTotal"): AssetClassMappingRule("multi_asset_other"),
}

APPROVED_TYPE_VALUES = tuple(
    sorted(
        [
            *DERIVATIVE_POSTURE_TYPES,
            *AGGREGATE_TOTAL_TYPES,
            "Cash",
            "Fixed Income Externally Managed",
            "Fixed Income Internally Managed",
            "Listed Equity",
            "Listed Infrastructure",
            "Listed Property",
            "Unlisted Alternatives Externally Managed",
            "Unlisted Equity Externally Managed",
            "Unlisted Equity Internally Managed",
            "Unlisted Infrastructure Externally Managed",
            "Unlisted Infrastructure Internally Managed",
            "Unlisted Property Externally Managed",
        ]
    )
)


def lookup_asset_class_mapping(type_value: str) -> AssetClassMappingRule | None:
    return ART_REAL_16COL_TYPE_MAPPINGS.get(_key(type_value))


def is_derivative_posture_type(type_value: str) -> bool:
    return type_value in DERIVATIVE_POSTURE_TYPES


def derive_friendly_option_name(option_name_raw: str) -> str:
    return option_name_raw.replace("_", " ").strip()
