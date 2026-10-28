"""Deterministic weighted scoring engine."""

from __future__ import annotations

from typing import Any, Dict, List, Optional

from config import CriteriaConfig
from eligibility import UNKNOWN
from models import ComponentScore, ScoredProposal


def score_proposal(
    proposal: Dict[str, Any],
    eligibility,
    config: CriteriaConfig,
) -> ScoredProposal:
    """Compute component scores only where justified.

    A proposal is rankable only when:
      - it passed all mandatory gates, and
      - every weighted component can be computed from verified evidence.
    """
    proposal_id = str(proposal.get("id", ""))
    name = str(proposal.get("name", ""))

    eligible = eligibility.eligible
    components: Dict[str, ComponentScore] = {}
    review_flags: List[str] = []

    # Experience
    comp_exp, flag_exp = _score_experience(proposal, config)
    components["experience"] = comp_exp
    if flag_exp:
        review_flags.append(flag_exp)

    # Price
    comp_price, flag_price = _score_price(proposal, config)
    components["price"] = comp_price
    if flag_price:
        review_flags.append(flag_price)

    # Timeline
    comp_timeline, flag_timeline = _score_timeline(proposal, config)
    components["timeline"] = comp_timeline
    if flag_timeline:
        review_flags.append(flag_timeline)

    # Warranty
    comp_warranty, flag_warranty = _score_warranty(proposal, config)
    components["warranty"] = comp_warranty
    if flag_warranty:
        review_flags.append(flag_warranty)

    # Team and approach
    comp_team, flag_team = _score_team_approach(proposal, config)
    components["team_approach"] = comp_team
    if flag_team:
        review_flags.append(flag_team)

    rankable = eligible and all(c.score is not None for c in components.values())
    total_score: Optional[float] = None
    reason_parts: List[str] = []

    if not eligible:
        status = "ineligible"
        reason_parts.append("Ineligible: " + eligibility.reason)
    elif not rankable:
        status = "flagged"
        missing = [c.criterion_id for c in components.values() if c.score is None]
        reason_parts.append(
            "Flagged for review: insufficient evidence to score " + ", ".join(missing)
        )
    else:
        status = "ranked"
        total_score = _weighted_total(components, config)
        reason_parts.append("Eligible and sufficiently evidenced; total score computed (" + _ranked_factors(components) + ").")

    if review_flags:
        reason_parts.append("Review flags: " + "; ".join(review_flags))

    return ScoredProposal(
        proposal_id=proposal_id,
        name=name,
        eligible=eligible,
        rankable=rankable,
        status=status,
        components=components,
        total_score=total_score,
        reason=" ".join(reason_parts),
        config_version=config.config_version,
        config_hash=config.config_hash,
    )


def _ranked_factors(components: Dict[str, ComponentScore]) -> str:
    """Build a concise, evidence-backed factor summary for a ranked proposal."""
    order = ("experience", "price", "timeline", "warranty", "team_approach")
    parts: List[str] = []
    for cid in order:
        comp = components.get(cid)
        if comp and comp.score is not None:
            parts.append(f"{cid} {comp.score:.0f}/100")
    return ", ".join(parts) if parts else "all components scored"


def _score_experience(proposal: Dict[str, Any], config: CriteriaConfig) -> tuple:
    exp = proposal.get("experience", {})
    status = exp.get("status")
    count = exp.get("qualifying_count")
    window_established = exp.get("window_established", False)
    evidence = exp.get("evidence", "")

    if status != "verified" or count is None or not window_established:
        reason = "Experience evidence not verified for the rolling five-year window."
        if status == "uncertain":
            reason += " " + str(exp.get("uncertainty_reason", ""))
        return (
            ComponentScore(
                criterion_id="experience",
                score=None,
                reason=reason,
                evidence_reference=evidence,
                status="flagged",
            ),
            "experience component cannot be scored without a verified qualifying installation count.",
        )

    target = int(config.experience["target_installations"])
    score = 100.0 * min(float(count) / float(target), 1.0)
    return (
        ComponentScore(
            criterion_id="experience",
            score=score,
            reason=f"{count} qualifying installations; target {target}.",
            evidence_reference=evidence,
        ),
        None,
    )


