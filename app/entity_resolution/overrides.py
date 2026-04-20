from __future__ import annotations

from dataclasses import dataclass
from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias, EntityMatchOverride, Holding


FORCE_MATCH_ACTION = "force_match"
FORCE_NO_MATCH_ACTION = "force_no_match"
FORCE_NEW_ENTITY_ACTION = "force_new_entity"
REDIRECT_TO_PARENT_ACTION = "redirect_to_parent"
SUPPORTED_OVERRIDE_ACTIONS = {
    FORCE_MATCH_ACTION,
    FORCE_NO_MATCH_ACTION,
    FORCE_NEW_ENTITY_ACTION,
    REDIRECT_TO_PARENT_ACTION,
}
OVERRIDE_MATCH_CONFIDENCE = Decimal("1.0")
DEFAULT_FORCE_NEW_ENTITY_TYPE = "company"


@dataclass(frozen=True)
class AppliedEntityMatchOverride:
    override_id: int
    action: str
    entity_id: int | None
    created_new_entity: bool


def apply_entity_match_override(
    session: Session,
    *,
    holding: Holding,
) -> AppliedEntityMatchOverride | None:
    override = find_matching_entity_override(session, holding=holding)
    if override is None:
        return None

    if override.action == FORCE_MATCH_ACTION:
        target_entity = _require_override_target_entity(session, override)
        holding.entity_id = target_entity.id
        return AppliedEntityMatchOverride(
            override_id=override.id,
            action=override.action,
            entity_id=target_entity.id,
            created_new_entity=False,
        )

    if override.action == REDIRECT_TO_PARENT_ACTION:
        target_entity = _require_override_target_entity(session, override)
        holding.entity_id = target_entity.id
        return AppliedEntityMatchOverride(
            override_id=override.id,
            action=override.action,
            entity_id=target_entity.id,
            created_new_entity=False,
        )

    if override.action == FORCE_NO_MATCH_ACTION:
        holding.entity_id = None
        return AppliedEntityMatchOverride(
            override_id=override.id,
            action=override.action,
            entity_id=None,
            created_new_entity=False,
        )

    if override.action == FORCE_NEW_ENTITY_ACTION:
        entity_id, created_new_entity = _resolve_or_create_force_new_entity(
            session,
            holding=holding,
            override=override,
        )
        holding.entity_id = entity_id
        return AppliedEntityMatchOverride(
            override_id=override.id,
            action=override.action,
            entity_id=entity_id,
            created_new_entity=created_new_entity,
        )

    raise ValueError(f"Unsupported entity_match_overrides action {override.action!r}")


def find_matching_entity_override(session: Session, *, holding: Holding) -> EntityMatchOverride | None:
    if holding.raw_name is None:
        return None

    normalized_raw_name = normalise_name(holding.raw_name)
    if normalized_raw_name == "":
        return None

    explicit_holding_scope = _infer_explicit_holding_entity_type_scope(holding)
    candidate_overrides = session.scalars(
        select(EntityMatchOverride).where(EntityMatchOverride.raw_name_normalized == normalized_raw_name)
    ).all()

    ranked_candidates: list[tuple[int, EntityMatchOverride]] = []
    for override in candidate_overrides:
        specificity = _match_specificity_for_override(
            session,
            holding=holding,
            override=override,
            explicit_holding_scope=explicit_holding_scope,
        )
        if specificity is None:
            continue
        ranked_candidates.append((specificity, override))

    if not ranked_candidates:
        return None

    highest_specificity = max(score for score, _override in ranked_candidates)
    best_candidates = [override for score, override in ranked_candidates if score == highest_specificity]
    if len(best_candidates) > 1:
        raise ValueError(
            "Multiple equally specific entity_match_overrides matched "
            f"raw_name_normalized={normalized_raw_name!r} for holding_id={holding.id}"
        )
    return best_candidates[0]


