"""Command-line interface for the proposal triage prototype.

Usage:
    python prototype/main.py --proposals prototype/sample_data.json --criteria prototype/criteria.json --output ranking.json
"""

from __future__ import annotations

import argparse
import json
import sys
from pathlib import Path
from typing import Any, Dict, List

from audit import AuditLog
from config import ConfigError, load_criteria
from eligibility import evaluate_mandatory
from models import RankedProposal
from ranking import rank_proposals
from scoring import apply_price_normalization, score_proposal
from validation import ProposalValidationError, validate_proposals


def load_json(path: Path, label: str) -> Any:
    if not path.is_file():
        print(f"Error: {label} file not found: {path}", file=sys.stderr)
        sys.exit(2)
    try:
        return json.loads(path.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        print(f"Error: Invalid JSON in {label} file {path}: {exc}", file=sys.stderr)
        sys.exit(2)


def build_parser() -> argparse.ArgumentParser:
    parser = argparse.ArgumentParser(
        description="AI-assisted proposal triage prototype (decision support only)."
    )
    parser.add_argument("--proposals", required=True, help="Path to proposals JSON file")
    parser.add_argument("--criteria", required=True, help="Path to criteria configuration JSON file")
    parser.add_argument("--output", required=True, help="Path to write ranking.json output")
    return parser


def run(proposals_path: Path, criteria_path: Path, output_path: Path) -> int:
    # 1. Load and validate criteria configuration
    try:
        config = load_criteria(criteria_path)
    except ConfigError as exc:
        print(f"Configuration error: {exc}", file=sys.stderr)
        return 2

    audit = AuditLog(config.config_version, config.config_hash)

    # 2. Load proposal fixtures
    raw = load_json(proposals_path, "proposals")
    if not isinstance(raw, dict) or "proposals" not in raw:
        print("Error: proposals file must contain a JSON object with a 'proposals' list", file=sys.stderr)
        return 2
    proposals: List[Dict[str, Any]] = raw["proposals"]

    # 3. Validate proposal identifiers and required fields
    try:
        validate_proposals(proposals)
    except ProposalValidationError as exc:
        print(f"Proposal validation error: {exc}", file=sys.stderr)
        return 2

    # Avoid overwriting input files
    if output_path.resolve() == proposals_path.resolve() or output_path.resolve() == criteria_path.resolve():
        print("Error: output path must not overwrite an input file", file=sys.stderr)
        return 2

    # 4-6. Evaluate mandatory gates, identify missing/conflicting evidence, compute scores
    scored: List[Any] = []
    for proposal in proposals:
        pid = str(proposal.get("id", ""))
        eligibility = evaluate_mandatory(proposal, config.mandatory_rules)

        audit.record(
            proposal_id=pid,
            event_type="mandatory_evaluation",
            actor="system",
            stage="eligibility",
            evidence_reference="proposal.mandatory",
            explanation=eligibility.reason,
        )

        scored_proposal = score_proposal(proposal, eligibility, config)
        scored.append(scored_proposal)

        audit.record(
            proposal_id=pid,
            event_type="scoring",
            actor="system",
            stage="scoring",
            explanation=scored_proposal.reason,
        )

    # 7. Price normalization against the eligible rankable pool
    apply_price_normalization(scored, config)

    # 8. Rank
    ranked: List[RankedProposal] = rank_proposals(scored, config)

    # 9. Record audit events for ranking decisions
    for r in ranked:
        audit.record(
            proposal_id=r.proposal_id,
            event_type="ranking_decision",
            actor="system",
            stage="ranking",
            explanation=f"Status={r.status}, rank={r.rank}, score={r.score}. {r.reason}",
        )

    # 10. Produce JSON output
    output_records = [r.to_dict() for r in ranked]
    output = {
        "config_version": config.config_version,
        "config_hash": config.config_hash,
        "proposals": output_records,
        "audit": audit.to_list(),
    }

    output_path.parent.mkdir(parents=True, exist_ok=True)
    output_path.write_text(json.dumps(output, indent=2, ensure_ascii=False) + "\n", encoding="utf-8")

    # 11. Print concise summary
    print_summary(output_records)
    return 0


def print_summary(records: List[dict]) -> None:
    print("\nProposal Triage Summary")
    print("=" * 40)
    for r in records:
        rank = r["rank"] if r["rank"] is not None else "—"
        score = r["score"] if r["score"] is not None else "—"
        print(f"  {r['proposal']}: rank={rank}, status={r['status']}, score={score}")
        print(f"         {r['reason']}")
    print()


def main(argv: List[str] | None = None) -> int:
    parser = build_parser()
    args = parser.parse_args(argv)
    return run(Path(args.proposals), Path(args.criteria), Path(args.output))


if __name__ == "__main__":
    sys.exit(main())
