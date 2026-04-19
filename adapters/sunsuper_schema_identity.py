from __future__ import annotations

from dataclasses import dataclass
from urllib.parse import urlparse

from adapters.sunsuper_schema_mapping import EXPECTED_HEADER


AUSTRALIANSUPER_REAL_HEADER = [
    "Option Code",
    "Option Name",
    "Asset Class",
    "Filter",
    "Sub-Filter",
    "Name",
    "Name Type",
    "Currency",
    "Issuer Type",
    "Security Identifier",
    "Units Held",
    "Location",
    "Address",
    "% Ownership",
    "$ Value",
    "Weighting (%)",
    "Actual Currency Exposure (%)",
    "Actual Asset Allocation (%)",
    "Effect of Derivatives Exposure (%)",
    "Classification",
    "Sort Order",
    "Value Range",
    "Geo Latitude",
    "Geo Longitude",
]


AUSTRALIANSUPER_PATH_TOKENS = ("australiansuper",)
ART_PATH_TOKENS = ("australianretirementtrust", "australian-retirement-trust", "art_sunsuper", "art-sunsuper")

AUSTRALIANSUPER_STRONG_OPTION_NAMES = {"socially aware", "member direct", "conservative balanced"}
ART_STRONG_OPTION_PREFIXES = ("art ",)
FRIENDLY_FUND_OWNER_LABELS = {
    "art": "Australian Retirement Trust / Sunsuper lineage",
    "australiansuper": "AustralianSuper",
}


@dataclass(frozen=True)
class SharedSchemaIdentityAssessment:
    probable_fund_code: str | None
    confidence: str
    schema_variant: str
    source_domain: str | None
    reasons: tuple[str, ...]


def assess_shared_schema_fund_identity(
    *,
    source_url: str,
    option_names: set[str] | list[str] | tuple[str, ...],
    header: list[str] | None = None,
) -> SharedSchemaIdentityAssessment:
    lowered_source = source_url.casefold()
    parsed = urlparse(source_url)
    source_domain = parsed.hostname.casefold() if parsed.hostname else None
    normalised_option_names = {_normalise_text(option_name) for option_name in option_names}

    reasons: list[str] = []
    australiansuper_signals = 0
    art_signals = 0

    schema_variant = "unknown_shared_schema_variant"
    if header == AUSTRALIANSUPER_REAL_HEADER:
        schema_variant = "australiansuper_real_24col"
        reasons.append("header matches the observed AustralianSuper 24-column source variant")
    elif header == EXPECTED_HEADER:
        schema_variant = "normalised_shared_contract"
        reasons.append("header matches the internal shared-schema contract used by the ART narrow slice")

    if source_domain:
        if "australiansuper.com" in source_domain:
            australiansuper_signals += 2
            reasons.append(f"source domain {source_domain!r} matches AustralianSuper branding")
        if "australianretirementtrust.com.au" in source_domain or "art.com.au" in source_domain:
            art_signals += 2
            reasons.append(f"source domain {source_domain!r} matches Australian Retirement Trust branding")

    if any(token in lowered_source for token in AUSTRALIANSUPER_PATH_TOKENS):
        australiansuper_signals += 2
        reasons.append("source path contains explicit AustralianSuper branding")
    if any(token in lowered_source for token in ART_PATH_TOKENS):
        art_signals += 2
        reasons.append("source path contains explicit ART/Sunsuper branding")

    matched_australiansuper_options = sorted(
        option_name
        for option_name in normalised_option_names
        if option_name in AUSTRALIANSUPER_STRONG_OPTION_NAMES
    )
    if matched_australiansuper_options:
        australiansuper_signals += 1
        reasons.append(
            "option names include AustralianSuper-specific products: "
            + ", ".join(repr(name) for name in matched_australiansuper_options)
        )

    matched_art_options = sorted(
        option_name
        for option_name in normalised_option_names
        if option_name.startswith(ART_STRONG_OPTION_PREFIXES)
    )
    if matched_art_options:
        art_signals += 1
        reasons.append(
            "option names include ART-branded products: "
            + ", ".join(repr(name) for name in matched_art_options)
        )

    if australiansuper_signals > 0 and art_signals > 0:
        return SharedSchemaIdentityAssessment(
            probable_fund_code=None,
            confidence="conflicted",
            schema_variant=schema_variant,
            source_domain=source_domain,
            reasons=tuple(reasons),
        )
    if australiansuper_signals > 0:
        return SharedSchemaIdentityAssessment(
            probable_fund_code="australiansuper",
            confidence="high" if australiansuper_signals >= 2 else "medium",
            schema_variant=schema_variant,
            source_domain=source_domain,
            reasons=tuple(reasons),
        )
    if art_signals > 0:
        return SharedSchemaIdentityAssessment(
            probable_fund_code="art",
            confidence="high" if art_signals >= 2 else "medium",
            schema_variant=schema_variant,
            source_domain=source_domain,
            reasons=tuple(reasons),
        )
    reasons.append("no strong source/domain/content signals were present beyond the shared schema family")
    return SharedSchemaIdentityAssessment(
        probable_fund_code=None,
        confidence="unknown",
        schema_variant=schema_variant,
        source_domain=source_domain,
        reasons=tuple(reasons),
    )


def validate_declared_fund_identity(
    *,
    declared_fund_code: str | int,
    assessment: SharedSchemaIdentityAssessment,
) -> list[str]:
    declared = str(declared_fund_code).casefold()
    if assessment.probable_fund_code is None:
        return [
            f"Unable to verify declared fund {declared!r} from non-option-code signals for the shared 24-column schema"
        ]
    if declared != assessment.probable_fund_code:
        return [
            "Declared fund "
            f"{declared!r} disagrees with source/domain/content signals favouring {assessment.probable_fund_code!r}"
        ]
    return []


def _normalise_text(value: str) -> str:
    return " ".join(value.strip().casefold().split())


def describe_probable_fund_owner(probable_fund_code: str | None) -> str | None:
    if probable_fund_code is None:
        return None
    return FRIENDLY_FUND_OWNER_LABELS.get(probable_fund_code, probable_fund_code)
