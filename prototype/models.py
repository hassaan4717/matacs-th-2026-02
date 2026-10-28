"""Data models for the proposal triage prototype."""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Any, Dict, List, Optional


@dataclass
class MandatoryResult:
    """Result of evaluating one mandatory rule."""

    rule_id: str
    name: str
    state: str  # PASS, FAIL, UNKNOWN
    reason: str
    evidence_reference: str = ""

    @property
    def passed(self) -> bool:
        return self.state == "PASS"

    @property
    def failed(self) -> bool:
        return self.state == "FAIL"

    @property
    def unknown(self) -> bool:
        return self.state == "UNKNOWN"


@dataclass
class EligibilityResult:
    """Aggregated mandatory eligibility outcome for a proposal."""

    proposal_id: str
    eligible: bool
    results: List[MandatoryResult] = field(default_factory=list)
    reason: str = ""

    @property
    def has_confirmed_failure(self) -> bool:
        return any(r.failed for r in self.results)

    @property
    def has_unknown(self) -> bool:
        return any(r.unknown for r in self.results)


@dataclass
class ComponentScore:
    """A single weighted-component score."""

    criterion_id: str
    score: Optional[float]  # None means not computable / flagged
    reason: str
    evidence_reference: str = ""
    status: str = "computed"  # computed, flagged, not_applicable


@dataclass
class ScoredProposal:
    """A fully evaluated proposal before ranking."""

    proposal_id: str
    name: str
    eligible: bool
    rankable: bool
    status: str  # ranked, flagged, ineligible
    components: Dict[str, ComponentScore] = field(default_factory=dict)
    total_score: Optional[float] = None
    reason: str = ""
    config_version: str = ""
    config_hash: str = ""
    audit_refs: List[str] = field(default_factory=list)


@dataclass
class RankedProposal:
    """A proposal after ranking has been applied."""

    proposal_id: str
    name: str
    rank: Optional[int]
    status: str
    score: Optional[float]
    reason: str
    eligibility: Optional[Dict[str, Any]] = None
    component_scores: Optional[Dict[str, Any]] = None
    evidence_references: Optional[Dict[str, str]] = None
    review_flags: Optional[List[str]] = None
    config_version: str = ""
    config_hash: str = ""
    audit_id: str = ""

    def to_dict(self) -> Dict[str, Any]:
        record: Dict[str, Any] = {
            "proposal": self.proposal_id,
            "rank": self.rank,
            "status": self.status,
            "score": self.score,
            "reason": self.reason,
        }
        if self.eligibility is not None:
            record["eligibility"] = self.eligibility
        if self.component_scores is not None:
            record["component_scores"] = self.component_scores
        if self.evidence_references is not None:
            record["evidence_references"] = self.evidence_references
        if self.review_flags:
            record["review_flags"] = self.review_flags
        if self.config_version:
            record["config_version"] = self.config_version
        if self.config_hash:
            record["config_hash"] = self.config_hash
        if self.audit_id:
            record["audit_id"] = self.audit_id
        return record


@dataclass
class AuditEvent:
    """A single audit record."""

    timestamp: str
    proposal_id: str
    event_type: str
    actor: str
    config_version: str
    config_hash: str
    stage: str
    evidence_reference: str = ""
    previous_value: Optional[Any] = None
    updated_value: Optional[Any] = None
    explanation: str = ""

    def to_dict(self) -> Dict[str, Any]:
        return {
            "timestamp": self.timestamp,
            "proposal_id": self.proposal_id,
            "event_type": self.event_type,
            "actor": self.actor,
            "config_version": self.config_version,
            "config_hash": self.config_hash,
            "stage": self.stage,
            "evidence_reference": self.evidence_reference,
            "previous_value": self.previous_value,
            "updated_value": self.updated_value,
            "explanation": self.explanation,
        }
