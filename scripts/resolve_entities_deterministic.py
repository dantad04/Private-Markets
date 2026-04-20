from __future__ import annotations

from argparse import ArgumentParser
import json

from app.db.session import get_session
from app.entity_resolution.deterministic import DETERMINISTIC_CONFIDENCE_SCORE, resolve_entities_deterministically


def build_parser() -> ArgumentParser:
    parser = ArgumentParser(description="Run deterministic entity resolution for a reporting period.")
    parser.add_argument("--reporting-period", type=int, required=True, help="Reporting period id to resolve.")
    parser.add_argument(
        "--force-rerun",
        action="store_true",
        help="Re-evaluate holdings that are already linked to an entity.",
    )
    return parser


def main() -> int:
    args = build_parser().parse_args()
    session = get_session()
    try:
        summary = resolve_entities_deterministically(
            session,
            reporting_period_id=args.reporting_period,
            force_rerun=args.force_rerun,
        )
        session.commit()
    except Exception:
        session.rollback()
        raise
    finally:
        session.close()

    print(
        json.dumps(
            {
                "reporting_period_id": summary.reporting_period_id,
                "holdings_scanned": summary.holdings_scanned,
                "holdings_skipped_prelinked": summary.holdings_skipped_prelinked,
                "abn_matches": summary.abn_matches,
                "security_identifier_matches": summary.security_identifier_matches,
                "unresolved_abn": summary.unresolved_abn,
                "unresolved_security_identifier": summary.unresolved_security_identifier,
                "ambiguous_abn": summary.ambiguous_abn,
                "ambiguous_security_identifier": summary.ambiguous_security_identifier,
                "total_matches": summary.total_matches,
                "deterministic_confidence_score": DETERMINISTIC_CONFIDENCE_SCORE,
                "force_rerun": args.force_rerun,
            },
            indent=2,
            sort_keys=True,
        )
    )
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