def _match_specificity_for_override(
    session: Session,
    *,
    holding: Holding,
    override: EntityMatchOverride,
    explicit_holding_scope: str | None,
) -> int | None:
    if override.action not in SUPPORTED_OVERRIDE_ACTIONS:
        raise ValueError(f"Unsupported entity_match_overrides action {override.action!r}")
    if _is_override_expired(override):
        return None
    if override.source_fund_id is not None and override.source_fund_id != holding.source_fund_id:
        return None
    if (
        override.source_asset_class_scope is not None
        and override.source_asset_class_scope != holding.source_asset_class_raw
    ):
        return None

    target_entity = _get_override_target_entity_if_present(session, override)
    if override.entity_type_scope is not None:
        if explicit_holding_scope is not None and override.entity_type_scope != explicit_holding_scope:
            return None
        if target_entity is not None and target_entity.entity_type != override.entity_type_scope:
            raise ValueError(
                "entity_match_overrides.entity_type_scope must match the matched entity type when matched_entity_id is set"
            )

    specificity = 0
    if override.source_fund_id is not None:
        specificity += 1
    if override.source_asset_class_scope is not None:
        specificity += 1
    if override.entity_type_scope is not None and (
        explicit_holding_scope == override.entity_type_scope
        or target_entity is not None
    ):
        specificity += 1
    return specificity


def _is_override_expired(override: EntityMatchOverride) -> bool:
    if override.expires_at is None:
        return False
    if override.expires_at.tzinfo is None:
        return override.expires_at <= datetime.now()
    return override.expires_at <= datetime.now(UTC)


def _infer_explicit_holding_entity_type_scope(holding: Holding) -> str | None:
    if holding.issuer_entity_id is not None:
        return "issuer"
    if holding.manager_entity_id is not None:
        return "manager"
    return None


def _get_override_target_entity_if_present(session: Session, override: EntityMatchOverride) -> Entity | None:
    if override.matched_entity_id is None:
        return None
    target_entity = session.get(Entity, override.matched_entity_id)
    if target_entity is None:
        raise ValueError(
            f"entity_match_overrides row {override.id} references missing entity {override.matched_entity_id}"
        )
    return target_entity


def _require_override_target_entity(session: Session, override: EntityMatchOverride) -> Entity:
    target_entity = _get_override_target_entity_if_present(session, override)
    if target_entity is None:
        raise ValueError(
            f"entity_match_overrides row {override.id} requires matched_entity_id for action {override.action}"
        )
    return target_entity


def _resolve_or_create_force_new_entity(
    session: Session,
    *,
    holding: Holding,
    override: EntityMatchOverride,
) -> tuple[int, bool]:
    target_entity = _get_override_target_entity_if_present(session, override)
    if target_entity is not None:
        _ensure_entity_alias(
            session,
            entity_id=target_entity.id,
            alias=holding.raw_name,
            source_file_id=holding.source_file_id,
        )
        return target_entity.id, False

    if holding.raw_name is None or holding.raw_name.strip() == "":
        raise ValueError("holding raw_name is required for force_new_entity")

    entity = Entity(
        entity_type=override.entity_type_scope or DEFAULT_FORCE_NEW_ENTITY_TYPE,
        canonical_name=holding.raw_name,
        abn=None,
    )
    session.add(entity)
    session.flush()

    _ensure_entity_alias(
        session,
        entity_id=entity.id,
        alias=holding.raw_name,
        source_file_id=holding.source_file_id,
    )
    override.matched_entity_id = entity.id
    session.flush()
    return entity.id, True


def _ensure_entity_alias(
    session: Session,
    *,
    entity_id: int,
    alias: str,
    source_file_id: int | None,
) -> None:
    existing_alias = session.scalar(
        select(EntityAlias).where(
            EntityAlias.entity_id == entity_id,
            EntityAlias.alias == alias,
        )
    )
    if existing_alias is not None:
        return

    session.add(
        EntityAlias(
            entity_id=entity_id,
            alias=alias,
            alias_normalized=normalise_name(alias),
            source_system="entity_match_overrides",
            source_file_id=source_file_id,
            is_preferred=True,
            match_confidence=OVERRIDE_MATCH_CONFIDENCE,
        )
    )
    session.flush()
