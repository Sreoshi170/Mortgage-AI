# Agent Regression Test Report

**Date:** 2026-11-05  
**Test runner:** pytest 8.4.2  
**Python version:** 3.13  
**Result: 256 PASSED, 0 FAILED, 0 SKIPPED, 1 WARNING**

> [!IMPORTANT]
> The warning is a deprecation notice from FastAPI/Starlette advising to install `httpx2` instead of `httpx`. It does not affect any test outcomes.

---

## Test File Summary

| Test File | Tests | Result | Coverage Area |
|---|---|---|---|
| `test_backend_api.py` | 10 | PASS | FastAPI routes, health, schema contracts |
| `test_case01_pdf_upload_regression.py` | 1 | PASS | CASE01 PDF upload regression |
| `test_comprehensive_precheck.py` | 187 | PASS | Full end-to-end API and pipeline coverage |
| `test_frontend.py` | 4 | PASS | Frontend static server |
| `test_hmda_data.py` | 8 | PASS | HMDA dataset availability |
| `test_modeling_design.py` | 6 | PASS | Modeling spec design |
| `test_pipeline.py` | 10 | PASS | LangGraph graph execution |
| `test_readiness.py` | 3 | PASS | ML readiness checks |
| `test_recovery_regressions.py` | 7 | PASS | Fairness routing, review flow, token verification |
| `test_runtime_documents.py` | 9 | PASS | Document upload, PDF extraction, sanitization |
| `test_worker_diagnostic_audit.py` | 11 | PASS | Isolated worker contracts |
| **TOTAL** | **256** | **PASS** | |

---

## Phase 8 Test Matrix Coverage

| Test Case | Test Name | Status | Notes |
|---|---|---|---|
| Clean application, no review trigger | `test_valid_baseline_separates_input_success_from_human_review` | PASS | Returns `completed`/`proceed`/`human_review_required=False` |
| Clean application via pipeline | `test_default_policy_has_no_invented_dti_or_ltv_thresholds` | PASS | Returns `completed`/`proceed` |
| Document/form income conflict | `test_conflicting_form_and_document_facts_are_reported_but_structured_values_remain_authoritative` | PASS | Returns `flag_for_manual_review`; identifies `loan_amount` |
| Multiple document conflicts (Case 01) | `test_case01_pdf_surfaces_all_form_document_discrepancies_before_confirmation` | PASS | Identifies `annual_income`, `monthly_debt_obligations`, `property_value` |
| Missing required income | `test_optional_numeric_fields_can_be_missing_with_current_worker_handling[co_applicant_annual_income-True]` | PASS | `documentation_incomplete` |
| Missing property_value | `test_optional_numeric_fields_can_be_missing_with_current_worker_handling[property_value-True]` | PASS | `documentation_incomplete` |
| Invalid numeric input | `test_each_numeric_field_accepts_valid_and_very_large_values_but_rejects_bad_input` | PASS | 422 validation failure |
| Unsupported document format | `test_unreadable_empty_corrupt_and_unsupported_uploads_fail_with_safe_codes[*.exe/application/octet-stream]` | PASS | `document_file_type_unsupported` |
| Corrupted PDF | `test_unreadable_empty_corrupt_and_unsupported_uploads_fail_with_safe_codes[broken.pdf/application/pdf]` | PASS | `document_pdf_invalid` |
| Policy rule triggered (DTI > limit) | `test_configured_dti_policy_uses_only_the_caller_supplied_boundary[40.01-flag-flag_for_manual_review]` | PASS | POL-001 `flag` |
| Policy rule not triggered (DTI <= limit) | `test_configured_dti_policy_uses_only_the_caller_supplied_boundary[40-pass-proceed]` | PASS | POL-001 `pass` |
| Fairness not_evaluable, clean case | `test_clean_runtime_case_is_not_routed_to_review_only_for_not_evaluable_fairness` | PASS | `completed` despite `not_evaluable` |
| Fairness + document conflict | `test_authorized_fairness_finding_state_routes_to_review_when_supplied_by_a_separate_worker` | PASS | `needs_human_review` from fairness |
| Worker execution failure | `test_each_worker_failure_retries_then_returns_a_typed_safe_failure` | PASS | `failed` with typed code |
| Malformed worker output | `test_malformed_worker_output_is_retried_and_converted_to_typed_failure` | PASS | `failed` |
| All workers succeed, no findings | `test_demo_route_and_frontend_regression_contract_remain_functional` | PASS | `completed` |
| Repeated uploads, no stale state | `test_duplicate_uploads_have_same_hash_but_are_not_silently_collapsed` | PASS | Different `document_id`, same `sha256` |
| User corrects extracted values | `test_review_correction_changes_structured_value_and_marks_reviewer_provenance` | PASS | Reviewer provenance preserved |

