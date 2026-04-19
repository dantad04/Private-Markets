from __future__ import annotations

from dataclasses import dataclass


EXPECTED_HEADER = [
    "AsAtDate",
    "OptionName",
    "AssetClass",
    "InternalExternal",
    "InvestmentName",
    "SecurityIdentifier",
    "Currency",
    "UnitsHeld",
    "MarketValueAud",
    "WeightingPct",
    "OwnershipPct",
    "Address",
    "Classification",
    "Location",
    "ValueBand",
    "Notes",
]


@dataclass(frozen=True)
class AssetClassMappingRule:
    canonical_code: str
    is_aggregate: bool


def _key(asset_class: str) -> str:
    return asset_class.strip().casefold()


ART_QSUPER_ASSET_CLASS_MAPPINGS: dict[str, AssetClassMappingRule] = {
    _key("Cash"): AssetClassMappingRule("cash", False),
    _key("Cash Total"): AssetClassMappingRule("cash", True),
    _key("Fixed Income"): AssetClassMappingRule("fixed_income", False),
    _key("Fixed Income Total"): AssetClassMappingRule("fixed_income", True),
    _key("Listed Equity"): AssetClassMappingRule("listed_equity", False),
    _key("Listed Equity Total"): AssetClassMappingRule("listed_equity", True),
    _key("Listed Infrastructure"): AssetClassMappingRule("listed_infrastructure", False),
    _key("Listed Infrastructure Total"): AssetClassMappingRule("listed_infrastructure", True),
    _key("Listed Property"): AssetClassMappingRule("listed_property", False),
    _key("Listed Property Total"): AssetClassMappingRule("listed_property", True),
    _key("Unlisted Equity"): AssetClassMappingRule("unlisted_equity", False),
    _key("Unlisted Equity Internal Total"): AssetClassMappingRule("unlisted_equity", True),
    _key("Unlisted Equity External Total"): AssetClassMappingRule("unlisted_equity", True),
    _key("Unlisted Infrastructure"): AssetClassMappingRule("unlisted_infrastructure", False),
    _key("Unlisted Infrastructure Total"): AssetClassMappingRule("unlisted_infrastructure", True),
    _key("Unlisted Property"): AssetClassMappingRule("unlisted_property", False),
    _key("Unlisted Property Total"): AssetClassMappingRule("unlisted_property", True),
    _key("Total Investment Items"): AssetClassMappingRule("multi_asset_other", True),
}


def lookup_asset_class_mapping(asset_class: str) -> AssetClassMappingRule | None:
    return ART_QSUPER_ASSET_CLASS_MAPPINGS.get(_key(asset_class))
