from __future__ import annotations

from dataclasses import dataclass
from datetime import date

from sqlalchemy import select

from app.db.models import Entity
from app.entity_resolution.brandon_capital_partners_seed import (
    BRANDON_CAPITAL_PARTNERS_CANONICAL_NAME,
    BRANDON_CAPITAL_PARTNERS_REGISTERED_NAME_ON_ABR,
    BRANDON_CAPITAL_PARTNERS_REVIEWED_ABN,
    ensure_brandon_capital_partners_seed,
)
from app.entity_resolution.alphinity_investment_management_seed import (
    ALPHINITY_INVESTMENT_MANAGEMENT_CANONICAL_NAME,
    ALPHINITY_INVESTMENT_MANAGEMENT_REGISTERED_NAME_ON_ABR,
    ALPHINITY_INVESTMENT_MANAGEMENT_REVIEWED_ABN,
    ensure_alphinity_investment_management_seed,
)
from app.entity_resolution.bgh_capital_seed import (
    BGH_CAPITAL_CANONICAL_NAME,
    BGH_CAPITAL_REGISTERED_NAME_ON_ABR,
    BGH_CAPITAL_REVIEWED_ABN,
    ensure_bgh_capital_seed,
)
from app.entity_resolution.bentham_asset_management_seed import (
    BENTHAM_ASSET_MANAGEMENT_CANONICAL_NAME,
    BENTHAM_ASSET_MANAGEMENT_REGISTERED_NAME_ON_ABR,
    BENTHAM_ASSET_MANAGEMENT_REVIEWED_ABN,
    ensure_bentham_asset_management_seed,
)
from app.entity_resolution.blackbird_ventures_seed import (
    BLACKBIRD_VENTURES_CANONICAL_NAME,
    BLACKBIRD_VENTURES_REGISTERED_NAME_ON_ABR,
    BLACKBIRD_VENTURES_REVIEWED_ABN,
    ensure_blackbird_ventures_seed,
)
from app.entity_resolution.catalyst_investment_managers_seed import (
    CATALYST_INVESTMENT_MANAGERS_CANONICAL_NAME,
    CATALYST_INVESTMENT_MANAGERS_REGISTERED_NAME_ON_ABR,
    CATALYST_INVESTMENT_MANAGERS_REVIEWED_ABN,
    ensure_catalyst_investment_managers_seed,
)
from app.entity_resolution.deterministic import normalise_abn
from app.entity_resolution.industry_super_holdings_seed import (
    INDUSTRY_SUPER_HOLDINGS_CANONICAL_NAME,
    INDUSTRY_SUPER_HOLDINGS_REGISTERED_NAME_ON_ABR,
    INDUSTRY_SUPER_HOLDINGS_REVIEWED_ABN,
    ensure_industry_super_holdings_seed,
)
from app.entity_resolution.myriota_seed import (
    MYRIOTA_CANONICAL_NAME,
    ensure_myriota_seed,
)
from app.entity_resolution.roc_capital_seed import (
    ROC_CAPITAL_CANONICAL_NAME,
    ROC_CAPITAL_REGISTERED_NAME_ON_ABR,
    ROC_CAPITAL_REVIEWED_ABN,
    ensure_roc_capital_seed,
)
from app.entity_resolution.stafford_capital_partners_seed import (
    STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME,
    STAFFORD_CAPITAL_PARTNERS_REGISTERED_NAME_ON_ABR,
    STAFFORD_CAPITAL_PARTNERS_REVIEWED_ABN,
    ensure_stafford_capital_partners_seed,
)
from app.entity_resolution.square_peg_capital_seed import (
    SQUARE_PEG_CAPITAL_CANONICAL_NAME,
    SQUARE_PEG_CAPITAL_REGISTERED_NAME_ON_ABR,
    SQUARE_PEG_CAPITAL_REVIEWED_ABN,
    ensure_square_peg_capital_seed,
)
from app.entity_resolution.wellington_management_australia_seed import (
    WELLINGTON_MANAGEMENT_AUSTRALIA_CANONICAL_NAME,
    WELLINGTON_MANAGEMENT_AUSTRALIA_REGISTERED_NAME_ON_ABR,
    WELLINGTON_MANAGEMENT_AUSTRALIA_REVIEWED_ABN,
    ensure_wellington_management_australia_seed,
)


