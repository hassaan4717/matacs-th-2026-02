"""Automated tests for the proposal triage prototype.

These tests verify business rules independently and do not require an API key,
network access, or a live model. Extraction is simulated by structured fixtures.
"""

from __future__ import annotations

import copy
import json
import subprocess
import sys
import tempfile
import unittest
from pathlib import Path

# Ensure the prototype directory is importable
PROTOTYPE_DIR = Path(__file__).resolve().parent
if str(PROTOTYPE_DIR) not in sys.path:
    sys.path.insert(0, str(PROTOTYPE_DIR))

from config import ConfigError, load_criteria
from eligibility import evaluate_mandatory, FAIL, PASS, UNKNOWN
from models import ScoredProposal
from scoring import apply_price_normalization, score_proposal
from validation import ProposalValidationError, validate_proposals, validate_proposal

REPO_ROOT = PROTOTYPE_DIR.parent
CRITERIA_PATH = PROTOTYPE_DIR / "criteria.json"
SAMPLE_DATA_PATH = PROTOTYPE_DIR / "sample_data.json"
MAIN_PATH = PROTOTYPE_DIR / "main.py"


def load_json(path: Path):
    return json.loads(path.read_text(encoding="utf-8"))


def load_config():
    return load_criteria(CRITERIA_PATH)


def load_proposals():
    data = load_json(SAMPLE_DATA_PATH)
    return data["proposals"]


def find(proposals, pid):
    for p in proposals:
        if p["id"] == pid:
            return p
    raise AssertionError(f"Proposal {pid} not found")


class TestConfiguration(unittest.TestCase):
    def test_valid_config_loads(self):
        config = load_config()
        self.assertEqual(config.config_id, "solar-triage-windsor-2026-v1")
        self.assertAlmostEqual(config.total_weight(), 100.0)

    def test_invalid_weights_rejected(self):
        raw = load_json(CRITERIA_PATH)
        raw["weighted_criteria"][0]["weight"] = 50
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(raw, f)
            tmp = Path(f.name)
        try:
            with self.assertRaises(ConfigError):
                load_criteria(tmp)
        finally:
            tmp.unlink()

    def test_missing_required_fields_rejected(self):
        raw = load_json(CRITERIA_PATH)
        del raw["weighted_criteria"]
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(raw, f)
            tmp = Path(f.name)
        try:
            with self.assertRaises(ConfigError):
                load_criteria(tmp)
        finally:
            tmp.unlink()

    def test_weights_must_be_numeric_non_negative(self):
        raw = load_json(CRITERIA_PATH)
        raw["weighted_criteria"][0]["weight"] = -5
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(raw, f)
            tmp = Path(f.name)
        try:
            with self.assertRaises(ConfigError):
                load_criteria(tmp)
        finally:
            tmp.unlink()


