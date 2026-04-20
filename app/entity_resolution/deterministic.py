from __future__ import annotations

from dataclasses import dataclass

from sqlalchemy import select
from sqlalchemy.orm import Session

from app.db.models import Entity, EntitySecurityIdentifier, Holding
from app.entity_resolution.exact_name import (
    EXACT_NAME_CONFIDENCE_SCORE,
    build_exact_name_candidate_map,
    resolve_exact_normalized_name_match,
)
from app.entity_resolution.overrides import (
    FORCE_MATCH_ACTION,
    FORCE_NEW_ENTITY_ACTION,
    FORCE_NO_MATCH_ACTION,
    REDIRECT_TO_PARENT_ACTION,
    apply_entity_match_override,
)
from app.entity_resolution.queue import upsert_entity_resolution_queue_item


SUPPORTED_SECURITY_IDENTIFIER_TYPES = {"ASX", "ISIN", "CUSIP", "LEI"}
ABN_IDENTIFIER_TYPE = "ABN"
DETERMINISTIC_CONFIDENCE_SCORE = 1.0


@dataclass(frozen=True)
class DeterministicResolutionSummary:
    reporting_period_id: int
    holdings_scanned: int
    holdings_skipped_prelinked: int
    abn_matches: int
    security_identifier_matches: int
    unresolved_abn: int
    unresolved_security_identifier: int
    ambiguous_abn: int
    ambiguous_security_identifier: int
    force_match_applications: int
    force_no_match_suppressions: int
    force_new_entity_creations: int
    redirect_to_parent_applications: int
    exact_name_auto_links: int
    exact_name_ambiguities_queued: int
    exact_name_candidates_rejected_due_to_scope_conflict: int
    unresolved_rows_remaining: int

    @property
    def total_matches(self) -> int:
        return self.abn_matches + self.security_identifier_matches

    @property
    def deterministic_identifier_matches(self) -> int:
        return self.total_matches


def normalise_abn(value: str | None) -> str | None:
    if value is None:
        return None
    digits_only = "".join(character for character in value if character.isdigit())
    if len(digits_only) != 11:
        return None
    return digits_only


def normalise_security_identifier_type(value: str | None) -> str | None:
    if value is None:
        return None
    normalised = " ".join(value.strip().upper().split())
    if normalised == "":
        return None
    if normalised == "ASX_CODE":
        return "ASX"
    return normalised


def normalise_security_identifier_value(identifier_type: str | None, value: str | None) -> str | None:
    if value is None:
        return None
    stripped = "".join(value.strip().split())
    if stripped == "":
        return None
    normalised_type = normalise_security_identifier_type(identifier_type)
    if normalised_type == ABN_IDENTIFIER_TYPE:
        return normalise_abn(stripped)
    return stripped.upper()


