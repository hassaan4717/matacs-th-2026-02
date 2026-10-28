"""Mandatory eligibility evaluation."""

from __future__ import annotations

from typing import Any, Dict, List

from models import EligibilityResult, MandatoryResult


PASS = "PASS"
FAIL = "FAIL"
UNKNOWN = "UNKNOWN"


def evaluate_mandatory(
    proposal: Dict[str, Any],
    rules: List[Dict[str, Any]],
) -> EligibilityResult:
    """Evaluate all mandatory rules for a proposal.

    Mandatory state semantics:
      PASS   - evidence confirms the requirement.
      FAIL   - evidence confirms the requirement is NOT met.
      UNKNOWN - evidence is missing or ambiguous; route for review.
    """
    proposal_id = str(proposal.get("id", ""))
    mandatory = proposal.get("mandatory", {})
    results: List[MandatoryResult] = []

    for rule in rules:
        rule_id = str(rule.get("id", ""))
        name = str(rule.get("name", rule_id))

        if rule_id == "M1":
            state, reason, evidence_ref = _evaluate_m1(mandatory, rule)
        elif rule_id == "M2":
            state, reason, evidence_ref = _evaluate_m2(mandatory, rule)
        else:
            state, reason, evidence_ref = UNKNOWN, f"No evaluator for rule {rule_id}", ""

        results.append(
            MandatoryResult(
                rule_id=rule_id,
                name=name,
                state=state,
                reason=reason,
                evidence_reference=evidence_ref,
            )
        )

    eligible = all(r.state == PASS for r in results)
    if not eligible:
        failed = [r.name for r in results if r.state == FAIL]
        unknown = [r.name for r in results if r.state == UNKNOWN]
        parts: List[str] = []
        if failed:
            parts.append("failed: " + ", ".join(failed))
        if unknown:
            parts.append("needs review: " + ", ".join(unknown))
        reason = "; ".join(parts) if parts else "ineligible"
    else:
        reason = "All mandatory requirements passed."

    return EligibilityResult(
        proposal_id=proposal_id,
        eligible=eligible,
        results=results,
        reason=reason,
    )


def _evaluate_m1(mandatory: Dict[str, Any], rule: Dict[str, Any]) -> tuple:
    stated = mandatory.get("bidder_licence_stated")
    licence_number = mandatory.get("licence_number")
    if stated is True and licence_number:
        return PASS, "Bidder's Ontario electrical contractor licence stated.", "mandatory.licence_number"
    if stated is False or stated is None:
        return FAIL, "Bidder's own Ontario electrical contractor licence is not established.", "mandatory.bidder_licence_stated"
    return UNKNOWN, "Licence evidence is ambiguous.", ""


def _evaluate_m2(mandatory: Dict[str, Any], rule: Dict[str, Any]) -> tuple:
    wsib = mandatory.get("wsib_clearance")
    insurance = mandatory.get("liability_insurance_cad")

    wsib_ok = wsib is True
    insurance_ok = isinstance(insurance, (int, float)) and not isinstance(insurance, bool) and insurance >= 5_000_000

    if wsib_ok and insurance_ok:
        return PASS, "WSIB clearance and CAD 5,000,000 liability insurance confirmed.", "mandatory.wsib_clearance;mandatory.liability_insurance_cad"

    reasons: List[str] = []
    if not wsib_ok:
        reasons.append("WSIB clearance not confirmed")
    if not insurance_ok:
        reasons.append("Liability insurance of at least CAD 5,000,000 not confirmed")
    if any(v is None for v in (wsib, insurance)):
        return UNKNOWN, "; ".join(reasons) + ". Evidence missing or ambiguous.", ""
    return FAIL, "; ".join(reasons) + ".", ""
