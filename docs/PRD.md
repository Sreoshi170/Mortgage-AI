# Mortgage Pre-Check AI product requirements

## Product purpose

Mortgage Pre-Check AI is a research-only application workflow for collecting a
synthetic loan application, reviewing supporting-document evidence, running a
bounded pre-check graph, and presenting traceable findings to a human reviewer.
It does not approve or deny real applicants and does not claim that an HMDA
historical outcome model measures creditworthiness.

## Runtime user workflow

1. The user enters a structured, non-sensitive application: individual or joint
   application status, requested loan amount and purpose, loan type, annual
   income and income type, monthly debt obligations, reported debt-to-income
   ratio, property value/type/unit count, and occupancy. Co-applicant income
   fields appear only when a co-applicant is present. Names, contact details,
   government identifiers, protected characteristics, and free-form sensitive
   narratives are not collected.
2. The user may upload a supporting document such as synthetic income,
   employment, bank-statement, or property evidence. The runtime upload is separate
   from historical HMDA and LendingClub datasets.
3. The backend validates filename, media type, size, encoding, and extractable
   text. Before the extraction worker sees it, only labeled allowlisted fact
   lines are retained. The upload is identified by a SHA-256 digest; original
   document contents are not written to audit logs.
4. The existing extraction worker returns supported facts with source, line
   location when available, confidence, validation findings, and missing evidence.
5. The frontend shows a review step. The user can correct extracted values and
   confirm them before the pre-check runs.
6. The confirmed application and sanitized document enter the existing bounded
   LangGraph: Extraction, Policy-Check, Decision-Narrative, and Fairness-Check.
7. The result shows extracted facts, provenance, validation findings, policy
   flags, missing evidence, research-only recommendation text, human-review
   status, and structured audit events.

## Required safety behavior

- Synthetic mode remains available through the existing deterministic fixture.
- HMDA and LendingClub files remain offline research data and are never runtime
  upload inputs.
- Protected demographic fields are rejected at the worker boundary and are not
  passed to ordinary workers, prompts, or general logs.
- Historical HMDA `action_taken` is not a runtime applicant field and is not a
  live approval target.
- Unsupported, oversized, malformed, or empty documents fail safely with a
  typed error.
- Inconsistent document facts and inconsistencies between reported DTI and
  monthly debt/income are surfaced for human review; structured values remain
  reviewable and are not silently overwritten by document text.
- A successful graph run is a non-final research pre-check, never an automatic
  approval or denial.

## Research data policy

The prepared HMDA dataset and approved Phase 4 `action_taken=1` versus `3`
experiment remain offline research artifacts. The raw 2025 HMDA files and
LendingClub files are documented in
`reports/data/runtime_dataset_inventory.md`. They are not individual borrower
upload formats and are not connected to live recommendations.
