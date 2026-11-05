from backend.service import demo_request, demo_run_payload, run_payload
from pathlib import Path


FRONTEND_ROOT = Path(__file__).parents[1] / "frontend"


def test_frontend_demo_is_backed_by_real_pipeline_result():
    request = demo_request()
    payload = demo_run_payload()

    assert request["synthetic_document"]["label"] == "SYNTHETIC"
    assert payload["case_id"] == "demo-phase2-001"
    assert payload["status"] == "completed"
    assert payload["gate_status"] == "not_run"
    assert payload["recommendation"] == "proceed"
    assert payload["fairness"]["status"] == "not_evaluable"
    assert {event["node"] for event in payload["audit_events"] if event["event_type"] == "worker_completed"} == {
        "extraction_worker",
        "policy_check_worker",
        "decision_narrative_worker",
        "fairness_check_worker",
    }


def test_dynamic_payload_runs_through_backend_and_preserves_boundary():
    payload = demo_request()
    payload["case_id"] = "dynamic-case-001"
    payload["application"]["loan_amount"] = "250000"

    result = run_payload(payload)

    assert result["case_id"] == "dynamic-case-001"
    assert result["extraction"]["summary"]["loan_amount"] == 250000.0
    assert result["status"] == "needs_human_review"


def test_dynamic_payload_rejects_protected_fields_without_echoing_values():
    payload = demo_request()
    payload["application"]["race"] = "SensitiveValue"

    result = run_payload(payload)

    assert result["status"] == "failed"
    assert result["failure"]["code"] == "protected_field_detected"
    assert "SensitiveValue" not in str(result)


def test_frontend_exposes_upload_review_and_runtime_result_contract():
    html = (FRONTEND_ROOT / "index.html").read_text(encoding="utf-8")
    javascript = (FRONTEND_ROOT / "app.js").read_text(encoding="utf-8")
    assert 'id="supporting-document-file"' in html
    assert 'id="review-panel"' in html
    assert 'id="review-extracted-facts"' in html
    assert "/api/precheck/extract" in javascript
    assert "/api/precheck/review" in javascript
    assert "validation-findings" in html
    assert "extracted-facts" in javascript
    assert "reviewPanel.dataset.initialValues" in javascript
    assert "reviewPanel.dataset.reviewToken" in javascript
    assert "form changed after extraction" in javascript
    assert "Document-extracted facts" in html
    assert "factValue" not in javascript
    assert "logUploadDiagnostic" in javascript
    assert "extracted_field_names" in javascript
    assert "request_prepared" in javascript
    assert "reviewedDocumentFile" in javascript
    assert "selected document changed after extraction" in javascript
    assert 'name="loan_purpose"' in html
    assert 'name="income_type"' in html
    assert 'name="monthly_debt_obligations"' in html
    assert 'name="property_value"' in html
    assert 'name="occupancy_type"' in html
    assert 'id="co-applicant-present"' in html
    assert "updateCoApplicantFields" in javascript