def _score_price(proposal: Dict[str, Any], config: CriteriaConfig) -> tuple:
    price = proposal.get("price", {})
    status = price.get("status")
    amount = price.get("amount_cad")
    evidence = price.get("evidence", "")
    ceiling = float(config.price["budget_ceiling_cad"])

    if status != "verified" or amount is None:
        return (
            ComponentScore(
                criterion_id="price",
                score=None,
                reason="Price evidence not verified.",
                evidence_reference=evidence,
                status="flagged",
            ),
            "price component cannot be scored without verified price evidence.",
        )

    amount = float(amount)
    if amount <= 0:
        return (
            ComponentScore(
                criterion_id="price",
                score=None,
                reason="Price must be positive.",
                evidence_reference=evidence,
                status="flagged",
            ),
            "price is not positive.",
        )
    if amount > ceiling:
        return (
            ComponentScore(
                criterion_id="price",
                score=None,
                reason=f"Price CAD {amount:,.0f} exceeds budget ceiling CAD {ceiling:,.0f}.",
                evidence_reference=evidence,
                status="flagged",
            ),
            "price exceeds budget ceiling.",
        )

    # Baseline (lowest eligible price) is applied by the ranking stage.
    return (
        ComponentScore(
            criterion_id="price",
            score=amount,  # raw value; normalized during ranking
            reason=f"Price CAD {amount:,.0f} within budget ceiling.",
            evidence_reference=evidence,
        ),
        None,
    )


def _score_timeline(proposal: Dict[str, Any], config: CriteriaConfig) -> tuple:
    timeline = proposal.get("timeline", {})
    status = timeline.get("status")
    weeks = timeline.get("weeks")
    evidence = timeline.get("evidence", "")
    max_weeks = float(config.timeline["max_weeks"])

    if status != "verified" or weeks is None:
        return (
            ComponentScore(
                criterion_id="timeline",
                score=None,
                reason="Timeline not verified; cannot confirm 16-week constraint.",
                evidence_reference=evidence,
                status="flagged",
            ),
            "timeline component cannot be scored without verified timeline evidence.",
        )

    weeks = float(weeks)
    if weeks <= 0:
        return (
            ComponentScore(
                criterion_id="timeline",
                score=None,
                reason="Timeline must be positive.",
                evidence_reference=evidence,
                status="flagged",
            ),
            "timeline is not positive.",
        )
    if weeks > max_weeks:
        return (
            ComponentScore(
                criterion_id="timeline",
                score=None,
                reason=f"Timeline {weeks} weeks exceeds maximum {max_weeks} weeks.",
                evidence_reference=evidence,
                status="flagged",
            ),
            "timeline exceeds maximum permitted duration.",
        )

    score = 100.0 * (max_weeks - weeks) / max_weeks
    return (
        ComponentScore(
            criterion_id="timeline",
            score=score,
            reason=f"{weeks} weeks within {max_weeks}-week maximum.",
            evidence_reference=evidence,
        ),
        None,
    )


def _score_warranty(proposal: Dict[str, Any], config: CriteriaConfig) -> tuple:
    warranty = proposal.get("warranty", {})
    status = warranty.get("status")
    panel = warranty.get("panel_years")
    workmanship = warranty.get("workmanship_years")
    evidence = warranty.get("evidence", "")

    if status != "verified" or panel is None or workmanship is None:
        return (
            ComponentScore(
                criterion_id="warranty",
                score=None,
                reason="Warranty evidence not verified.",
                evidence_reference=evidence,
                status="flagged",
            ),
            "warranty component cannot be scored without verified warranty evidence.",
        )

    panel_target = float(config.warranty["panel_target_years"])
    workmanship_target = float(config.warranty["workmanship_target_years"])
    panel_score = 100.0 * min(float(panel) / panel_target, 1.0)
    workmanship_score = 100.0 * min(float(workmanship) / workmanship_target, 1.0)
    score = (panel_score + workmanship_score) / 2.0
    return (
        ComponentScore(
            criterion_id="warranty",
            score=score,
            reason=f"Panel {panel}y ({panel_score:.1f}), workmanship {workmanship}y ({workmanship_score:.1f}).",
            evidence_reference=evidence,
        ),
        None,
    )


