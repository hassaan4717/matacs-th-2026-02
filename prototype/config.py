"""Configuration loading and validation for the triage policy."""

from __future__ import annotations

import hashlib
import json
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Dict, List, Optional


class ConfigError(ValueError):
    """Raised when configuration is invalid or missing required fields."""


@dataclass
class CriteriaConfig:
    """Validated policy configuration."""

    schema_version: str
    config_id: str
    project: Dict[str, Any]
    mandatory_rules: List[Dict[str, Any]]
    weighted_criteria: List[Dict[str, Any]]
    experience: Dict[str, Any]
    price: Dict[str, Any]
    timeline: Dict[str, Any]
    warranty: Dict[str, Any]
    team_approach: Dict[str, Any]
    tie_breaking: List[Dict[str, Any]]
    missing_evidence_policy: Dict[str, Any]
    rounding_policy: Dict[str, Any]
    raw: Dict[str, Any] = field(default_factory=dict)

    @property
    def config_version(self) -> str:
        return f"{self.config_id}::{self.schema_version}"

    @property
    def config_hash(self) -> str:
        payload = json.dumps(self.raw, sort_keys=True).encode("utf-8")
        return hashlib.sha256(payload).hexdigest()[:16]

    def weight_by_id(self, criterion_id: str) -> float:
        for c in self.weighted_criteria:
            if c.get("id") == criterion_id:
                return float(c["weight"])
        raise ConfigError(f"Missing weight for criterion '{criterion_id}'")

    def total_weight(self) -> float:
        return sum(float(c.get("weight", 0)) for c in self.weighted_criteria)


def _require(config: Dict[str, Any], path: str) -> Any:
    parts = path.split(".")
    node: Any = config
    for part in parts:
        if not isinstance(node, dict) or part not in node:
            raise ConfigError(f"Missing required configuration field: {path}")
        node = node[part]
    return node


def load_criteria(path: str | Path) -> CriteriaConfig:
    """Load and validate the criteria configuration file."""
    p = Path(path)
    if not p.is_file():
        raise ConfigError(f"Criteria file not found: {p}")
    try:
        raw = json.loads(p.read_text(encoding="utf-8"))
    except json.JSONDecodeError as exc:
        raise ConfigError(f"Invalid JSON in criteria file {p}: {exc}") from exc

    if not isinstance(raw, dict):
        raise ConfigError("Criteria configuration must be a JSON object")

    # Top-level required fields
    for field_name in (
        "schema_version",
        "config_id",
        "project",
        "mandatory_rules",
        "weighted_criteria",
    ):
        if field_name not in raw:
            raise ConfigError(f"Missing required configuration field: {field_name}")

    project = _require(raw, "project")
    for field_name in ("budget_ceiling_cad", "max_completion_weeks"):
        if field_name not in project:
            raise ConfigError(f"Missing required project field: {field_name}")

    # Mandatory rules
    mandatory_rules = raw["mandatory_rules"]
    if not isinstance(mandatory_rules, list) or not mandatory_rules:
        raise ConfigError("mandatory_rules must be a non-empty list")
    for rule in mandatory_rules:
        if not isinstance(rule, dict) or "id" not in rule:
            raise ConfigError("Each mandatory rule must have an id")

    # Weighted criteria
    weighted_criteria = raw["weighted_criteria"]
    if not isinstance(weighted_criteria, list) or not weighted_criteria:
        raise ConfigError("weighted_criteria must be a non-empty list")
    criterion_ids: List[str] = []
    for c in weighted_criteria:
        if not isinstance(c, dict) or "id" not in c or "weight" not in c:
            raise ConfigError("Each weighted criterion must have an id and weight")
        weight = c["weight"]
        if not isinstance(weight, (int, float)) or isinstance(weight, bool):
            raise ConfigError(f"Weight for '{c.get('id')}' must be numeric")
        if weight < 0:
            raise ConfigError(f"Weight for '{c.get('id')}' must be non-negative")
        criterion_ids.append(str(c["id"]))

    total_weight = sum(float(c["weight"]) for c in weighted_criteria)
    # Tolerance for floating-point decimal weights
    if abs(total_weight - 100.0) > 1e-6:
        raise ConfigError(
            f"Weighted criteria must total 100%, got {total_weight}%"
        )

    # Scoring parameter blocks
    for block in ("experience", "price", "timeline", "warranty", "team_approach"):
        if block not in raw:
            raise ConfigError(f"Missing required scoring block: {block}")

    experience = raw["experience"]
    for field_name in ("target_installations", "capacity_threshold_kw", "evaluation_window_years"):
        if field_name not in experience:
            raise ConfigError(f"Missing experience parameter: {field_name}")

    price = raw["price"]
    if "budget_ceiling_cad" not in price:
        raise ConfigError("Missing price parameter: budget_ceiling_cad")

    timeline = raw["timeline"]
    if "max_weeks" not in timeline:
        raise ConfigError("Missing timeline parameter: max_weeks")

    warranty = raw["warranty"]
    for field_name in ("panel_target_years", "workmanship_target_years"):
        if field_name not in warranty:
            raise ConfigError(f"Missing warranty parameter: {field_name}")

    team_approach = raw["team_approach"]
    components = team_approach.get("components", [])
    if not isinstance(components, list) or not components:
        raise ConfigError("team_approach.components must be a non-empty list")
    comp_weight_total = sum(float(c.get("weight", 0)) for c in components)
    if abs(comp_weight_total - 100.0) > 1e-6:
        raise ConfigError(
            f"team_approach component weights must total 100%, got {comp_weight_total}%"
        )

    if "tie_breaking" not in raw:
        raise ConfigError("Missing required configuration field: tie_breaking")
    if "missing_evidence_policy" not in raw:
        raise ConfigError("Missing required configuration field: missing_evidence_policy")
    if "rounding_policy" not in raw:
        raise ConfigError("Missing required configuration field: rounding_policy")

    return CriteriaConfig(
        schema_version=str(raw["schema_version"]),
        config_id=str(raw["config_id"]),
        project=project,
        mandatory_rules=mandatory_rules,
        weighted_criteria=weighted_criteria,
        experience=experience,
        price=price,
        timeline=timeline,
        warranty=warranty,
        team_approach=team_approach,
        tie_breaking=raw["tie_breaking"],
        missing_evidence_policy=raw["missing_evidence_policy"],
        rounding_policy=raw["rounding_policy"],
        raw=raw,
    )
