# Prototype — AI Proposal Triage (Deterministic Policy Engine)

MATACS Technologies — AI Proposal Triage Design  
Reference: MATACS-TH-2026-02  
Candidate: Muhammad Hassaan Masood

## What the prototype does

A local Python CLI that loads versioned criteria and synthetic proposal fixtures, evaluates mandatory eligibility gates, computes deterministic weighted scores, ranks eligible and sufficiently evidenced proposals, records audit events, and writes `ranking.json`. The system provides decision support only — it never awards the contract automatically.

## Architecture and module responsibilities

| Module | Responsibility |
|---|---|
| `config.py` | Loads and validates `criteria.json`; computes config version/hash |
| `validation.py` | Validates proposal fixture structure and duplicate ids |
| `eligibility.py` | Evaluates mandatory gates M1/M2 (PASS/FAIL/UNKNOWN) |
| `scoring.py` | Computes component scores (experience, price, timeline, warranty, team) |
| `ranking.py` | Price normalization, deterministic ranking, tie-breaking |
| `audit.py` | Lightweight audit log for decision provenance |
| `main.py` | CLI orchestration and summary output |
| `models.py` | Data models for results, scores, and audit events |
| `sample_data.json` | Synthetic fixture facts (paraphrases, not proposal prose) |
| `criteria.json` | Versioned policy configuration |
| `test_main.py` | Automated test suite |

## Fixture-based extraction limitation

Extraction is simulated by structured fixtures; no live LLM is called. This limitation is stated prominently in `PROMPTS.md` and here. Do not claim the extraction prompt was executed against a live model.

## Configuration format

`criteria.json` is the single source of policy. It contains schema version, config id, project budget ceiling and max duration, mandatory rules, weighted criteria and weights, experience/target/warranty/team parameters, tie-breaking rules, missing-evidence policy, and rounding policy. Edit this file without changing Python source. Configuration is validated before any proposal is processed; invalid weights or missing fields cause a clear error.

## Scoring formulas and assumptions (proposed, not MATACS-supplied)

- experience_score = 100 × min(verified_qualifying_installations / target, 1)  (target 14)
- price_score = 100 × lowest_eligible_price / proposal_price  (among rankable pool)
- timeline_score = 100 × (max_weeks − proposed_weeks) / max_weeks  (zero at max)
- warranty_score = average of panel and workmanship scores (targets 25y / 12y)
- team_approach_score = weighted rubric (named lead, crew, safety plan, monitoring)
- total_score = weighted sum using config weights (must total 100%)

Weights are read from configuration, not hard-coded. Rounding is applied only for output.

## Eligibility and review-state semantics

Mandatory states: PASS, FAIL, UNKNOWN. A confirmed failure makes a proposal ineligible. Missing/ambiguous evidence is not a pass; it routes to review. Proposal statuses: `ranked`, `flagged`, `ineligible`. Unranked proposals have null rank and score.

## Setup, run, and test commands

From the repository root:

```bash
# Run the CLI (creates root ranking.json)
python prototype/main.py --proposals prototype/sample_data.json --criteria prototype/criteria.json --output ranking.json

# Run the test suite
python prototype/test_main.py
```

Requires Python 3.8+. No external dependencies; standard library only.

## Example output behavior

- A (Northshore): flagged (year-only experience evidence cannot establish qualifying count within a rolling five-year window without an evaluation date), null rank/score
- E (SunGrid): flagged (year-only experience evidence cannot establish qualifying count within a rolling five-year window without an evaluation date), null rank/score
- C (Lakeview): flagged (experience window unverified), null rank/score
- D (Essex Green): flagged (timeline unknown), null rank/score
- B (BrightPath): ineligible (bidder's own licence not established), null rank/score

No proposal is ranked because none of A, C, or E can have experience verified from year-only evidence, and D's timeline is unknown.

## How to modify criteria without changing scoring

Edit `prototype/criteria.json` (weights, targets, budget, window). The engine reads all parameters from config. Changing a weight changes computed results in a controlled, explainable way (covered by tests).

## How the tests protect against prompt injection and missing evidence

- Proposal D's embedded instruction cannot modify criteria or force first place (tested).
- Missing WSIB/insurance evidence is not treated as a pass (tested).
- Missing experience/timeline evidence never becomes a fabricated score (tested).
- Unranked proposals have null rank and score (tested).

## Connecting a real extraction model in the future

Implement an adapter that calls a model with the prompt in `PROMPTS.md`, returns the structured JSON schema, and lets `validation.py`/`scoring.py` validate and use it. Keep it optional and opt-in; default tests must not require network, API keys, or paid calls.