---

## Critical Scenario Verification

### Scenario A: Clean Application → `completed`

**Input:**
```json
{
  "loan_amount": 250000, "annual_income": 60000, "income_type": "employment",
  "monthly_debt_obligations": 1900, "loan_type": "conventional",
  "loan_purpose": "purchase", "debt_to_income_ratio": 38,
  "property_value": 300000, "property_type": "single_family",
  "property_units": 1, "occupancy_type": "primary_residence",
  "supporting_document": "Synthetic employment verification letter"
}
```

**Output:**
```
status: completed
policy_check.status: clear
recommendation: proceed
human_review_required: false
fairness_check.status: not_evaluable (NOT a review trigger)
```

**Test:** `test_valid_baseline_separates_input_success_from_human_review` → PASS

---

### Scenario B: Document Income Conflict → `needs_human_review`

**Input:** Same as A, but `supporting_document = "Annual Income: 1200000"`

**Output:**
```
status: needs_human_review
policy.recommendation: flag_for_manual_review
human_review_required: true
validation_findings: [{code: "document_application_inconsistent", field: "annual_income"}]
narrative: "Document/application validation found information requiring human review for: annual_income..."
```

**Test:** `test_conflicting_form_and_document_facts_are_reported_but_structured_values_remain_authoritative` → PASS

---

### Scenario C: Policy DTI Trigger → `needs_human_review`

**Input:** Same as A, `debt_to_income_ratio=50`, `PipelineConfig(policy_dti_max=40)`

**Output:**
```
status: needs_human_review
policy.recommendation: flag_for_manual_review
policy checks: [{rule_id: "POL-001", status: "flag", evidence: "Numeric DTI 50 compared with configured limit 40."}]
```

**Test:** `test_configured_dti_policy_uses_only_the_caller_supplied_boundary` → PASS

---

### Scenario D: Worker Failure → `failed`

**Input:** Same as A, extraction worker always raises RuntimeError

**Output:**
```
status: failed
failure.code: worker_exception
audit_events: worker_started → worker_retry_scheduled → worker_started → worker_failed
```

**Test:** `test_each_worker_failure_retries_then_returns_a_typed_safe_failure` → PASS

---

## Worker Contract Verification

| Worker | Receives Real Inputs | Input-Dependent Output | Valid Schema Returned | Graph Executes It | Downstream Consumes Output | Errors Handled |
|---|---|---|---|---|---|---|
| Extraction | YES | YES | YES | YES | YES (policy) | YES (retried, then failed) |
| Policy | YES | YES | YES | YES | YES (narrative) | YES |
| Narrative | YES | YES | YES | YES | YES (fairness) | YES |
| Fairness | YES | YES | YES | YES | YES (finalize_success) | YES |

---

## Skipped Tests

None. All 256 tests run to completion.

---

## Warnings

```
StarletteDeprecationWarning: Using `httpx` with `starlette.testclient` is deprecated;
install `httpx2` instead.
```

This is a third-party library deprecation warning that does not affect correctness. No action required.

---

## Command

```
python -m pytest tests/ -v --tb=short
Result: 256 passed, 1 warning in 11.07s
```