ASIC_COMPANY_STATUS_REGISTERED = "Registered"
ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES = "Australian Proprietary Company, Limited By Shares"
ASIC_REVIEW_SOURCE = "current ASIC company summary public record; exact record details supplied in-turn by user"
ASIC_REVIEWED_BY = "user+codex"
ASIC_REVIEWED_AT = date(2026, 4, 23)

BRANDON_CAPITAL_PARTNERS_ACN = "128 415 903"
BRANDON_CAPITAL_PARTNERS_ASIC_REGISTRATION_DATE = date(2007, 11, 12)
BRANDON_CAPITAL_PARTNERS_ASIC_NEXT_REVIEW_DATE = date(2026, 11, 12)

STAFFORD_CAPITAL_PARTNERS_ACN = "094 669 940"
STAFFORD_CAPITAL_PARTNERS_ASIC_REGISTRATION_DATE = date(2000, 10, 5)
STAFFORD_CAPITAL_PARTNERS_ASIC_NEXT_REVIEW_DATE = date(2026, 10, 5)

CATALYST_INVESTMENT_MANAGERS_ACN = "118 410 101"
CATALYST_INVESTMENT_MANAGERS_ASIC_REGISTRATION_DATE = date(2006, 2, 17)
CATALYST_INVESTMENT_MANAGERS_ASIC_NEXT_REVIEW_DATE = date(2027, 2, 17)

INDUSTRY_SUPER_HOLDINGS_ACN = "119 748 060"
INDUSTRY_SUPER_HOLDINGS_ASIC_REGISTRATION_DATE = date(2006, 5, 17)
INDUSTRY_SUPER_HOLDINGS_ASIC_NEXT_REVIEW_DATE = date(2026, 5, 17)

WELLINGTON_MANAGEMENT_AUSTRALIA_ACN = "167 091 090"
WELLINGTON_MANAGEMENT_AUSTRALIA_ASIC_REGISTRATION_DATE = date(2014, 6, 3)
WELLINGTON_MANAGEMENT_AUSTRALIA_ASIC_NEXT_REVIEW_DATE = date(2026, 6, 3)

ROC_CAPITAL_ACN = "167 858 764"
ROC_CAPITAL_ASIC_REGISTRATION_DATE = date(2014, 3, 5)
ROC_CAPITAL_ASIC_NEXT_REVIEW_DATE = date(2027, 3, 5)

ALPHINITY_INVESTMENT_MANAGEMENT_ACN = "140 833 709"
ALPHINITY_INVESTMENT_MANAGEMENT_ASIC_REGISTRATION_DATE = date(2009, 11, 30)
ALPHINITY_INVESTMENT_MANAGEMENT_ASIC_NEXT_REVIEW_DATE = date(2026, 11, 30)

BENTHAM_ASSET_MANAGEMENT_ACN = "140 833 674"
BENTHAM_ASSET_MANAGEMENT_ASIC_REGISTRATION_DATE = date(2009, 11, 30)
BENTHAM_ASSET_MANAGEMENT_ASIC_NEXT_REVIEW_DATE = date(2026, 11, 30)

BLACKBIRD_VENTURES_ACN = "159 044 989"
BLACKBIRD_VENTURES_ASIC_REGISTRATION_DATE = date(2012, 6, 19)
BLACKBIRD_VENTURES_ASIC_NEXT_REVIEW_DATE = date(2026, 7, 2)

SQUARE_PEG_CAPITAL_ACN = "164 352 229"
SQUARE_PEG_CAPITAL_ASIC_REGISTRATION_DATE = date(2013, 7, 29)
SQUARE_PEG_CAPITAL_ASIC_NEXT_REVIEW_DATE = date(2026, 9, 28)

BGH_CAPITAL_ACN = "617 386 982"
BGH_CAPITAL_ASIC_REGISTRATION_DATE = date(2017, 2, 14)
BGH_CAPITAL_ASIC_NEXT_REVIEW_DATE = date(2027, 2, 14)

MYRIOTA_ABN = "65 609 161 373"
MYRIOTA_ACN = "609 161 373"
MYRIOTA_ASIC_REGISTRATION_DATE = date(2015, 11, 6)
MYRIOTA_ASIC_NEXT_REVIEW_DATE = date(2026, 11, 6)


@dataclass(frozen=True)
class AsicCompanyRegisterCrossReference:
    canonical_name: str
    entity_type: str
    reviewed_abn: str
    registered_name: str | None
    acn: str
    registration_date: date
    next_review_date: date

    @property
    def record_url(self) -> str:
        return (
            "https://connectonline.asic.gov.au/RegistrySearch/faces/landing/"
            f"panelSearch.jspx?searchType=OrgAndBusNm&searchText={''.join(ch for ch in self.acn if ch.isdigit())}"
        )