def resolve_entities_deterministically(
    session: Session,
    *,
    reporting_period_id: int,
    force_rerun: bool = False,
) -> DeterministicResolutionSummary:
    abn_candidates = _build_abn_candidate_map(session)
    security_identifier_candidates = _build_security_identifier_candidate_map(session)
    exact_name_candidates = build_exact_name_candidate_map(session)

    holdings = session.scalars(
        select(Holding)
        .where(Holding.reporting_period_id == reporting_period_id)
        .order_by(Holding.id.asc())
    ).all()

    summary = {
        "holdings_scanned": len(holdings),
        "holdings_skipped_prelinked": 0,
        "abn_matches": 0,
        "security_identifier_matches": 0,
        "unresolved_abn": 0,
        "unresolved_security_identifier": 0,
        "ambiguous_abn": 0,
        "ambiguous_security_identifier": 0,
        "force_match_applications": 0,
        "force_no_match_suppressions": 0,
        "force_new_entity_creations": 0,
        "redirect_to_parent_applications": 0,
        "exact_name_auto_links": 0,
        "exact_name_ambiguities_queued": 0,
        "exact_name_candidates_rejected_due_to_scope_conflict": 0,
        "unresolved_rows_remaining": 0,
    }

    for holding in holdings:
        if holding.entity_id is not None and not force_rerun:
            summary["holdings_skipped_prelinked"] += 1
            continue

        matched_entity_id = None
        ambiguous_candidate_entity_ids: list[int] | None = None
        ambiguous_evidence_json: dict[str, object] | None = None
        identifier_type = normalise_security_identifier_type(holding.security_identifier_type)

        if identifier_type == ABN_IDENTIFIER_TYPE:
            normalized_abn = normalise_abn(holding.security_identifier_value)
            if normalized_abn is not None:
                abn_matches = abn_candidates.get(normalized_abn, set())
                if len(abn_matches) == 1:
                    matched_entity_id = next(iter(abn_matches))
                    summary["abn_matches"] += 1
                elif len(abn_matches) > 1:
                    summary["ambiguous_abn"] += 1
                    ambiguous_candidate_entity_ids = sorted(abn_matches)
                    ambiguous_evidence_json = {
                        "ambiguity_kind": "abn",
                        "identifier_type": ABN_IDENTIFIER_TYPE,
                        "identifier_value": normalized_abn,
                        "confidence_score": DETERMINISTIC_CONFIDENCE_SCORE,
                    }
                else:
                    summary["unresolved_abn"] += 1
            elif holding.security_identifier_value:
                summary["unresolved_abn"] += 1

        if matched_entity_id is None and identifier_type in SUPPORTED_SECURITY_IDENTIFIER_TYPES:
            normalized_identifier_value = normalise_security_identifier_value(
                identifier_type,
                holding.security_identifier_value,
            )
            if normalized_identifier_value is not None:
                security_matches = security_identifier_candidates.get((identifier_type, normalized_identifier_value), set())
                if len(security_matches) == 1:
                    matched_entity_id = next(iter(security_matches))
                    summary["security_identifier_matches"] += 1
                elif len(security_matches) > 1:
                    summary["ambiguous_security_identifier"] += 1
                    ambiguous_candidate_entity_ids = sorted(security_matches)
                    ambiguous_evidence_json = {
                        "ambiguity_kind": "security_identifier",
                        "identifier_type": identifier_type,
                        "identifier_value": normalized_identifier_value,
                        "confidence_score": DETERMINISTIC_CONFIDENCE_SCORE,
                    }
                else:
                    summary["unresolved_security_identifier"] += 1
            elif holding.security_identifier_value:
                summary["unresolved_security_identifier"] += 1

        if matched_entity_id is not None:
            holding.entity_id = matched_entity_id
            continue

        applied_override = apply_entity_match_override(session, holding=holding)
        if applied_override is not None:
            if applied_override.action == FORCE_MATCH_ACTION:
                summary["force_match_applications"] += 1
            elif applied_override.action == FORCE_NO_MATCH_ACTION:
                summary["force_no_match_suppressions"] += 1
            elif applied_override.action == FORCE_NEW_ENTITY_ACTION:
                if applied_override.created_new_entity:
                    summary["force_new_entity_creations"] += 1
                exact_name_candidates = build_exact_name_candidate_map(session)
            elif applied_override.action == REDIRECT_TO_PARENT_ACTION:
                summary["redirect_to_parent_applications"] += 1

            if holding.entity_id is None:
                summary["unresolved_rows_remaining"] += 1
            continue

        if ambiguous_candidate_entity_ids is None and ambiguous_evidence_json is None:
            exact_name_resolution = resolve_exact_normalized_name_match(
                holding=holding,
                candidate_map=exact_name_candidates,
            )
            summary["exact_name_candidates_rejected_due_to_scope_conflict"] += len(
                exact_name_resolution.rejected_candidate_entity_ids
            )
            if exact_name_resolution.matched_entity_id is not None:
                holding.entity_id = exact_name_resolution.matched_entity_id
                summary["exact_name_auto_links"] += 1
                continue
            if exact_name_resolution.ambiguous_candidate_entity_ids and exact_name_resolution.evidence_json is not None:
                ambiguous_candidate_entity_ids = list(exact_name_resolution.ambiguous_candidate_entity_ids)
                ambiguous_evidence_json = exact_name_resolution.evidence_json
                summary["exact_name_ambiguities_queued"] += 1

        if ambiguous_candidate_entity_ids is not None and ambiguous_evidence_json is not None:
            upsert_entity_resolution_queue_item(
                session,
                holding_id=holding.id,
                candidate_entity_ids=ambiguous_candidate_entity_ids,
                evidence_json=ambiguous_evidence_json,
                top_candidate_score=(
                    EXACT_NAME_CONFIDENCE_SCORE
                    if ambiguous_evidence_json.get("ambiguity_kind") == "exact_name"
                    else DETERMINISTIC_CONFIDENCE_SCORE
                ),
            )

        if holding.entity_id is None:
            summary["unresolved_rows_remaining"] += 1

    session.flush()
    return DeterministicResolutionSummary(
        reporting_period_id=reporting_period_id,
        holdings_scanned=summary["holdings_scanned"],
        holdings_skipped_prelinked=summary["holdings_skipped_prelinked"],
        abn_matches=summary["abn_matches"],
        security_identifier_matches=summary["security_identifier_matches"],
        unresolved_abn=summary["unresolved_abn"],
        unresolved_security_identifier=summary["unresolved_security_identifier"],
        ambiguous_abn=summary["ambiguous_abn"],
        ambiguous_security_identifier=summary["ambiguous_security_identifier"],
        force_match_applications=summary["force_match_applications"],
        force_no_match_suppressions=summary["force_no_match_suppressions"],
        force_new_entity_creations=summary["force_new_entity_creations"],
        redirect_to_parent_applications=summary["redirect_to_parent_applications"],
        exact_name_auto_links=summary["exact_name_auto_links"],
        exact_name_ambiguities_queued=summary["exact_name_ambiguities_queued"],
        exact_name_candidates_rejected_due_to_scope_conflict=summary[
            "exact_name_candidates_rejected_due_to_scope_conflict"
        ],
        unresolved_rows_remaining=summary["unresolved_rows_remaining"],
    )


def _build_abn_candidate_map(session: Session) -> dict[str, set[int]]:
    candidates: dict[str, set[int]] = {}
    rows = session.execute(select(Entity.id, Entity.abn).where(Entity.abn.is_not(None))).all()
    for entity_id, abn in rows:
        normalized_abn = normalise_abn(abn)
        if normalized_abn is None:
            continue
        candidates.setdefault(normalized_abn, set()).add(int(entity_id))
    return candidates


def _build_security_identifier_candidate_map(session: Session) -> dict[tuple[str, str], set[int]]:
    candidates: dict[tuple[str, str], set[int]] = {}
    rows = session.execute(
        select(
            EntitySecurityIdentifier.entity_id,
            EntitySecurityIdentifier.identifier_type,
            EntitySecurityIdentifier.identifier_value,
        ).where(EntitySecurityIdentifier.identifier_value.is_not(None))
    ).all()
    for entity_id, identifier_type, identifier_value in rows:
        normalized_type = normalise_security_identifier_type(identifier_type)
        if normalized_type not in SUPPORTED_SECURITY_IDENTIFIER_TYPES:
            continue
        normalized_value = normalise_security_identifier_value(normalized_type, identifier_value)
        if normalized_value is None:
            continue
        candidates.setdefault((normalized_type, normalized_value), set()).add(int(entity_id))
    return candidates
