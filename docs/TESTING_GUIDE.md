# Testing Guide — Mortgage Pre-Check AI

This guide details the test structure, test matrix, and procedures for running and extending tests for Mortgage Pre-Check AI.

---

## 1. Test Architecture Overview

All tests are located in `tests/` and use standard `pytest` fixtures and the FastAPI `TestClient`.

| Test File | Test Count | Description |
|---|---|---|
| `test_backend_api.py` | 10 | FastAPI endpoint routing, CORS, payload size limits, schema rejection |
| `test_case01_pdf_upload_regression.py` | 1 | Real PDF extraction and multi-field discrepancy detection (`CASE01_baseline.pdf`) |
| `test_comprehensive_precheck.py` | 187 | Parameterized matrices: numeric domains, boundary values, MIME types, retry limits |
| `test_frontend.py` | 4 | Frontend static server, proxying, and file serving |
| `test_hmda_data.py` | 8 | HMDA dataset availability, schema integrity, and boundary compliance |
| `test_modeling_design.py` | 6 | Modeling specifications and offline feature leakage checks |
| `test_pipeline.py` | 10 | LangGraph state transitions, retry loops, timeouts, and boundary error handling |
| `test_readiness.py` | 3 | ML experiment readiness and data split contracts |
| `test_recovery_regressions.py` | 7 | Upload review flow, token tampering, and fairness routing regressions |
| `test_runtime_documents.py` | 9 | Supporting document encoding, SHA-256 digests, and sanitization |
| `test_worker_diagnostic_audit.py` | 11 | Direct unit tests on isolated workers without HTTP / FastAPI layer |

---

## 2. Running Tests

### Run All Tests
```bash
python -m pytest tests/ -v --tb=short
```

### Run a Specific Test Module
```bash
python -m pytest tests/test_worker_diagnostic_audit.py -v
```

### Run Only Regression Tests
```bash
python -m pytest tests/test_recovery_regressions.py tests/test_case01_pdf_upload_regression.py -v
```

---

## 3. Synthetic Test Scenarios

The suite validates that different inputs produce distinct, explainable results:

### Scenario 1: Clean Application (Matching Document)
- **Input**: Complete form values matching document text.
- **Expected Outcome**:
  - `pipeline_trace.status`: `"completed"`
  - `policy.recommendation`: `"proceed"`
  - `human_review_required`: `False`
  - `fairness.status`: `"not_evaluable"` (not a review trigger)
- **Automated Test**: `test_comprehensive_precheck.py::test_valid_baseline_separates_input_success_from_human_review`

### Scenario 2: Document / Form Discrepancy
- **Input**: Form indicates Annual Income of \$60,000, while document indicates \$1,200,000.
- **Expected Outcome**:
  - `pipeline_trace.status`: `"needs_human_review"`
  - `policy.recommendation`: `"flag_for_manual_review"`
  - `human_review_required`: `True`
  - Validation finding: `document_application_inconsistent` on `annual_income`
- **Automated Test**: `test_comprehensive_precheck.py::test_conflicting_form_and_document_facts_are_reported_but_structured_values_remain_authoritative`

### Scenario 3: Missing Required Information
- **Input**: Application omitted `income_type` or `monthly_debt_obligations`.
- **Expected Outcome**:
  - `pipeline_trace.status`: `"needs_human_review"`
  - `policy.recommendation`: `"documentation_incomplete"`
  - `human_review_required`: `True`
  - Extraction `missing_fields`: lists the absent fields
- **Automated Test**: `test_comprehensive_precheck.py::test_optional_numeric_fields_can_be_missing_with_current_worker_handling`

### Scenario 4: Configured Policy Threshold Trigger
- **Input**: DTI of 50%, with `PipelineConfig(policy_dti_max=40)`.
- **Expected Outcome**:
  - `pipeline_trace.status`: `"needs_human_review"`
  - `policy.recommendation`: `"flag_for_manual_review"`
  - Rule `POL-001`: status `"flag"`
- **Automated Test**: `test_comprehensive_precheck.py::test_configured_dti_policy_uses_only_the_caller_supplied_boundary`

### Scenario 5: Worker Failure and Retry Limit
- **Input**: Worker raises unexpected runtime exception.
- **Expected Outcome**:
  - Worker retries up to `max_attempts`
  - `pipeline_trace.status`: `"failed"`
  - `failure.code`: `"worker_exception"`
  - Audit log records each attempt and failure event
- **Automated Test**: `test_comprehensive_precheck.py::test_each_worker_failure_retries_then_returns_a_typed_safe_failure`

---

## 4. Manual Browser Checklist

For manual verification in the UI ([http://127.0.0.1:8765/index.html](http://127.0.0.1:8765/index.html)):

1. **Clean Baseline**:
   - Submit the pre-filled default form with "Synthetic employment verification letter".
   - Verify status shows **Completed** (green badge).
   - Verify Recommendation shows **Proceed**.
   - Verify "No configured policy rule was flagged".

2. **Document Upload & Conflict Review**:
   - Choose `tests/fixtures/documents/CASE01_baseline.pdf`.
   - Click "Submit and run pre-check".
   - Review draft panel appears with 3 conflict warnings (annual income, monthly debt, property value).
   - Form values and document values are shown separately.
   - Click "Confirm reviewed values and run pre-check".
   - Status updates to **Needs human review** with explicit findings.

3. **Value Correction**:
   - Change a conflicting value in the review panel to match the document.
   - Confirm review.
   - Verify provenance in the final result reflects `reviewer_correction`.
