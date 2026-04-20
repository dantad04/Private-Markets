from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from sqlalchemy import select

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias, EntityMatchOverride, EntityResolutionQueue, Holding
from app.entity_resolution.exact_name import infer_holding_entity_type_scope


def upsert_entity_resolution_queue_item(
    session,
    *,
    holding_id: int,
    candidate_entity_ids: list[int],
    evidence_json: dict[str, object],
    top_candidate_score: Decimal = Decimal("1.0"),
) -> EntityResolutionQueue:
    candidate_ids = sorted({int(entity_id) for entity_id in candidate_entity_ids})
    queue_item = session.query(EntityResolutionQueue).filter(
        EntityResolutionQueue.holding_id == holding_id,
        EntityResolutionQueue.status == "open",
    ).one_or_none()
    if queue_item is None:
        queue_item = EntityResolutionQueue(
            holding_id=holding_id,
            candidate_entity_ids=candidate_ids,
            top_candidate_score=top_candidate_score,
            evidence_json=evidence_json,
            status="open",
        )
        session.add(queue_item)
    else:
        queue_item.candidate_entity_ids = candidate_ids
        queue_item.top_candidate_score = top_candidate_score
        queue_item.evidence_json = evidence_json
        queue_item.notes = None
    session.flush()
    return queue_item


def apply_entity_resolution_queue_action(
    session,
    *,
    queue_item_id: int,
    action: str,
    chosen_entity_id: int | None = None,
    resolved_by: str | None = None,
    notes: str | None = None,
) -> EntityResolutionQueue | None:
    queue_item = session.get(EntityResolutionQueue, queue_item_id)
    if queue_item is None:
        return None
    if queue_item.status != "open":
        raise ValueError(f"queue item {queue_item_id} is already {queue_item.status}")

    holding = session.get(Holding, queue_item.holding_id)
    if holding is None:
        raise ValueError(f"holding {queue_item.holding_id} no longer exists")

    resolved_at = datetime.now(UTC)
    resolved_by_value = resolved_by or "system"

    if action == "accept":
        if chosen_entity_id is None:
            raise ValueError("chosen_entity_id is required for accept")
        if chosen_entity_id not in {int(entity_id) for entity_id in queue_item.candidate_entity_ids}:
            raise ValueError("chosen_entity_id must be one of the queued candidates")
        holding.entity_id = chosen_entity_id
        _upsert_override_from_queue_resolution(
            session,
            holding=holding,
            action="force_match",
            matched_entity_id=chosen_entity_id,
            created_by=resolved_by_value,
            reason=_queue_override_reason(
                queue_item_id=queue_item.id,
                action="accept",
                notes=notes,
            ),
        )
        queue_item.status = "accepted"
    elif action == "reject":
        _upsert_override_from_queue_resolution(
            session,
            holding=holding,
            action="force_no_match",
            matched_entity_id=None,
            created_by=resolved_by_value,
            reason=_queue_override_reason(
                queue_item_id=queue_item.id,
                action="reject",
                notes=notes,
            ),
        )
        queue_item.status = "rejected"
    elif action == "create_new":
        if not holding.raw_name:
            raise ValueError("holding raw_name is required to create a new entity")
        entity = Entity(
            entity_type="company",
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
            is_preferred=True,
        )
        holding.entity_id = entity.id
        _upsert_override_from_queue_resolution(
            session,
            holding=holding,
            action="force_new_entity",
            matched_entity_id=entity.id,
            created_by=resolved_by_value,
            reason=_queue_override_reason(
                queue_item_id=queue_item.id,
                action="create_new",
                notes=notes,
            ),
        )
        queue_item.status = "created_new"
    else:
        raise ValueError("action must be 'accept', 'reject', or 'create_new'")

    queue_item.resolved_at = resolved_at
    queue_item.resolved_by = resolved_by_value
    queue_item.notes = notes
    session.flush()
    return queue_item


def _upsert_override_from_queue_resolution(
    session,
    *,
    holding: Holding,
    action: str,
    matched_entity_id: int | None,
    created_by: str,
    reason: str,
) -> EntityMatchOverride:
    if holding.raw_name is None or holding.raw_name.strip() == "":
        raise ValueError("holding raw_name is required to persist an entity resolution override")

    normalized_raw_name = normalise_name(holding.raw_name)
    entity_type_scope = infer_holding_entity_type_scope(holding)
    candidate_overrides = session.scalars(
        select(EntityMatchOverride).where(EntityMatchOverride.raw_name_normalized == normalized_raw_name)
    ).all()
    matching_overrides = [
        override
        for override in candidate_overrides
        if override.source_fund_id == holding.source_fund_id
        and override.source_asset_class_scope == holding.source_asset_class_raw
        and override.entity_type_scope == entity_type_scope
    ]
    if len(matching_overrides) > 1:
        raise ValueError(
            "Multiple entity_match_overrides rows already exist for the same queue-resolution scope "
            f"raw_name_normalized={normalized_raw_name!r}, source_fund_id={holding.source_fund_id}, "
            f"source_asset_class_scope={holding.source_asset_class_raw!r}, entity_type_scope={entity_type_scope!r}"
        )

    if matching_overrides:
        override = matching_overrides[0]
    else:
        override = EntityMatchOverride(
            raw_name_normalized=normalized_raw_name,
            entity_type_scope=entity_type_scope,
            source_fund_id=holding.source_fund_id,
            source_asset_class_scope=holding.source_asset_class_raw,
            matched_entity_id=matched_entity_id,
            action=action,
            reason=reason,
            created_by=created_by,
            expires_at=None,
        )
        session.add(override)

    override.action = action
    override.matched_entity_id = matched_entity_id
    override.reason = reason
    override.created_by = created_by
    override.expires_at = None
    session.flush()
    return override


def _ensure_entity_alias(
    session,
    *,
    entity_id: int,
    alias: str,
    source_file_id: int | None,
    is_preferred: bool,
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
            source_system="entity_resolution_queue",
            source_file_id=source_file_id,
            is_preferred=is_preferred,
            match_confidence=Decimal("1.0"),
        )
    )


def _queue_override_reason(
    *,
    queue_item_id: int,
    action: str,
    notes: str | None,
) -> str:
    base_reason = f"Entity resolution queue item {queue_item_id} action {action}."
    if notes is None or notes.strip() == "":
        return base_reason
    return f"{base_reason} Notes: {notes.strip()}"
