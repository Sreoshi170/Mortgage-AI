# Known Limitations

**Date:** 2026-11-05  
**System:** Mortgage Pre-Check AI — Phase 2 Foundation

This document records every identified limitation of the current system. Each limitation is documented with its scope, impact, and any mitigation already in place.

---

## LIM-001: Fairness Evaluation Is Not Possible at Runtime

**Scope:** Fairness worker  
**Category:** By design  
**Severity:** Disclosure only

The runtime fairness worker cannot perform demographic group-fairness analysis because protected demographic evaluation data (race, ethnicity, sex, etc.) is intentionally not collected, not passed to workers, and not part of the runtime schema. The boundary layer enforces this exclusion.

**Current behavior:** `fairness.status = "not_evaluable"` for every runtime case. The concern message explains: *"No authorized demographic evaluation ran because demographic evaluation data is intentionally unavailable to this worker. This is not evidence of fairness."*

**Mitigation:** The `WorkerSet` interface allows injecting an authorized, separately governed fairness worker for offline evaluation. The `evaluation_only/` data directory is reserved for this purpose and is never read by runtime routes.

**Impact:** Every runtime response discloses this limitation. It is NOT treated as a review trigger.

---

## LIM-002: No Invented Lending Thresholds

**Scope:** Policy worker  
**Category:** By design  
**Severity:** Operational — caller must supply limits

The default `PipelineConfig` has `policy_dti_max=None` and `policy_ltv_max=None`. Without explicit configuration, POL-001 (DTI limit) and POL-002 (LTV limit) do not appear in policy checks.

**Current behavior:** Default configuration → no policy threshold rules run. Only documentation quality rules (DOC-001 through DOC-004) run.

**Mitigation:** Callers supply configured limits via `PipelineConfig(policy_dti_max=X, policy_ltv_max=Y)`. No lending threshold is fabricated from dataset inspection.

**Impact:** A clean application with default config will not have POL-001/POL-002 results. This is correct and documented.

---

## LIM-003: Single-Document Contract Only

**Scope:** Upload API  
**Category:** Product gap  
**Severity:** Medium

The current API accepts exactly one supporting document per pre-check request. Cross-document comparison (e.g., tax returns vs. pay stubs) is not supported.

**Current behavior:** Attempting to submit multiple documents returns 422 (rejected by Pydantic because `supporting_document` is typed as a single object, not a list).

**Impact:** Multi-document conflict detection is not available. Users needing multi-document analysis must submit sequentially.

---

## LIM-004: `income_type` Required by Extraction Despite Being Optional in API

**Scope:** Extraction worker, `PrecheckRequest` schema  
**Category:** Contract gap  
**Severity:** Low — UX confusion only

The extraction worker treats `income_type` as a required field for a complete pre-check (`missing_fields`). However, `PrecheckRequest.income_type` has `default=None`, making it technically optional at the HTTP layer.

**Current behavior:** A request without `income_type` → `documentation_incomplete` → `needs_human_review`.

**Mitigation:** The frontend form always provides `income_type` via a required `<select>` with a default value of "employment". The gap only affects direct API callers.

---

## LIM-005: Deterministic/Template Narratives Only

**Scope:** Decision narrative worker  
**Category:** Implementation scope  
**Severity:** Low

The decision narrative worker is deterministic and template-based. It does not use an LLM to generate explanations. Narratives are accurate and evidence-grounded but follow fixed templates.

**Current behavior:** Narratives are correct, non-final, and evidence-linked. They are not prose-rich but are unambiguous.

**Impact:** No LLM costs or latency. No risk of hallucinated explanations. Limited narrative variation.

---

## LIM-006: DTI Bucket Values (`>60%`) Don't Trigger Numeric POL-001

**Scope:** Policy worker, extraction worker  
**Category:** Documented behavior  
**Severity:** Low

If `debt_to_income_ratio` is a non-numeric string (e.g., `">60%"`) that matches the HMDA bucket format, the extraction worker sets `debt_to_income_bucket = ">60%"`. The policy worker handles this via:

```python
if extraction.summary.debt_to_income_bucket == ">60%":
    flags.append("POL-001")
```

Other non-numeric DTI strings (e.g., `"not-applicable"`) are preserved as `debt_to_income_bucket` with no numeric comparison possible.

**Impact:** A non-numeric DTI that is not `">60%"` will not trigger POL-001. This is expected and documented.

---

## LIM-007: No Report Generation or Export

**Scope:** Frontend, API  
**Category:** Product gap  
**Severity:** Low

The system exposes pipeline explanations, audit traces, and worker results in the browser. It does not provide a downloadable PDF, structured report, or export API endpoint.

**Impact:** Users who need a persistent record must copy the displayed results manually.

---

## LIM-008: No Persistent Storage

**Scope:** Backend service  
**Category:** Architecture  
**Severity:** Medium for production use

Pre-check runs are not persisted. The backend is stateless. Review tokens are HMAC-signed and time-limited (30 minutes) but held in memory only. A backend restart invalidates all in-flight review tokens.

**Impact:** Cannot re-load past runs. Cannot audit historical runs without external log capture.

---

## LIM-009: Regex-Based Fact Extraction May Miss Unusual Document Formats

**Scope:** Extraction worker  
**Category:** Technical  
**Severity:** Low

Document fact extraction uses regex patterns that match labeled facts (e.g., `"Loan Amount: 250000"`). PDF documents with unusual text layouts (multi-column, rotated text, image-scanned without OCR) may not yield extractable facts.

**Current behavior:** `document_no_extractable_facts` warning → `missing_evidence = ["document_relevant_facts"]` → `documentation_incomplete`.

**Mitigation:** The structured application values are authoritative. Document facts only provide supporting evidence, never replace reviewed values.

---

## LIM-010: No Duplicate Detection or Stale State Prevention Across Requests

**Scope:** Backend service  
**Category:** Architecture  
**Severity:** Low

The backend does not track previously seen documents or cases. Submitting the same document twice produces two independent runs with different `document_id` values and the same `sha256`. There is no cross-run contamination.

**Impact:** No stale state. Each run is fully independent. However, duplicate uploads are not detected as such unless the caller compares hashes.

---

## LIM-011: Browser Automation Not Available for Automated Testing

**Scope:** Test suite  
**Category:** Test coverage  
**Severity:** Low

The test suite does not include browser-driven integration tests (e.g., Selenium, Playwright). Frontend behavior has been verified by code inspection and manual test steps documented in `tests/MORTGAGE_PRECHECK_TEST_MATRIX.md`.

---

## LIM-012: httpx Deprecation Warning

**Scope:** Test suite  
**Category:** Third-party library  
**Severity:** None

```
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated;
install `httpx2` instead.
```

This is a third-party deprecation notice. It does not affect test correctness or production behavior. Upgrading to `httpx2` will resolve the warning.
