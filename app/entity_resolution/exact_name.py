from __future__ import annotations

from dataclasses import dataclass
from decimal import Decimal

from sqlalchemy import select
from sqlalchemy.orm import Session

from adapters.sunsuper_schema_normalisation import normalise_name
from app.db.models import Entity, EntityAlias, Holding


EXACT_NAME_CONFIDENCE_SCORE = Decimal("0.97000")


@dataclass(frozen=True)
class ExactNameCandidate:
    entity_id: int
    entity_type: str
    matched_names: tuple[str, ...]


@dataclass(frozen=True)
class ExactNameResolutionResult:
    matched_entity_id: int | None
    ambiguous_candidate_entity_ids: tuple[int, ...]
    rejected_candidate_entity_ids: tuple[int, ...]
    evidence_json: dict[str, object] | None


def build_exact_name_candidate_map(session: Session) -> dict[str, tuple[ExactNameCandidate, ...]]:
    candidate_map: dict[str, dict[int, dict[str, object]]] = {}

    entity_rows = session.execute(
        select(
            Entity.id,
            Entity.entity_type,
            Entity.canonical_name,
        )
    ).all()
    for entity_id, entity_type, canonical_name in entity_rows:
        _register_candidate_name(
            candidate_map,
            normalized_name=normalise_name(canonical_name),
            entity_id=int(entity_id),
            entity_type=entity_type,
            matched_name=canonical_name,
        )

    alias_rows = session.execute(
        select(
            EntityAlias.entity_id,
            Entity.entity_type,
            EntityAlias.alias_normalized,
            EntityAlias.alias,
        ).join(Entity, Entity.id == EntityAlias.entity_id)
    ).all()
    for entity_id, entity_type, alias_normalized, alias in alias_rows:
        _register_candidate_name(
            candidate_map,
            normalized_name=alias_normalized,
            entity_id=int(entity_id),
            entity_type=entity_type,
            matched_name=alias,
        )

    return {
        normalized_name: tuple(
            ExactNameCandidate(
                entity_id=entity_id,
                entity_type=str(candidate["entity_type"]),
                matched_names=tuple(sorted(str(name) for name in candidate["matched_names"])),
            )
            for entity_id, candidate in sorted(candidates.items())
        )
        for normalized_name, candidates in candidate_map.items()
    }


def resolve_exact_normalized_name_match(
    *,
    holding: Holding,
    candidate_map: dict[str, tuple[ExactNameCandidate, ...]],
) -> ExactNameResolutionResult:
    if holding.raw_name is None:
        return ExactNameResolutionResult(
            matched_entity_id=None,
            ambiguous_candidate_entity_ids=(),
            rejected_candidate_entity_ids=(),
            evidence_json=None,
        )

    normalized_raw_name = normalise_name(holding.raw_name)
    if normalized_raw_name == "":
        return ExactNameResolutionResult(
            matched_entity_id=None,
            ambiguous_candidate_entity_ids=(),
            rejected_candidate_entity_ids=(),
            evidence_json=None,
        )

    candidates = candidate_map.get(normalized_raw_name, ())
    if not candidates:
        return ExactNameResolutionResult(
            matched_entity_id=None,
            ambiguous_candidate_entity_ids=(),
            rejected_candidate_entity_ids=(),
            evidence_json=None,
        )

    holding_scope = infer_holding_entity_type_scope(holding)
    scoped_candidates: list[ExactNameCandidate] = []
    rejected_candidate_entity_ids: list[int] = []
    for candidate in candidates:
        if _candidate_matches_scope(candidate.entity_type, holding_scope):
            scoped_candidates.append(candidate)
        else:
            rejected_candidate_entity_ids.append(candidate.entity_id)

    unique_candidate_ids = tuple(sorted({candidate.entity_id for candidate in scoped_candidates}))
    unique_rejected_ids = tuple(sorted(set(rejected_candidate_entity_ids)))
    if not unique_candidate_ids:
        return ExactNameResolutionResult(
            matched_entity_id=None,
            ambiguous_candidate_entity_ids=(),
            rejected_candidate_entity_ids=unique_rejected_ids,
            evidence_json=None,
        )

    if len(unique_candidate_ids) == 1:
        return ExactNameResolutionResult(
            matched_entity_id=unique_candidate_ids[0],
            ambiguous_candidate_entity_ids=(),
            rejected_candidate_entity_ids=unique_rejected_ids,
            evidence_json=None,
        )

    return ExactNameResolutionResult(
        matched_entity_id=None,
        ambiguous_candidate_entity_ids=unique_candidate_ids,
        rejected_candidate_entity_ids=unique_rejected_ids,
        evidence_json={
            "ambiguity_kind": "exact_name",
            "match_method": "exact_normalized_name",
            "normalized_name": normalized_raw_name,
            "holding_entity_type_scope": holding_scope,
            "confidence_score": float(EXACT_NAME_CONFIDENCE_SCORE),
            "candidate_details": [
                {
                    "entity_id": candidate.entity_id,
                    "entity_type": candidate.entity_type,
                    "matched_names": list(candidate.matched_names),
                }
                for candidate in scoped_candidates
            ],
            "rejected_candidate_entity_ids": list(unique_rejected_ids),
        },
    )


def infer_holding_entity_type_scope(holding: Holding) -> str | None:
    if holding.manager_entity_id is not None:
        return "manager"
    if holding.issuer_entity_id is not None:
        return "company"
    # Ownership-bearing rows can truthfully name a company or a manager (the IFM
    # worked case is the canonical example), so do not hard-scope them from the
    # source subclass alone.
    if holding.ownership_pct is not None:
        return None

    normalized_subclass = _normalize_text(holding.source_subclass_raw)
    if normalized_subclass == "externally managed":
        return "manager"
    if normalized_subclass == "internally managed":
        return "company"

    normalized_classification = _normalize_text(holding.classification_raw)
    if normalized_classification is not None and "manager" in normalized_classification.split():
        return "manager"

    return None


def _candidate_matches_scope(entity_type: str, holding_scope: str | None) -> bool:
    if holding_scope is None:
        return True
    return entity_type == holding_scope


def _register_candidate_name(
    candidate_map: dict[str, dict[int, dict[str, object]]],
    *,
    normalized_name: str,
    entity_id: int,
    entity_type: str,
    matched_name: str,
) -> None:
    if normalized_name == "":
        return
    normalized_candidates = candidate_map.setdefault(normalized_name, {})
    candidate = normalized_candidates.setdefault(
        entity_id,
        {
            "entity_type": entity_type,
            "matched_names": set(),
        },
    )
    candidate["matched_names"].add(matched_name)


def _normalize_text(value: str | None) -> str | None:
    if value is None:
        return None
    normalized = " ".join(value.strip().casefold().split())
    if normalized == "":
        return None
    return normalized
