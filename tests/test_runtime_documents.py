from __future__ import annotations

import base64
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api import app
from mortgage_precheck.documents import sanitize_document_text


client = TestClient(app)
FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_employment_verification.txt"


def upload_payload(*, content: bytes | None = None, filename: str = "synthetic_employment_verification.txt", media_type: str = "text/plain"):
    content = FIXTURE.read_bytes() if content is None else content
    return {
        "loan_amount": 250000,
        "annual_income": 60000,
        "loan_type": "conventional",
        "debt_to_income_ratio": 38,
        "supporting_document": {
            "filename": filename,
            "media_type": media_type,
            "content_base64": base64.b64encode(content).decode("ascii"),
        },
    }


def reviewed_payload(payload: dict, *, corrected_fields: list[str] | None = None) -> dict:
    draft = client.post("/api/precheck/extract", json=payload)
    assert draft.status_code == 200, draft.text
    return {
        **payload,
        "review_confirmed": True,
        "corrected_fields": corrected_fields or [],
        "review_token": draft.json()["review_token"],
    }


def test_upload_extraction_returns_reviewable_facts_and_provenance():
    response = client.post("/api/precheck/extract", json=upload_payload())
    assert response.status_code == 200
    result = response.json()
    assert result["review_required"] is True
    assert result["document"]["filename"] == "synthetic_employment_verification.txt"
    assert result["extracted_facts"]["loan_amount"]["value"] == 250000
    assert result["extracted_facts"]["loan_amount"]["provenance"]["source"] == "uploaded_document"
    assert result["extracted_facts"]["loan_amount"]["provenance"]["confidence"] == 0.9


def test_upload_extracts_property_and_debt_facts_with_line_locations():
    content = (
        b"Employment verification\n"
        b"Loan Amount: 250000\n"
        b"Annual Income: 60000\n"
        b"Monthly Debt Obligations: 1900\n"
        b"Property Value: 300000\n"
        b"Loan Purpose: purchase\n"
    )
    payload = upload_payload(content=content)
    payload.update({
        "loan_purpose": "purchase",
        "income_type": "employment",
        "monthly_debt_obligations": 1900,
        "property_value": 300000,
        "property_type": "single_family",
        "property_units": 1,
        "occupancy_type": "primary_residence",
    })
    response = client.post("/api/precheck/extract", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["extracted_facts"]["property_value"]["value"] == 300000
    assert ":line:5" in result["extracted_facts"]["property_value"]["provenance"]["evidence"]
    assert result["extracted_facts"]["loan_purpose"]["value"] == "purchase"


def test_reviewed_upload_runs_the_existing_four_worker_graph():
    payload = reviewed_payload(upload_payload())
    response = client.post("/api/precheck/review", json=payload)
    assert response.status_code == 200
    result = response.json()
    assert result["review_status"] == "reviewed"
    assert result["research_only"] is True
    assert result["pipeline_trace"]["extraction"]["extracted_facts"]["loan_type"]["value"] == "conventional"
    assert {event["node"] for event in result["pipeline_trace"]["audit_events"] if event["event_type"] == "worker_completed"} == {
        "extraction_worker",
        "policy_check_worker",
        "decision_narrative_worker",
        "fairness_check_worker",
    }
    assert result["pipeline_trace"]["fairness"]["protected_data_seen"] is False


def test_upload_type_mismatch_and_review_confirmation_fail_safely():
    bad_type = upload_payload(filename="synthetic.exe", media_type="application/octet-stream")
    response = client.post("/api/precheck/extract", json=bad_type)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "document_file_type_unsupported"

    unconfirmed = upload_payload()
    unconfirmed["review_confirmed"] = False
    response = client.post("/api/precheck/review", json=unconfirmed)
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "review_confirmation_required"


def test_inconsistent_document_values_are_reported_without_using_document_as_authority():
    payload = upload_payload(content=b"Loan Amount: 400000\nAnnual Income: 60000\n")
    draft = client.post("/api/precheck/extract", json=payload)
    assert draft.status_code == 200
    findings = draft.json()["validation_findings"]
    assert any(finding["code"] == "document_application_inconsistent" for finding in findings)


def test_inconsistent_derived_dti_is_reported_for_human_review():
    payload = upload_payload()
    payload.update({
        "income_type": "employment",
        "monthly_debt_obligations": 500,
        "property_value": 300000,
        "loan_purpose": "purchase",
        "property_type": "single_family",
        "property_units": 1,
        "occupancy_type": "primary_residence",
    })
    response = client.post("/api/precheck/extract", json=payload)
    assert response.status_code == 200
    assert any(finding["code"] == "application_dti_inconsistent" for finding in response.json()["validation_findings"])


def test_upload_size_limit_is_enforced():
    response = client.post("/api/precheck/extract", json=upload_payload(content=b"x" * (2 * 1024 * 1024 + 1)))
    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "document_size_exceeded"


def test_protected_or_irrelevant_document_text_does_not_cross_worker_boundary():
    payload = upload_payload(content=b"Race: SensitiveValue\nAddress: private\nLoan Amount: 250000\n")
    response = client.post("/api/precheck/review", json=reviewed_payload(payload))
    assert response.status_code == 200
    assert "SensitiveValue" not in response.text
    assert "private" not in response.text
    assert response.json()["extracted_facts"]["loan_amount"]["value"] == 250000


def test_sanitizer_preserves_only_a_safe_adjacent_value_for_pdf_style_labels():
    sanitized = sanitize_document_text("Annual Income\nAlex Morgan\nLoan Amount\n250000\n")

    assert "Alex Morgan" not in sanitized
    assert "Loan Amount\n250000" in sanitized
