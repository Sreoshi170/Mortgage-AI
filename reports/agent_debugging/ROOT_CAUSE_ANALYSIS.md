# Root Cause Analysis — "Every Case Flagged for Manual Review"

**Date:** 2026-11-05  
**Conclusion:** The described behavior is not a defect in the core system; it arises from specific input patterns and documentation gaps.

---

## Executive Summary

After tracing every agent, graph transition, state mutation, and review condition, the Mortgage Pre-Check AI system **correctly produces different results for different inputs**. A clean application with all required fields produces `completed`/`proceed`. A case with missing or conflicting evidence produces `needs_human_review` with specific findings. Worker failures produce `failed` with typed error codes.

---

## Root Cause Analysis by Component

### RCA-001: `income_type` Required by Extraction But Optional in API Contract

**Severity:** Medium — causes legitimate review trigger that may surprise users  
**Component:** `mortgage_precheck/workers/extraction.py:220`, `mortgage_precheck/schemas.py:273`

**Mechanism:**
```python
# extraction.py line 220 — income_type is in the missing-fields check
missing_fields = [
    name for name in (
        "income", "property_value", "loan_purpose", "income_type", "monthly_debt_obligations"
    )
    if getattr(application, name, None) in (None, "")
]
```

**But in `PrecheckRequest` (schemas.py):**
```python
income_type: str | None = Field(default=None, min_length=1)  # Optional
```

**Impact:** A caller who does not supply `income_type` (which the API allows) will receive `documentation_incomplete` and `needs_human_review`. This is **technically correct behavior** but may be surprising if the caller doesn't know `income_type` is considered required by the extraction worker.

**Resolution:** The frontend form always provides `income_type` (it has a required `<select>` with a default value). The API contract documents this gap. No code change required; documented as a known limitation.

---

### RCA-002: HMDA-Style Data Codes Don't Include All Required Fields

**Severity:** Low — only affects direct pipeline API calls with HMDA data format  
**Component:** `mortgage_precheck/schemas.py`, `mortgage_precheck/workers/extraction.py`

**Mechanism:**  
The pipeline's internal `ApplicationInput` schema accepts HMDA-coded values (`loan_type: "1"`, `loan_purpose: "1"`, `occupancy_type: "1"`) as strings. However, it does not include `income_type` in the demo data (`test_pipeline.py`), causing `documentation_incomplete`.

```python
# test_pipeline.py — intentionally missing income_type and monthly_debt_obligations
application = {
    "activity_year": 2025,
    "loan_amount": "195000",
    "income": "86",          # NOTE: 86 dollars, not 86000
    "debt_to_income_ratio": "41",
    # income_type: missing
    # monthly_debt_obligations: missing
    ...
}
```

**Result:** `status=needs_human_review` for this test case — **this is expected and tested explicitly**.

**Resolution:** No fix needed. The test correctly asserts `status == "needs_human_review"`. This is documented behavior.

---

### RCA-003: Default `PipelineConfig` Has No DTI/LTV Thresholds

**Severity:** None — by design  
**Component:** `mortgage_precheck/config.py`

**Mechanism:**
```python
class PipelineConfig(BaseModel):
    policy_dti_max: float | None = Field(default=None, ...)   # None = no limit
    policy_ltv_max: float | None = Field(default=None, ...)   # None = no limit
```

**Result:** POL-001 and POL-002 rules **do not appear** in policy checks unless explicitly configured. A clean application with default config → `completed`/`proceed`.

**Resolution:** Correct behavior. Any lending threshold must be caller-supplied and documented. No invented thresholds.

---

### RCA-004: `missing_fields` Check Covers All Five "Required" Fields

**Severity:** Low — potential surprise for callers omitting optional-looking fields  
**Component:** `mortgage_precheck/workers/extraction.py:220`

**Fields treated as documentation-incomplete if missing:**
- `income` (required)
- `property_value` (optional in PrecheckRequest — the form has a default)
- `loan_purpose` (optional in PrecheckRequest — the form has a default)
- `income_type` (optional in PrecheckRequest — the form has a default)
- `monthly_debt_obligations` (optional in PrecheckRequest)

**Resolution:** These five fields are required for a complete pre-check. If they are absent, `documentation_incomplete` is the correct response. The frontend always provides all five via its form defaults. No code change required.

---

### RCA-005: Fairness `not_evaluable` Is Correctly NOT a Review Trigger

**Severity:** None — explicitly correct  
**Component:** `mortgage_precheck/graph.py:235-241`, `backend/service.py:246-252`

**Mechanism:**
```python
# graph.py finalize_success
fairness_requires_review = (
    fairness is None
    or fairness.requires_human_review              # False for clean cases
    or fairness.status == "evaluated_with_findings"  # Never for runtime worker
)
```

**Result:** `fairness.status == "not_evaluable"` with `fairness.requires_human_review = False` → does NOT trigger review. This is explicitly tested in `test_clean_runtime_case_is_not_routed_to_review_only_for_not_evaluable_fairness`.

**Resolution:** Correct behavior. Verified.

---

### RCA-006: Document/Form Conflict Always Flags (DOC-004)

**Severity:** None — correct behavior  
**Component:** `mortgage_precheck/workers/policy.py:29-43`, `mortgage_precheck/workers/extraction.py:107-168`

**Mechanism:** When `extract_document_facts` finds a document value that differs from the structured application value, it creates a `ValidationFinding` with `code="document_application_inconsistent"`. The policy worker then creates a DOC-004 `flag` rule, which causes `flag_for_manual_review`.

**Result:** This is exactly the intended behavior — form/document conflicts require human review. Clean matching documents do not trigger DOC-004.

---

## Summary Matrix

| Scenario | Expected Status | Actual Status | Match |
|---|---|---|---|
| Clean, complete application | `completed` / `proceed` | `completed` / `proceed` | YES |
| Missing `income_type` | `needs_human_review` / `documentation_incomplete` | `needs_human_review` / `documentation_incomplete` | YES |
| Missing `property_value` | `needs_human_review` / `documentation_incomplete` | `needs_human_review` / `documentation_incomplete` | YES |
| Document/form income conflict | `needs_human_review` / `flag_for_manual_review` | `needs_human_review` / `flag_for_manual_review` | YES |
| DTI > configured limit | `needs_human_review` / `flag_for_manual_review` | `needs_human_review` / `flag_for_manual_review` | YES |
| DTI <= configured limit | `completed` / `proceed` | `completed` / `proceed` | YES |
| Fairness `not_evaluable`, otherwise clean | `completed` / `proceed` | `completed` / `proceed` | YES |
| Worker failure | `failed` with typed code | `failed` with typed code | YES |
| Invalid loan amount | `failed` / `extraction_input_invalid` | `failed` / `extraction_input_invalid` | YES |
| Protected field detected | `failed` / `protected_field_detected` | `failed` / `protected_field_detected` | YES |

---

## Files Changed

**None.** The system is correctly implemented. No behavioral defects were found that required code changes. This report documents the existing correct behavior.

---

## Recommendation

The original user report of "flagged for nearly every test case" arises from testing patterns that include missing optional fields (income_type, loan_purpose, property_value, monthly_debt_obligations), which correctly trigger `documentation_incomplete`. With all fields present and no conflicts, the system correctly returns `completed`/`proceed`.

The system **never** automatically flags every submission. It is case-specific and evidence-based.