class TestEligibility(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.proposals = load_proposals()

    def test_a_passes_mandatory_gates(self):
        result = evaluate_mandatory(find(self.proposals, "A"), self.config.mandatory_rules)
        self.assertTrue(result.eligible)
        self.assertEqual(result.results[0].state, PASS)  # M1
        self.assertEqual(result.results[1].state, PASS)  # M2

    def test_b_ineligible_bidder_licence_not_established(self):
        result = evaluate_mandatory(find(self.proposals, "B"), self.config.mandatory_rules)
        self.assertFalse(result.eligible)
        m1 = result.results[0]
        self.assertEqual(m1.state, FAIL)
        self.assertIn("licence", m1.reason.lower())

    def test_e_passes_mandatory_gates(self):
        result = evaluate_mandatory(find(self.proposals, "E"), self.config.mandatory_rules)
        self.assertTrue(result.eligible)

    def test_missing_wsib_or_insurance_not_pass(self):
        proposal = copy.deepcopy(find(self.proposals, "A"))
        proposal["mandatory"]["wsib_clearance"] = None
        result = evaluate_mandatory(proposal, self.config.mandatory_rules)
        self.assertFalse(result.eligible)
        m2 = result.results[1]
        self.assertNotEqual(m2.state, PASS)

    def test_price_above_budget_not_compliant_rank(self):
        proposal = copy.deepcopy(find(self.proposals, "A"))
        proposal["price"]["amount_cad"] = 300000
        proposal["price"]["within_budget"] = False
        config = load_config()
        scored = score_proposal(proposal, evaluate_mandatory(proposal, config.mandatory_rules), config)
        apply_price_normalization([scored], config)
        self.assertFalse(scored.rankable)
        self.assertEqual(scored.status, "flagged")

    def test_timeline_beyond_max_not_compliant_rank(self):
        proposal = copy.deepcopy(find(self.proposals, "A"))
        proposal["timeline"]["weeks"] = 20
        proposal["timeline"]["within_max"] = False
        config = load_config()
        scored = score_proposal(proposal, evaluate_mandatory(proposal, config.mandatory_rules), config)
        self.assertFalse(scored.rankable)
        self.assertEqual(scored.status, "flagged")

    def test_missing_evidence_not_fabricated_score(self):
        proposal = copy.deepcopy(find(self.proposals, "C"))
        config = load_config()
        eligibility = evaluate_mandatory(proposal, config.mandatory_rules)
        scored = score_proposal(proposal, eligibility, config)
        self.assertIsNone(scored.components["experience"].score)
        self.assertFalse(scored.rankable)


class TestFlags(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.proposals = load_proposals()

    def test_d_flagged_unknown_timeline(self):
        result = evaluate_mandatory(find(self.proposals, "D"), self.config.mandatory_rules)
        self.assertTrue(result.eligible)
        scored = score_proposal(find(self.proposals, "D"), result, self.config)
        self.assertFalse(scored.rankable)
        self.assertEqual(scored.status, "flagged")
        self.assertIsNone(scored.components["timeline"].score)

    def test_c_flagged_uncertain_experience(self):
        result = evaluate_mandatory(find(self.proposals, "C"), self.config.mandatory_rules)
        self.assertTrue(result.eligible)
        scored = score_proposal(find(self.proposals, "C"), result, self.config)
        self.assertFalse(scored.rankable)
        self.assertEqual(scored.status, "flagged")
        self.assertIsNone(scored.components["experience"].score)

    def test_experience_window_policy_consistent(self):
        # Year-only evidence ("since 2021"/"since 2020"/"during the last five
        # years") cannot establish a qualifying count within a rolling five-year
        # window without an evaluation date and per-installation dates. The same
        # standard applies to A, C, D, and E: all four have unscored experience.
        for pid in ("A", "C", "D", "E"):
            scored = score_proposal(
                find(self.proposals, pid),
                evaluate_mandatory(find(self.proposals, pid), self.config.mandatory_rules),
                self.config,
            )
            self.assertIsNone(
                scored.components["experience"].score,
                f"{pid} experience should be unscored (year-only evidence, no window cutoff)",
            )
            self.assertFalse(scored.rankable)
            self.assertEqual(scored.status, "flagged")

        # A proposal with verified qualifying installations can be scored.
        verified = copy.deepcopy(find(self.proposals, "A"))
        verified["experience"] = {
            "stated_installations": 14,
            "capacity_kw_min": 100,
            "window_years": 5,
            "qualifying_count": 14,
            "window_established": True,
            "evidence": "14 verified installations within the window.",
            "status": "verified",
        }
        scored = score_proposal(
            verified,
            evaluate_mandatory(verified, self.config.mandatory_rules),
            self.config,
        )
        self.assertEqual(scored.components["experience"].score, 100.0)
        self.assertTrue(scored.rankable)


class TestPromptInjection(unittest.TestCase):
    def setUp(self):
        self.config = load_config()
        self.proposals = load_proposals()

    def test_prompt_injection_does_not_change_criteria_or_ranking(self):
        raw = load_json(SAMPLE_DATA_PATH)
        d = find(raw["proposals"], "D")
        self.assertTrue(d.get("prompt_injection"), "fixture should mark prompt injection")
        # The injected text must not alter config or scoring
        scored = score_proposal(d, evaluate_mandatory(d, self.config.mandatory_rules), self.config)
        apply_price_normalization([scored], self.config)
        # D remains flagged due to unknown timeline, not ranked first
        self.assertFalse(scored.rankable)
        self.assertEqual(scored.status, "flagged")


class TestDeterminism(unittest.TestCase):
    def test_identical_inputs_produce_identical_output(self):
        config = load_config()
        proposals = load_proposals()
        scored1 = [score_proposal(p, evaluate_mandatory(p, config.mandatory_rules), config) for p in proposals]
        apply_price_normalization(scored1, config)
        from ranking import rank_proposals
        ranked1 = rank_proposals(scored1, config)

        scored2 = [score_proposal(p, evaluate_mandatory(p, config.mandatory_rules), config) for p in proposals]
        apply_price_normalization(scored2, config)
        ranked2 = rank_proposals(scored2, config)

        self.assertEqual(
            [(r.proposal_id, r.rank, r.status, r.score) for r in ranked1],
            [(r.proposal_id, r.rank, r.status, r.score) for r in ranked2],
        )


class TestConfigChange(unittest.TestCase):
    def test_changing_weight_changes_result(self):
        config = load_config()
        fully_evidenced = {
            "mandatory": {
                "bidder_licence_stated": True,
                "licence_number": "ECRA/ESA #0000000",
                "wsib_clearance": True,
                "liability_insurance_cad": 5000000,
            },
            "experience": {
                "stated_installations": 7,
                "capacity_kw_min": 100,
                "window_years": 5,
                "qualifying_count": 7,
                "window_established": True,
                "evidence": "7 verified installations within window.",
                "status": "verified",
            },
            "price": {
                "amount_cad": 230000,
                "within_budget": True,
                "evidence": "Price CAD 230,000.",
                "status": "verified",
            },
            "timeline": {
                "weeks": 10,
                "within_max": True,
                "evidence": "Completion in 10 weeks.",
                "status": "verified",
            },
            "warranty": {
                "panel_years": 25,
                "workmanship_years": 10,
                "evidence": "Panel 25y, workmanship 10y.",
                "status": "verified",
            },
            "team_approach": {
                "named_lead": True,
                "crew": "Six-person crew",
                "safety_plan": True,
                "monitoring": "12 months monitoring",
                "evidence": "Full team and approach.",
                "status": "verified",
            },
        }

        def total_for(cfg):
            p = dict(fully_evidenced, id="X")
            scored = score_proposal(
                p, evaluate_mandatory(p, cfg.mandatory_rules), cfg
            )
            apply_price_normalization([scored], cfg)
            return scored.total_score

        base_score = total_for(config)

        modified = copy.deepcopy(load_json(CRITERIA_PATH))
        # Swap experience and price weights
        for c in modified["weighted_criteria"]:
            if c["id"] == "experience":
                c["weight"] = 25
            if c["id"] == "price":
                c["weight"] = 30
        with tempfile.NamedTemporaryFile("w", suffix=".json", delete=False) as f:
            json.dump(modified, f)
            tmp = Path(f.name)
        try:
            mod_config = load_criteria(tmp)
            mod_score = total_for(mod_config)
        finally:
            tmp.unlink()

        self.assertNotEqual(base_score, mod_score)


class TestTieBreaks(unittest.TestCase):
    def test_ties_follow_documented_rules(self):
        # Two identical fully-evidenced proposals tie on score; tie-break falls
        # through to stable proposal identifier ordering.
        config = load_config()
        base = {
            "mandatory": {
                "bidder_licence_stated": True,
                "licence_number": "ECRA/ESA #0000000",
                "wsib_clearance": True,
                "liability_insurance_cad": 5000000,
            },
            "experience": {
                "stated_installations": 7,
                "capacity_kw_min": 100,
                "window_years": 5,
                "qualifying_count": 7,
                "window_established": True,
                "evidence": "7 verified installations within window.",
                "status": "verified",
            },
            "price": {
                "amount_cad": 230000,
                "within_budget": True,
                "evidence": "Price CAD 230,000.",
                "status": "verified",
            },
            "timeline": {
                "weeks": 10,
                "within_max": True,
                "evidence": "Completion in 10 weeks.",
                "status": "verified",
            },
            "warranty": {
                "panel_years": 25,
                "workmanship_years": 10,
                "evidence": "Panel 25y, workmanship 10y.",
                "status": "verified",
            },
            "team_approach": {
                "named_lead": True,
                "crew": "Six-person crew",
                "safety_plan": True,
                "monitoring": "12 months monitoring",
                "evidence": "Full team and approach.",
                "status": "verified",
            },
        }
        p1 = dict(base, id="X", name="Synthetic X")
        p2 = dict(base, id="Z", name="Synthetic Z")
        proposals = [p1, p2]
        scored = [
            score_proposal(p, evaluate_mandatory(p, config.mandatory_rules), config)
            for p in proposals
        ]
        apply_price_normalization(scored, config)
        from ranking import rank_proposals
        ranked = rank_proposals(scored, config)
        ranks = {r.proposal_id: r.rank for r in ranked if r.status == "ranked"}
        self.assertEqual(ranks["X"], 1)
        self.assertEqual(ranks["Z"], 2)


class TestOutputSemantics(unittest.TestCase):
    def test_output_contains_all_five_proposals(self):
        proposals = load_proposals()
        ids = {p["id"] for p in proposals}
        self.assertEqual(ids, {"A", "B", "C", "D", "E"})

    def test_ranking_uses_only_required_status_values(self):
        config = load_config()
        proposals = load_proposals()
        scored = [
            score_proposal(p, evaluate_mandatory(p, config.mandatory_rules), config)
            for p in proposals
        ]
        apply_price_normalization(scored, config)
        from ranking import rank_proposals
        ranked = rank_proposals(scored, config)
        valid = {"ranked", "flagged", "ineligible"}
        for r in ranked:
            self.assertIn(r.status, valid)

    def test_unranked_proposals_have_null_rank_and_score(self):
        config = load_config()
        proposals = load_proposals()
        scored = [
            score_proposal(p, evaluate_mandatory(p, config.mandatory_rules), config)
            for p in proposals
        ]
        apply_price_normalization(scored, config)
        from ranking import rank_proposals
        ranked = rank_proposals(scored, config)
        for r in ranked:
            if r.status != "ranked":
                self.assertIsNone(r.rank)
                self.assertIsNone(r.score)

    def test_scored_proposals_have_finite_scores_in_range(self):
        config = load_config()
        proposals = load_proposals()
        scored = [
            score_proposal(p, evaluate_mandatory(p, config.mandatory_rules), config)
            for p in proposals
        ]
        apply_price_normalization(scored, config)
        import math
        for s in scored:
            if s.total_score is not None:
                self.assertTrue(math.isfinite(s.total_score))
                self.assertGreaterEqual(s.total_score, 0)
                self.assertLessEqual(s.total_score, 100)


class TestCLI(unittest.TestCase):
    def test_cli_execution_works(self):
        with tempfile.TemporaryDirectory() as tmp:
            out = Path(tmp) / "ranking.json"
            result = subprocess.run(
                [sys.executable, str(MAIN_PATH),
                 "--proposals", str(SAMPLE_DATA_PATH),
                 "--criteria", str(CRITERIA_PATH),
                 "--output", str(out)],
                capture_output=True, text=True,
            )
            self.assertEqual(result.returncode, 0, f"CLI failed: {result.stderr}")
            self.assertTrue(out.is_file())
            data = json.loads(out.read_text(encoding="utf-8"))
            self.assertIn("proposals", data)
            ids = {r["proposal"] for r in data["proposals"]}
            self.assertEqual(ids, {"A", "B", "C", "D", "E"})

    def test_cli_errors_nonzero_exit(self):
        with tempfile.TemporaryDirectory() as tmp:
            bad = Path(tmp) / "bad.json"
            bad.write_text("{invalid json", encoding="utf-8")
            result = subprocess.run(
                [sys.executable, str(MAIN_PATH),
                 "--proposals", str(bad),
                 "--criteria", str(CRITERIA_PATH),
                 "--output", str(Path(tmp) / "out.json")],
                capture_output=True, text=True,
            )
            self.assertNotEqual(result.returncode, 0)

    def test_no_api_key_or_network_required(self):
        # Default tests import only stdlib + local modules; no network.
        import os
        self.assertNotIn("API_KEY", os.environ)


class TestRankingOutcome(unittest.TestCase):
    def test_experience_flags_consistent_across_proposals(self):
        # A ("since 2021"), C ("since 2020"), and E ("since 2021") all use
        # year-only evidence, so none can have experience verified within a
        # rolling five-year window without an evaluation date. All three are
        # flagged on experience; D is flagged on timeline; B is ineligible on
        # the mandatory bidder-licence gate. No proposal is ranked.
        config = load_config()
        proposals = load_proposals()
        scored = [
            score_proposal(p, evaluate_mandatory(p, config.mandatory_rules), config)
            for p in proposals
        ]
        apply_price_normalization(scored, config)
        from ranking import rank_proposals
        ranked = rank_proposals(scored, config)
        statuses = {r.proposal_id: r.status for r in ranked}
        self.assertEqual(statuses["B"], "ineligible")
        self.assertEqual(statuses["A"], "flagged")
        self.assertEqual(statuses["C"], "flagged")
        self.assertEqual(statuses["E"], "flagged")
        self.assertEqual(statuses["D"], "flagged")
        self.assertEqual([r.proposal_id for r in ranked if r.status == "ranked"], [])

    def test_synthetic_fully_evidenced_proposal_can_be_ranked(self):
        # A proposal that passes mandatory gates and has fully verified
        # components (including experience) can receive a score and rank.
        config = load_config()
        fully_evidenced = {
            "id": "X",
            "name": "Synthetic",
            "mandatory": {
                "bidder_licence_stated": True,
                "licence_number": "ECRA/ESA #0000000",
                "wsib_clearance": True,
                "liability_insurance_cad": 5000000,
            },
            "experience": {
                "stated_installations": 7,
                "capacity_kw_min": 100,
                "window_years": 5,
                "qualifying_count": 7,
                "window_established": True,
                "evidence": "7 verified installations within window.",
                "status": "verified",
            },
            "price": {
                "amount_cad": 230000,
                "within_budget": True,
                "evidence": "Price CAD 230,000.",
                "status": "verified",
            },
            "timeline": {
                "weeks": 10,
                "within_max": True,
                "evidence": "Completion in 10 weeks.",
                "status": "verified",
            },
            "warranty": {
                "panel_years": 25,
                "workmanship_years": 10,
                "evidence": "Panel 25y, workmanship 10y.",
                "status": "verified",
            },
            "team_approach": {
                "named_lead": True,
                "crew": "Six-person crew",
                "safety_plan": True,
                "monitoring": "12 months monitoring",
                "evidence": "Full team and approach.",
                "status": "verified",
            },
        }
        scored = score_proposal(
            fully_evidenced,
            evaluate_mandatory(fully_evidenced, config.mandatory_rules),
            config,
        )
        apply_price_normalization([scored], config)
        self.assertTrue(scored.rankable)
        self.assertEqual(scored.status, "ranked")
        self.assertIsNotNone(scored.total_score)
        self.assertGreaterEqual(scored.total_score, 0)
        self.assertLessEqual(scored.total_score, 100)


if __name__ == "__main__":
    unittest.main()
