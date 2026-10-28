"""Ranking and deterministic tie-breaking."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from config import CriteriaConfig
from models import RankedProposal, ScoredProposal


def rank_proposals(
    scored: List[ScoredProposal],
    config: CriteriaConfig,
) -> List[RankedProposal]:
    """Rank eligible, sufficiently evidenced proposals.

    Flagged and ineligible proposals are returned with null rank/score.
    """
    round_decimals = int(config.rounding_policy.get("presentation_decimals", 2))

    ranked_records: List[RankedProposal] = []
    rankable: List[ScoredProposal] = []

    for s in scored:
        if s.status == "ranked" and s.total_score is not None:
            rankable.append(s)
        else:
            ranked_records.append(
                RankedProposal(
                    proposal_id=s.proposal_id,
                    name=s.name,
                    rank=None,
                    status=s.status,
                    score=None,
                    reason=s.reason,
                    eligibility=_eligibility_dict(s),
                    component_scores=_component_dict(s),
                    evidence_references=_evidence_dict(s),
                    review_flags=_review_flags(s),
                    config_version=s.config_version,
                    config_hash=s.config_hash,
                    audit_id=f"audit-{s.proposal_id}",
                )
            )

    # Deterministic tie-breaking sequence
    def sort_key(s: ScoredProposal):
        return (
            -float(s.total_score),
            -float(s.components["experience"].score)
            if s.components.get("experience") and s.components["experience"].score is not None
            else 0.0,
            float(s.components["price"].score)
            if s.components.get("price") and s.components["price"].score is not None
            else float("inf"),
            s.proposal_id,
        )

    rankable.sort(key=sort_key)

    for position, s in enumerate(rankable, start=1):
        score = round(float(s.total_score), round_decimals)
        ranked_records.append(
            RankedProposal(
                proposal_id=s.proposal_id,
                name=s.name,
                rank=position,
                status="ranked",
                score=score,
                reason=s.reason,
                eligibility=_eligibility_dict(s),
                component_scores=_component_dict(s),
                evidence_references=_evidence_dict(s),
                review_flags=_review_flags(s),
                config_version=s.config_version,
                config_hash=s.config_hash,
                audit_id=f"audit-{s.proposal_id}",
            )
        )

    # Stable ordering: ranked proposals first (by rank), then flagged, then ineligible,
    # each group in proposal-id order.
    order_key = {
        "ranked": (0, lambda r: r.rank if r.rank is not None else 9999),
        "flagged": (1, lambda r: r.proposal_id),
        "ineligible": (2, lambda r: r.proposal_id),
    }

    def final_key(r: RankedProposal):
        group, sub = order_key.get(r.status, (9, lambda r: r.proposal_id))
        return (group, sub(r))

    ranked_records.sort(key=final_key)
    return ranked_records


def _eligibility_dict(s: ScoredProposal) -> Optional[Dict[str, Any]]:
    return {
        "eligible": s.eligible,
        "rankable": s.rankable,
    }


def _component_dict(s: ScoredProposal) -> Optional[Dict[str, Any]]:
    out: Dict[str, Any] = {}
    for cid, comp in s.components.items():
        out[cid] = {
            "score": None if comp.score is None else round(comp.score, 2),
            "status": comp.status,
            "reason": comp.reason,
        }
    return out or None


def _evidence_dict(s: ScoredProposal) -> Optional[Dict[str, str]]:
    out: Dict[str, str] = {}
    for cid, comp in s.components.items():
        if comp.evidence_reference:
            out[cid] = comp.evidence_reference
    return out or None


def _review_flags(s: ScoredProposal) -> Optional[List[str]]:
    flags: List[str] = []
    if not s.eligible:
        flags.append("ineligible")
    if not s.rankable:
        flags.append("not_rankable")
    return flags or None
