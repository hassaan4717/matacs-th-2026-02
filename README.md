# MATACS Technologies — AI Proposal Triage Design

**Candidate:** Muhammad Hassaan Masood  
**Assessment reference:** MATACS-TH-2026-02  
**Repository:** `matacs-th-2026-02`

---

## Problem statement

Design an AI-assisted workflow for a facilities team evaluating contractor proposals for a 150 kW rooftop commercial solar installation in Windsor, Ontario, Canada.

- Budget ceiling: CAD $260,000
- Required completion: within 16 weeks
- Mandatory contractor eligibility must be evaluated before weighted ranking
- Weighted criteria total exactly 100%
- Final contractor selection remains a human responsibility

The workflow makes evaluation more consistent, auditable, explainable, and efficient — without letting a generative model make unverified compliance decisions.

---

## Design philosophy: AI versus deterministic rules

- **AI role:** Extract facts from unstructured proposal text and associate them with configured criteria. Return evidence quotes, page/section references, and uncertainty states.
- **Deterministic code role:** Validate schema/config, enforce mandatory gates, apply budget and timeline constraints, compute all scores, apply ranking and tie-breaks, and produce machine-readable output.
- **Human role:** Resolve missing/conflicting evidence, review flags, approve criteria changes, and make the final procurement decision.

The AI never calculates a score, changes weights, waives a mandatory rule, or awards the contract.

---

## Architecture

A small, modular Python CLI with no mandatory API key, database, frontend, or external service. Extraction is simulated by structured fixtures (no live model).

Modules: `config.py`, `validation.py`, `eligibility.py`, `scoring.py`, `ranking.py`, `audit.py`, `main.py`, `models.py`.

Workflow diagram: [diagram/workflow.png](diagram/workflow.png)

---

## Repository file structure

```
matacs-th-2026-02/
├── README.md
├── WRITEUP.md
├── PROMPTS.md
├── ranking.json
├── .gitignore
├── diagram/
│   └── workflow.png
└── prototype/
    ├── README.md
    ├── main.py
    ├── models.py
    ├── config.py
    ├── validation.py
    ├── eligibility.py
    ├── scoring.py
    ├── ranking.py
    ├── audit.py
    ├── sample_data.json
    ├── criteria.json
    ├── test_main.py
    └── requirements.txt
```

Key documents:
- [WRITEUP.md](WRITEUP.md) — five-question design response
- [PROMPTS.md](PROMPTS.md) — extraction prompt and model-usage statement
- [ranking.json](ranking.json) — generated output (A–E)
- [diagram/workflow.png](diagram/workflow.png) — workflow diagram
- [prototype/README.md](prototype/README.md) — prototype details

---

## Setup

Requires Python 3.8+. No external dependencies (standard library only).

```bash
# From the repository root
python prototype/main.py --proposals prototype/sample_data.json --criteria prototype/criteria.json --output ranking.json
```

## Test command

```bash
python prototype/test_main.py
```

---

## Expected decision categories and fixture outcomes

Status vocabulary: `ranked`, `flagged`, `ineligible`. Unranked proposals have `null` rank and score.

| Proposal | Status | Reason |
|---|---|---|
| A — Northshore | flagged | Year-only experience evidence ("since 2021") cannot establish qualifying count within a rolling five-year window without an evaluation date |
| E — SunGrid | flagged | Year-only experience evidence ("since 2021") cannot establish qualifying count within a rolling five-year window without an evaluation date |
| C — Lakeview | flagged | Year-only experience evidence ("since 2020") cannot establish qualifying count within a rolling five-year window without an evaluation date |
| D — Essex Green | flagged | Completion timeline unknown (16-week constraint unverified) |
| B — BrightPath | ineligible | Bidder's own Ontario electrical contractor licence not established |

No proposal is ranked: A, C, and E cannot have experience verified from year-only evidence, and D's timeline is unknown. B fails the mandatory bidder-licence gate.

---

## Important assumptions and limitations

- Scoring formulas are proposed design assumptions, documented in the prototype README, not rules supplied by MATACS.
- Extraction is fixture-based; no live LLM was called (see PROMPTS.md).
- Proposal facts are synthetic fixtures, not independent verification of real companies.
- The system provides decision support, not automatic procurement approval.
- No deployment, integration, or external-service testing is claimed.
- A production deployment would additionally require access control, secure storage, retention, monitoring, model/version management, and a review process.

---

## Time spent on assessment

**Actual time spent: Approximately 3 to 4 hours, including requirements analysis, workflow design, prototype implementation, test development, documentation, and final consistency review.**

---

**AI Usage Disclosure**

I used AI assistance during the development of the workflow design, prototype structure, test cases, and documentation. I reviewed the generated suggestions and checked them against the assessment requirements and the implemented behavior rather than accepting them uncritically.

One important issue concerned the five-year experience requirement. The initial implementation treated proposals A and E as sufficiently evidenced while flagging C, even though their experience claims were expressed in year-only terms and no evaluation reference date was configured. I reviewed this inconsistency and applied a consistent evidence standard to proposals A, C, D, and E, ensuring that unsupported experience claims remained unscored until sufficient evidence could establish their eligibility for scoring. I updated the regression test and regenerated `ranking.json` through the CLI.

The prototype uses fixture-based extraction; no live LLM was called at runtime. AI served as a development aid, while the eligibility policy, scoring behavior, and final outputs were subject to review and validation.

---


