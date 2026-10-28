# WRITEUP.md

MATACS Technologies — AI Proposal Triage Design
Reference: MATACS-TH-2026-02
Candidate: Muhammad Hassaan Masood

## 1. What should AI do versus what should be handled by deterministic rules?

AI is suitable for extracting information from unstructured proposal text: identifying the contractor's stated licence number, WSIB status, insurance amount, price, timeline, warranties, named lead, crew, safety plan, and monitoring approach, and associating each fact with a configured criterion identifier. Generative extraction is a good fit because proposals arrive as free-form documents with varying wording and layout.

Mandatory eligibility checks and score calculations belong in deterministic code. Rules are exact, auditable, and repeatable: a licence is either stated by the bidder or it is not; weights either sum to 100% or they do not; a price is either within the ceiling or it is not. The AI must not make the final procurement decision because generative models can hallucinate, vary between runs, and cannot be held accountable for compliance. The system supports human decision-making; it does not award the contract.

## 2. How would you keep results consistent and explainable?

Scores are repeatable because every formula is fixed, versioned, and configuration-driven. If the same proposals and criteria are processed twice, the result is identical (verified by the determinism test). A reviewer sees why a proposal ranked where it did through component scores, evidence references, and a concise reason for each record. Evidence references and uncertainty states (verified / unknown / uncertain) make extraction reviewable: a human can trace each scored fact back to the proposal text and confirm or correct it.

Scoring formulas are proposed assumptions, documented in the prototype README, not rules supplied by MATACS. They are kept configurable so an administrator can adjust targets without changing code.

## 3. Where should human oversight occur, and how would decisions be audited?

Human review occurs at: uncertain or conflicting extraction, missing mandatory evidence, borderline eligibility, and material score changes. An authorized human makes the final contractor-selection decision; the system never awards the contract automatically.

An audit trail preserves provenance by recording, for each event: timestamp, proposal id, event type, actor/component, configuration version and hash, processing stage, evidence reference, previous and updated values, and an explanation. System-generated events are clearly distinguished from hypothetical human-review events. An override preserves the original value, revised value, reason, and actor so nothing is silently erased.

## 4. What happens when criteria change after proposals have been submitted?

Configuration changes are versioned: each criteria.json carries a config id and schema version, and a SHA-256 hash is stored in every output and audit record. Historical results remain associated with the criteria under which they were calculated, so prior output never silently appears to have been computed under new rules. When authorized, explicit rescoring recomputes results under the new configuration. A change to mandatory criteria triggers mandatory-criteria eligibility reevaluation for all previously scored proposals.

## 5. What are the main risks, and how would you mitigate them?

Risks include hallucination, extraction mistakes, prompt injection, bias, missing evidence, privacy, security, cost, latency, and audit disputes.

Mitigations: treat proposal text as untrusted data and ignore embedded instructions (prompt injection is tested); validate all extraction output independently in code; never treat a bidder's self-description as independent verification; route missing or ambiguous evidence to human review instead of fabricating scores; keep mandatory gates separate from weighted scores so a cheap proposal cannot compensate for a failed rule; version configuration and hash outputs for auditability; store no secrets in the repository; and run all tests without network access or API keys.

This is a working local prototype. A production deployment would additionally require access control, secure document storage, retention policies, monitoring, model/version management, and a formal review process. Those controls do not exist in the prototype and are not claimed to.

Word count target: approximately 750 words.
