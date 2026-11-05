from __future__ import annotations

from fastapi.testclient import TestClient

from backend.api import app
from backend.service import demo_request

client = TestClient(app)


def test_backend_root_is_visible():
    response = client.get("/")
    assert response.status_code == 200
    assert response.json()["status"] == "ok"
    assert response.json()["run"] == "POST /api/run"


def test_health_contract():
    response = client.get("/api/health")
    assert response.status_code == 200
    health = response.json()
    assert health["status"] == "ok"
    assert health["backend"] == "langgraph"
    assert health["api_version"] == "1"


def test_dynamic_api_executes_graph():
    payload = demo_request()
    payload["case_id"] = "api-integration-001"
    payload["application"]["loan_amount"] = "275000"

    response = client.post("/api/run", json=payload)
    result = response.json()

    assert response.status_code == 200
    assert result["case_id"] == "api-integration-001"
    assert result["status"] == "needs_human_review"
    assert result["extraction"]["summary"]["loan_amount"] == 275000.0
    assert len([event for event in result["audit_events"] if event["event_type"] == "worker_completed"]) == 4


def test_user_submission_returns_complete_four_worker_response():
    payload = demo_request()
    payload["case_id"] = "user-submission-001"
    payload["application"].update({
        "loan_amount": "310000",
        "income": "NA",
        "debt_to_income_ratio": ">60%",
        "conforming_loan_limit": "766550",
        "derived_loan_product_type": "Conventional",
        "derived_dwelling_category": "Single family",
    })
    payload["synthetic_document"]["document_id"] = "user-document-001"
    payload["synthetic_document"]["content"] = "Synthetic supporting document submitted with the case."

    response = client.post("/api/run", json=payload)
    result = response.json()

    assert response.status_code == 200
    assert result["case_id"] == "user-submission-001"
    assert result["extraction"]["summary"]["loan_amount"] == 310000.0
    assert result["extraction"]["summary"]["special_codes"]["income"] == "NA"
    assert result["policy"]["checks"]
    assert result["narrative"]["evidence_rule_ids"]
    assert result["fairness"]["protected_data_seen"] is False
    assert len(result["audit_events"]) >= 4


def test_api_validation_errors_are_explicit():
    response = client.post("/api/run", content=b"not-json", headers={"Content-Type": "application/json"})
    assert response.status_code == 422

    response = client.post("/api/run", json={})
    assert response.status_code == 422


def test_api_protected_field_failure_does_not_echo_value():
    payload = demo_request()
    payload["application"]["race"] = "SensitiveValue"

    response = client.post("/api/run", json=payload)
    result = response.json()

    assert response.status_code == 200
    assert result["status"] == "failed"
    assert result["failure"]["code"] == "protected_field_detected"
    assert "SensitiveValue" not in response.text


def test_compact_precheck_contract_matches_requested_shape():
    response = client.post("/api/precheck", json={
        "loan_amount": 250000,
        "annual_income": 60000,
        "loan_type": "conventional",
        "debt_to_income_ratio": 38,
        "supporting_document": "Synthetic employment verification letter",
    })
    result = response.json()

    assert response.status_code == 200
    assert result["extraction_status"] == "success"
    assert result["policy_check"] == {
        "status": "flagged",
        "reason": "Requires review against configured policy rules",
    }
    assert result["recommendation"] == "flag for manual review"
    assert result["fairness_check"]["status"] == "not_evaluable"
    assert result["human_review_required"] is True
    assert "not a final mortgage approval or denial" in result["explanation"]
    assert result["pipeline_trace"]["extraction"]["summary"]["loan_amount"] == 250000.0


def test_structured_runtime_form_preserves_non_sensitive_application_summary():
    response = client.post("/api/precheck", json={
        "applicant_type": "joint",
        "co_applicant_present": True,
        "co_applicant_annual_income": 40000,
        "co_applicant_income_type": "employment",
        "loan_amount": 250000,
        "annual_income": 60000,
        "income_type": "employment",
        "monthly_debt_obligations": 1900,
        "loan_type": "conventional",
        "loan_purpose": "purchase",
        "debt_to_income_ratio": 38,
        "property_value": 300000,
        "property_type": "single_family",
        "property_units": 1,
        "occupancy_type": "primary_residence",
        "supporting_document": "Synthetic application evidence",
    })

    assert response.status_code == 200
    summary = response.json()["pipeline_trace"]["extraction"]["summary"]
    assert summary["applicant_type"] == "joint"
    assert summary["co_applicant_present"] is True
    assert summary["loan_purpose"] == "purchase"
    assert summary["monthly_debt_obligations"] == 1900.0
    assert summary["property_type"] == "single_family"


def test_joint_application_requires_explicit_co_applicant_presence():
    response = client.post("/api/precheck", json={
        "applicant_type": "joint",
        "loan_amount": 250000,
        "annual_income": 60000,
        "loan_type": "conventional",
        "debt_to_income_ratio": 38,
        "supporting_document": "Synthetic evidence",
    })

    assert response.status_code == 422


def test_runtime_form_rejects_out_of_range_numeric_dti():
    response = client.post("/api/precheck", json={
        "loan_amount": 250000,
        "annual_income": 60000,
        "loan_type": "conventional",
        "debt_to_income_ratio": 101,
        "supporting_document": "Synthetic evidence",
    })

    assert response.status_code == 422