BRANDON_CAPITAL_PARTNERS_ASIC_CROSS_REFERENCE = AsicCompanyRegisterCrossReference(
    canonical_name=BRANDON_CAPITAL_PARTNERS_CANONICAL_NAME,
    entity_type="manager",
    reviewed_abn=BRANDON_CAPITAL_PARTNERS_REVIEWED_ABN,
    registered_name=BRANDON_CAPITAL_PARTNERS_REGISTERED_NAME_ON_ABR,
    acn=BRANDON_CAPITAL_PARTNERS_ACN,
    registration_date=BRANDON_CAPITAL_PARTNERS_ASIC_REGISTRATION_DATE,
    next_review_date=BRANDON_CAPITAL_PARTNERS_ASIC_NEXT_REVIEW_DATE,
)

STAFFORD_CAPITAL_PARTNERS_ASIC_CROSS_REFERENCE = AsicCompanyRegisterCrossReference(
    canonical_name=STAFFORD_CAPITAL_PARTNERS_CANONICAL_NAME,
    entity_type="manager",
    reviewed_abn=STAFFORD_CAPITAL_PARTNERS_REVIEWED_ABN,
    registered_name=STAFFORD_CAPITAL_PARTNERS_REGISTERED_NAME_ON_ABR,
    acn=STAFFORD_CAPITAL_PARTNERS_ACN,
    registration_date=STAFFORD_CAPITAL_PARTNERS_ASIC_REGISTRATION_DATE,
    next_review_date=STAFFORD_CAPITAL_PARTNERS_ASIC_NEXT_REVIEW_DATE,
)

CATALYST_INVESTMENT_MANAGERS_ASIC_CROSS_REFERENCE = AsicCompanyRegisterCrossReference(
    canonical_name=CATALYST_INVESTMENT_MANAGERS_CANONICAL_NAME,
    entity_type="manager",
    reviewed_abn=CATALYST_INVESTMENT_MANAGERS_REVIEWED_ABN,
    registered_name=CATALYST_INVESTMENT_MANAGERS_REGISTERED_NAME_ON_ABR,
    acn=CATALYST_INVESTMENT_MANAGERS_ACN,
    registration_date=CATALYST_INVESTMENT_MANAGERS_ASIC_REGISTRATION_DATE,
    next_review_date=CATALYST_INVESTMENT_MANAGERS_ASIC_NEXT_REVIEW_DATE,
)

INDUSTRY_SUPER_HOLDINGS_ASIC_CROSS_REFERENCE = AsicCompanyRegisterCrossReference(
    canonical_name=INDUSTRY_SUPER_HOLDINGS_CANONICAL_NAME,
    entity_type="company",
    reviewed_abn=INDUSTRY_SUPER_HOLDINGS_REVIEWED_ABN,
    registered_name=INDUSTRY_SUPER_HOLDINGS_REGISTERED_NAME_ON_ABR,
    acn=INDUSTRY_SUPER_HOLDINGS_ACN,
    registration_date=INDUSTRY_SUPER_HOLDINGS_ASIC_REGISTRATION_DATE,
    next_review_date=INDUSTRY_SUPER_HOLDINGS_ASIC_NEXT_REVIEW_DATE,
)

WELLINGTON_MANAGEMENT_AUSTRALIA_ASIC_CROSS_REFERENCE = AsicCompanyRegisterCrossReference(
    canonical_name=WELLINGTON_MANAGEMENT_AUSTRALIA_CANONICAL_NAME,
    entity_type="manager",
    reviewed_abn=WELLINGTON_MANAGEMENT_AUSTRALIA_REVIEWED_ABN,
    registered_name=WELLINGTON_MANAGEMENT_AUSTRALIA_REGISTERED_NAME_ON_ABR,
    acn=WELLINGTON_MANAGEMENT_AUSTRALIA_ACN,
    registration_date=WELLINGTON_MANAGEMENT_AUSTRALIA_ASIC_REGISTRATION_DATE,
    next_review_date=WELLINGTON_MANAGEMENT_AUSTRALIA_ASIC_NEXT_REVIEW_DATE,
)

