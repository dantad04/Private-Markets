from __future__ import annotations

from dataclasses import dataclass


EXPECTED_HEADER = [
    "OptionCode",
    "OptionName",
    "Filter",
    "AssetClass",
    "NameType",
    "Name",
    "SecurityIdentifier",
    "Currency",
    "UnitsHeld",
    "MarketValueAud",
    "OwnershipPct",
    "WeightingPct",
    "ValueRange",
    "Classification",
    "Address",
    "Location",
    "GeoLat",
    "GeoLng",
    "CurrentManagementStyle",
    "IssuerName",
    "ManagerName",
    "Country",
    "Notes",
    "SourceView",
]

MANAGEMENT_STYLE_FILTERS = {"externally managed", "internally managed"}
METADATA_ATTACHING_FILTERS = {"all assets", "private equity"}
PORTFOLIO_POSTURE_FILTERS = {"derivatives"}

# Option-code prefixes are deliberately not fund-identity mappings. `AR**`
# appears in more than one shared-family source, so identity checks must use
# file registration, source URL/domain, and content signals instead.


@dataclass(frozen=True)
class AssetClassMappingRule:
    canonical_code: str
    is_aggregate: bool = False


def _key(asset_class: str) -> str:
    return asset_class.strip().casefold()


SUNSUPER_SCHEMA_ASSET_CLASS_MAPPINGS: dict[str, AssetClassMappingRule] = {
    _key("Cash"): AssetClassMappingRule("cash"),
    _key("Fixed Income"): AssetClassMappingRule("fixed_income"),
    _key("Listed Equity"): AssetClassMappingRule("listed_equity"),
    _key("Listed Infrastructure"): AssetClassMappingRule("listed_infrastructure"),
    _key("Listed Property"): AssetClassMappingRule("listed_property"),
    _key("Private Equity"): AssetClassMappingRule("unlisted_equity"),
    _key("Unlisted Equity"): AssetClassMappingRule("unlisted_equity"),
    _key("Unlisted Infrastructure"): AssetClassMappingRule("unlisted_infrastructure"),
    _key("Unlisted Property"): AssetClassMappingRule("unlisted_property"),
}


def lookup_asset_class_mapping(asset_class: str) -> AssetClassMappingRule | None:
    return SUNSUPER_SCHEMA_ASSET_CLASS_MAPPINGS.get(_key(asset_class))
