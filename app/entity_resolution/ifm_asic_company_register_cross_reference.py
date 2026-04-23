from __future__ import annotations

from datetime import date

from sqlalchemy import select

from app.db.models import Entity
from app.entity_resolution.deterministic import normalise_abn
from app.entity_resolution.ifm_seed import IFM_CANONICAL_NAME, IFM_REVIEWED_ABN


IFM_ASIC_RECORD_URL = (
    "https://connectonline.asic.gov.au/RegistrySearch/faces/landing/"
    "panelSearch.jspx?searchType=OrgAndBusNm&searchText=107247727"
)
IFM_ASIC_REVIEW_SOURCE = (
    "current ASIC Connect company register public record; exact record details supplied in-turn by user"
)
IFM_ASIC_REVIEWED_BY = "user+codex"
IFM_ASIC_REVIEWED_AT = date(2026, 4, 23)
IFM_ACN = "107 247 727"
IFM_ASIC_COMPANY_STATUS = "Registered"
IFM_ASIC_COMPANY_TYPE = "Australian Proprietary Company, Limited By Shares"
IFM_ASIC_REGISTRATION_DATE = date(2003, 12, 18)
IFM_ASIC_NEXT_REVIEW_DATE = date(2026, 5, 17)


def ensure_ifm_asic_company_register_cross_reference(session) -> Entity:
    entity = session.scalar(
        select(Entity).where(
            Entity.canonical_name == IFM_CANONICAL_NAME,
        )
    )
    if entity is None:
        raise ValueError("Canonical IFM entity has not been seeded yet")
    if entity.entity_type != "manager":
        raise ValueError(
            "Canonical IFM entity already exists with a conflicting entity_type "
            f"({entity.entity_type!r}); expected 'manager'"
        )
    if normalise_abn(entity.abn) not in {None, normalise_abn(IFM_REVIEWED_ABN)}:
        raise ValueError(
            "Canonical IFM entity already has a conflicting reviewed ABN "
            f"({entity.abn!r}); expected {IFM_REVIEWED_ABN!r}"
        )
    if entity.is_australian_entity is False:
        raise ValueError("Canonical IFM entity is marked non-Australian despite ASIC company registration")

    _ensure_matching_or_fill(entity=entity, attribute_name="acn", expected_value=IFM_ACN)
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="asic_company_status",
        expected_value=IFM_ASIC_COMPANY_STATUS,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="asic_company_type",
        expected_value=IFM_ASIC_COMPANY_TYPE,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="asic_registration_date",
        expected_value=IFM_ASIC_REGISTRATION_DATE,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="asic_next_review_date",
        expected_value=IFM_ASIC_NEXT_REVIEW_DATE,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="asic_record_url",
        expected_value=IFM_ASIC_RECORD_URL,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="asic_review_source",
        expected_value=IFM_ASIC_REVIEW_SOURCE,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="asic_reviewed_by",
        expected_value=IFM_ASIC_REVIEWED_BY,
    )
    _ensure_matching_or_fill(
        entity=entity,
        attribute_name="asic_reviewed_at",
        expected_value=IFM_ASIC_REVIEWED_AT,
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
            f"Canonical IFM entity already has conflicting {attribute_name} "
            f"({existing_value!r}); expected {expected_value!r}"
        )