ROC_CAPITAL_ASIC_CROSS_REFERENCE = AsicCompanyRegisterCrossReference(
    canonical_name=ROC_CAPITAL_CANONICAL_NAME,
    entity_type="manager",
    reviewed_abn=ROC_CAPITAL_REVIEWED_ABN,
    registered_name=ROC_CAPITAL_REGISTERED_NAME_ON_ABR,
    acn=ROC_CAPITAL_ACN,
    registration_date=ROC_CAPITAL_ASIC_REGISTRATION_DATE,
    next_review_date=ROC_CAPITAL_ASIC_NEXT_REVIEW_DATE,
)

ALPHINITY_INVESTMENT_MANAGEMENT_ASIC_CROSS_REFERENCE = AsicCompanyRegisterCrossReference(
    canonical_name=ALPHINITY_INVESTMENT_MANAGEMENT_CANONICAL_NAME,
    entity_type="manager",
    reviewed_abn=ALPHINITY_INVESTMENT_MANAGEMENT_REVIEWED_ABN,
    registered_name=ALPHINITY_INVESTMENT_MANAGEMENT_REGISTERED_NAME_ON_ABR,
    acn=ALPHINITY_INVESTMENT_MANAGEMENT_ACN,
    registration_date=ALPHINITY_INVESTMENT_MANAGEMENT_ASIC_REGISTRATION_DATE,
    next_review_date=ALPHINITY_INVESTMENT_MANAGEMENT_ASIC_NEXT_REVIEW_DATE,
)

BENTHAM_ASSET_MANAGEMENT_ASIC_CROSS_REFERENCE = AsicCompanyRegisterCrossReference(
    canonical_name=BENTHAM_ASSET_MANAGEMENT_CANONICAL_NAME,
    entity_type="manager",
    reviewed_abn=BENTHAM_ASSET_MANAGEMENT_REVIEWED_ABN,
    registered_name=BENTHAM_ASSET_MANAGEMENT_REGISTERED_NAME_ON_ABR,
    acn=BENTHAM_ASSET_MANAGEMENT_ACN,
    registration_date=BENTHAM_ASSET_MANAGEMENT_ASIC_REGISTRATION_DATE,
    next_review_date=BENTHAM_ASSET_MANAGEMENT_ASIC_NEXT_REVIEW_DATE,
)

BLACKBIRD_VENTURES_ASIC_CROSS_REFERENCE = AsicCompanyRegisterCrossReference(
    canonical_name=BLACKBIRD_VENTURES_CANONICAL_NAME,
    entity_type="manager",
    reviewed_abn=BLACKBIRD_VENTURES_REVIEWED_ABN,
    registered_name=BLACKBIRD_VENTURES_REGISTERED_NAME_ON_ABR,
    acn=BLACKBIRD_VENTURES_ACN,
    registration_date=BLACKBIRD_VENTURES_ASIC_REGISTRATION_DATE,
    next_review_date=BLACKBIRD_VENTURES_ASIC_NEXT_REVIEW_DATE,
)

SQUARE_PEG_CAPITAL_ASIC_CROSS_REFERENCE = AsicCompanyRegisterCrossReference(
    canonical_name=SQUARE_PEG_CAPITAL_CANONICAL_NAME,
    entity_type="manager",
    reviewed_abn=SQUARE_PEG_CAPITAL_REVIEWED_ABN,
    registered_name=SQUARE_PEG_CAPITAL_REGISTERED_NAME_ON_ABR,
    acn=SQUARE_PEG_CAPITAL_ACN,
    registration_date=SQUARE_PEG_CAPITAL_ASIC_REGISTRATION_DATE,
    next_review_date=SQUARE_PEG_CAPITAL_ASIC_NEXT_REVIEW_DATE,
)

BGH_CAPITAL_ASIC_CROSS_REFERENCE = AsicCompanyRegisterCrossReference(
    canonical_name=BGH_CAPITAL_CANONICAL_NAME,
    entity_type="manager",
    reviewed_abn=BGH_CAPITAL_REVIEWED_ABN,
    registered_name=BGH_CAPITAL_REGISTERED_NAME_ON_ABR,
    acn=BGH_CAPITAL_ACN,
    registration_date=BGH_CAPITAL_ASIC_REGISTRATION_DATE,
    next_review_date=BGH_CAPITAL_ASIC_NEXT_REVIEW_DATE,
)

MYRIOTA_ASIC_CROSS_REFERENCE = AsicCompanyRegisterCrossReference(
    canonical_name=MYRIOTA_CANONICAL_NAME,
    entity_type="company",
    reviewed_abn=MYRIOTA_ABN,
    registered_name=None,
    acn=MYRIOTA_ACN,
    registration_date=MYRIOTA_ASIC_REGISTRATION_DATE,
    next_review_date=MYRIOTA_ASIC_NEXT_REVIEW_DATE,
)


