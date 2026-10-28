"""Proposal fixture validation."""

from __future__ import annotations

from typing import Any, Dict, List


class ProposalValidationError(ValueError):
    """Raised when a proposal fixture is invalid."""


REQUIRED_TOP_FIELDS = ("id", "name", "mandatory", "experience", "price", "timeline", "warranty", "team_approach")


def validate_proposal(proposal: Dict[str, Any]) -> None:
    """Validate the structure of a single proposal fixture."""
    if not isinstance(proposal, dict):
        raise ProposalValidationError("Each proposal must be a JSON object")
    for field in REQUIRED_TOP_FIELDS:
        if field not in proposal:
            raise ProposalValidationError(f"Proposal missing required field: {field}")

    pid = proposal.get("id")
    if not isinstance(pid, str) or not pid.strip():
        raise ProposalValidationError("Proposal id must be a non-empty string")

    mandatory = proposal.get("mandatory")
    if not isinstance(mandatory, dict):
        raise ProposalValidationError("Proposal.mandatory must be an object")
    for key in ("bidder_licence_stated", "wsib_clearance", "liability_insurance_cad"):
        if key not in mandatory:
            raise ProposalValidationError(f"Proposal.mandatory missing field: {key}")

    for block in ("experience", "price", "timeline", "warranty", "team_approach"):
        if block not in proposal or not isinstance(proposal[block], dict):
            raise ProposalValidationError(f"Proposal.{block} must be an object")


def validate_proposals(proposals: List[Dict[str, Any]]) -> None:
    """Validate a list of proposal fixtures and check for duplicate ids."""
    if not isinstance(proposals, list) or not proposals:
        raise ProposalValidationError("proposals must be a non-empty list")
    seen: set = set()
    for proposal in proposals:
        validate_proposal(proposal)
        pid = proposal["id"]
        if pid in seen:
            raise ProposalValidationError(f"Duplicate proposal id: {pid}")
        seen.add(pid)
