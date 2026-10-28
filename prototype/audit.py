"""Lightweight audit mechanism for decision provenance."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import Any, List

from models import AuditEvent


class AuditLog:
    """In-memory audit log. A production system would persist this to durable storage."""

    def __init__(self, config_version: str, config_hash: str):
        self.config_version = config_version
        self.config_hash = config_hash
        self.events: List[AuditEvent] = []

    def record(
        self,
        proposal_id: str,
        event_type: str,
        actor: str,
        stage: str,
        evidence_reference: str = "",
        previous_value: Any = None,
        updated_value: Any = None,
        explanation: str = "",
    ) -> AuditEvent:
        event = AuditEvent(
            timestamp=datetime.now(timezone.utc).isoformat(),
            proposal_id=proposal_id,
            event_type=event_type,
            actor=actor,
            config_version=self.config_version,
            config_hash=self.config_hash,
            stage=stage,
            evidence_reference=evidence_reference,
            previous_value=previous_value,
            updated_value=updated_value,
            explanation=explanation,
        )
        self.events.append(event)
        return event

    def to_list(self) -> List[dict]:
        return [e.to_dict() for e in self.events]