def ensure_private_entity_asic_company_register_cross_reference_subset(session) -> tuple[Entity, ...]:
    ensure_brandon_capital_partners_seed(session)
    ensure_stafford_capital_partners_seed(session)
    ensure_catalyst_investment_managers_seed(session)
    ensure_industry_super_holdings_seed(session)

    return (
        ensure_brandon_capital_partners_asic_company_register_cross_reference(session),
        ensure_stafford_capital_partners_asic_company_register_cross_reference(session),
        ensure_catalyst_investment_managers_asic_company_register_cross_reference(session),
        ensure_industry_super_holdings_asic_company_register_cross_reference(session),
    )


def ensure_wellington_roc_asic_company_register_cross_reference_subset(session) -> tuple[Entity, ...]:
    ensure_wellington_management_australia_seed(session)
    ensure_roc_capital_seed(session)

    return (
        ensure_wellington_management_australia_asic_company_register_cross_reference(session),
        ensure_roc_capital_asic_company_register_cross_reference(session),
    )


def ensure_alphinity_bentham_asic_company_register_cross_reference_subset(session) -> tuple[Entity, ...]:
    ensure_alphinity_investment_management_seed(session)
    ensure_bentham_asset_management_seed(session)

    return (
        ensure_alphinity_investment_management_asic_company_register_cross_reference(session),
        ensure_bentham_asset_management_asic_company_register_cross_reference(session),
    )


def ensure_blackbird_square_peg_asic_company_register_cross_reference_subset(session) -> tuple[Entity, ...]:
    ensure_blackbird_ventures_seed(session)
    ensure_square_peg_capital_seed(session)

    return (
        ensure_blackbird_ventures_asic_company_register_cross_reference(session),
        ensure_square_peg_capital_asic_company_register_cross_reference(session),
    )


def ensure_bgh_capital_asic_company_register_cross_reference_subset(session) -> tuple[Entity, ...]:
    ensure_bgh_capital_seed(session)

    return (ensure_bgh_capital_asic_company_register_cross_reference(session),)


def ensure_myriota_asic_company_register_cross_reference_subset(session) -> tuple[Entity, ...]:
    ensure_myriota_seed(session)

    return (ensure_myriota_asic_company_register_cross_reference(session),)


def ensure_brandon_capital_partners_asic_company_register_cross_reference(session) -> Entity:
    return _ensure_entity_asic_company_register_cross_reference(
        session,
        cross_reference=BRANDON_CAPITAL_PARTNERS_ASIC_CROSS_REFERENCE,
    )


def ensure_stafford_capital_partners_asic_company_register_cross_reference(session) -> Entity:
    return _ensure_entity_asic_company_register_cross_reference(
        session,
        cross_reference=STAFFORD_CAPITAL_PARTNERS_ASIC_CROSS_REFERENCE,
    )


def ensure_catalyst_investment_managers_asic_company_register_cross_reference(session) -> Entity:
    return _ensure_entity_asic_company_register_cross_reference(
        session,
        cross_reference=CATALYST_INVESTMENT_MANAGERS_ASIC_CROSS_REFERENCE,
    )


def ensure_industry_super_holdings_asic_company_register_cross_reference(session) -> Entity:
    return _ensure_entity_asic_company_register_cross_reference(
        session,
        cross_reference=INDUSTRY_SUPER_HOLDINGS_ASIC_CROSS_REFERENCE,
    )


def ensure_wellington_management_australia_asic_company_register_cross_reference(session) -> Entity:
    return _ensure_entity_asic_company_register_cross_reference(
        session,
        cross_reference=WELLINGTON_MANAGEMENT_AUSTRALIA_ASIC_CROSS_REFERENCE,
    )


def ensure_roc_capital_asic_company_register_cross_reference(session) -> Entity:
    return _ensure_entity_asic_company_register_cross_reference(
        session,
        cross_reference=ROC_CAPITAL_ASIC_CROSS_REFERENCE,
    )


def ensure_alphinity_investment_management_asic_company_register_cross_reference(session) -> Entity:
    return _ensure_entity_asic_company_register_cross_reference(
        session,
        cross_reference=ALPHINITY_INVESTMENT_MANAGEMENT_ASIC_CROSS_REFERENCE,
    )


