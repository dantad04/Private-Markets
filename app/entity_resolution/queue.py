from __future__ import annotations

from datetime import UTC, datetime
from decimal import Decimal

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias, EntityResolutionQueue, Holding


def upsert_entity_resolution_queue_item(
    session,
    *,
    holding_id: int,
    candidate_entity_ids: list[int],
    evidence_json: dict[str, object],
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
            top_candidate_score=Decimal("1.0"),
            evidence_json=evidence_json,
            status="open",
        )
        session.add(queue_item)
    else:
        queue_item.candidate_entity_ids = candidate_ids
        queue_item.top_candidate_score = Decimal("1.0")
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
        queue_item.status = "accepted"
    elif action == "reject":
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
        session.add(
            EntityAlias(
                entity_id=entity.id,
                alias=holding.raw_name,
                alias_normalized=normalise_name(holding.raw_name),
                source_system="entity_resolution_queue",
                source_file_id=holding.source_file_id,
                is_preferred=True,
                match_confidence=Decimal("1.0"),
            )
        )
        holding.entity_id = entity.id
        queue_item.status = "created_new"
    else:
        raise ValueError("action must be 'accept', 'reject', or 'create_new'")

    queue_item.resolved_at = resolved_at
    queue_item.resolved_by = resolved_by_value
    queue_item.notes = notes
    session.flush()
    return queue_item