def _score_team_approach(proposal: Dict[str, Any], config: CriteriaConfig) -> tuple:
    team = proposal.get("team_approach", {})
    status = team.get("status")
    evidence = team.get("evidence", "")
    components_cfg = config.team_approach.get("components", [])

    if status not in ("verified", "partial"):
        return (
            ComponentScore(
                criterion_id="team_approach",
                score=None,
                reason="Team and approach evidence not documented.",
                evidence_reference=evidence,
                status="flagged",
            ),
            "team_approach component cannot be scored without documented evidence.",
        )

    total_weight = sum(float(c.get("weight", 0)) for c in components_cfg) or 100.0
    weighted_sum = 0.0
    for comp in components_cfg:
        comp_id = str(comp.get("id", ""))
        weight = float(comp.get("weight", 0))
        comp_score = _team_component_score(team, comp_id)
        weighted_sum += (weight / total_weight) * comp_score

    score = weighted_sum
    return (
        ComponentScore(
            criterion_id="team_approach",
            score=score,
            reason="Team and approach rubric applied to documented evidence.",
            evidence_reference=evidence,
        ),
        None,
    )


def _team_component_score(team: Dict[str, Any], comp_id: str) -> float:
    """Score one team rubric component (0-100) from documented evidence only."""
    if comp_id == "named_lead":
        return 100.0 if team.get("named_lead") is True else 0.0
    if comp_id == "crew_qualifications":
        crew = team.get("crew")
        return 100.0 if isinstance(crew, str) and crew.strip() else 0.0
    if comp_id == "safety_plan":
        return 100.0 if team.get("safety_plan") is True else 0.0
    if comp_id == "monitoring_approach":
        monitoring = team.get("monitoring")
        return 100.0 if isinstance(monitoring, str) and monitoring.strip() else 0.0
    return 0.0


def _weighted_total(components: Dict[str, ComponentScore], config: CriteriaConfig) -> float:
    total = 0.0
    total_weight = 0.0
    for criterion in config.weighted_criteria:
        cid = str(criterion["id"])
        weight = float(criterion["weight"])
        comp = components.get(cid)
        if comp is None or comp.score is None:
            continue
        total += weight * comp.score
        total_weight += weight
    if total_weight == 0:
        return 0.0
    return total / total_weight  # weights are fractions of 100; normalize


def apply_price_normalization(
    scored: List[ScoredProposal],
    config: CriteriaConfig,
) -> None:
    """Normalize price scores against the lowest eligible rankable price.

    Only proposals that are eligible and rankable (all components computed)
    participate in the comparison pool. Ineligible or flagged proposals never
    establish the baseline.
    """
    pool = [
        s for s in scored
        if s.eligible and s.rankable and s.components.get("price") is not None
        and isinstance(s.components["price"].score, (int, float))
    ]
    if not pool:
        return
    lowest = min(
        float(s.components["price"].score) for s in pool
    )
    ceiling = float(config.price["budget_ceiling_cad"])

    for s in scored:
        comp = s.components.get("price")
        if comp is None or not isinstance(comp.score, (int, float)):
            continue
        amount = float(comp.score)
        if amount > ceiling:
            comp.score = None
            s.rankable = False
            s.status = "flagged"
            comp.reason = f"Price CAD {amount:,.0f} exceeds budget ceiling."
            comp.status = "flagged"
            continue
        comp.score = 100.0 * lowest / amount
        comp.reason = f"Normalized price score vs lowest eligible price CAD {lowest:,.0f}."
        # Recompute total now that price is normalized
        if s.rankable:
            s.total_score = _weighted_total(s.components, config)
            # Refresh the ranked reason so the price factor reflects the normalized score.
            s.reason = (
                "Eligible and sufficiently evidenced; total score computed ("
                + _ranked_factors(s.components)
                + ")."
            )