def ensure_bentham_asset_management_asic_company_register_cross_reference(session) -> Entity:
    return _ensure_entity_asic_company_register_cross_reference(
        session,
        cross_reference=BENTHAM_ASSET_MANAGEMENT_ASIC_CROSS_REFERENCE,
    )


def ensure_blackbird_ventures_asic_company_register_cross_reference(session) -> Entity:
    return _ensure_entity_asic_company_register_cross_reference(
        session,
        cross_reference=BLACKBIRD_VENTURES_ASIC_CROSS_REFERENCE,
    )


def ensure_square_peg_capital_asic_company_register_cross_reference(session) -> Entity:
    return _ensure_entity_asic_company_register_cross_reference(
        session,
        cross_reference=SQUARE_PEG_CAPITAL_ASIC_CROSS_REFERENCE,
    )


def ensure_bgh_capital_asic_company_register_cross_reference(session) -> Entity:
    return _ensure_entity_asic_company_register_cross_reference(
        session,
        cross_reference=BGH_CAPITAL_ASIC_CROSS_REFERENCE,
    )


def ensure_myriota_asic_company_register_cross_reference(session) -> Entity:
    return _ensure_entity_asic_company_register_cross_reference(
        session,
        cross_reference=MYRIOTA_ASIC_CROSS_REFERENCE,
    )


def _ensure_entity_asic_company_register_cross_reference(
    session,
    *,
    cross_reference: AsicCompanyRegisterCrossReference,
) -> Entity:
    entity = session.scalar(
        select(Entity).where(
            Entity.canonical_name == cross_reference.canonical_name,
        )
    )
    if entity is None:
        raise ValueError(
            f"Canonical entity {cross_reference.canonical_name!r} has not been seeded yet"
        )
    if entity.entity_type != cross_reference.entity_type:
        raise ValueError(
            f"Canonical entity {cross_reference.canonical_name!r} already exists with a conflicting entity_type "
            f"({entity.entity_type!r}); expected {cross_reference.entity_type!r}"
        )
    if normalise_abn(entity.abn) not in {None, normalise_abn(cross_reference.reviewed_abn)}:
        raise ValueError(
            f"Canonical entity {cross_reference.canonical_name!r} already has a conflicting reviewed ABN "
            f"({entity.abn!r}); expected {cross_reference.reviewed_abn!r}"
        )
    if cross_reference.registered_name is not None and entity.registered_name_on_abr not in {
        None,
        cross_reference.registered_name,
    }:
        raise ValueError(
            f"Canonical entity {cross_reference.canonical_name!r} already has conflicting registered-name "
            f"provenance ({entity.registered_name_on_abr!r}); expected {cross_reference.registered_name!r}"
        )
    if entity.is_australian_entity is False:
        raise ValueError(
            f"Canonical entity {cross_reference.canonical_name!r} is marked non-Australian despite ASIC "
            "company registration"
        )

    _ensure_matching_or_fill(entity=entity, attribute_name="abn", expected_value=cross_reference.reviewed_abn)
    _ensure_matching_or_fill(entity=entity, attribute_name="acn", expected_value=cross_reference.acn)
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="asic_company_status",
        expected_value=ASIC_COMPANY_STATUS_REGISTERED,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="asic_company_type",
        expected_value=ASIC_COMPANY_TYPE_PROPRIETARY_LIMITED_BY_SHARES,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="asic_registration_date",
        expected_value=cross_reference.registration_date,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="asic_next_review_date",
        expected_value=cross_reference.next_review_date,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="asic_record_url",
        expected_value=cross_reference.record_url,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="asic_review_source",
        expected_value=ASIC_REVIEW_SOURCE,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="asic_reviewed_by",
        expected_value=ASIC_REVIEWED_BY,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="asic_reviewed_at",
        expected_value=ASIC_REVIEWED_AT,
    )

    if entity.country_code in {None, ""}:
        entity.country_code = "AU"
    if entity.is_australian_entity is None:
        entity.is_australian_entity = True

    session.flush()
    return entity


def _ensure_matching_or_fill(entity: Entity, *, attribute_name: str, expected_value: object) -> None:
    existing_value = getattr(entity, attribute_name)
    if existing_value is None:
        setattr(entity, attribute_name, expected_value)
        return
    if existing_value != expected_value:
        raise ValueError(
            f"Canonical entity {entity.canonical_name!r} already has conflicting {attribute_name} "
            f"({existing_value!r}); expected {expected_value!r}"
        )
