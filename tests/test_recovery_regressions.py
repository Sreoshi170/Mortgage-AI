"""Recovery regressions for synthetic document review and fairness routing."""

from __future__ import annotations

import base64
import time
from pathlib import Path

from fastapi.testclient import TestClient

from backend.api import app
from backend.service import demo_request
from mortgage_precheck.config import PipelineConfig
from mortgage_precheck.graph import WorkerSet, run_pipeline
from mortgage_precheck.schemas import FairnessCheckOutput, PipelineRequest


client = TestClient(app)
DOCUMENT_FIXTURES = Path(__file__).parent / "fixtures" / "documents"


def _application(**overrides: object) -> dict[str, object]:
    values: dict[str, object] = {
        "applicant_type": "individual",
        "co_applicant_present": False,
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
    }
    values.update(overrides)
    return values


def _upload_payload(path: Path, **application_overrides: object) -> dict[str, object]:
    return {
        **_application(**application_overrides),
        "supporting_document": {
            "filename": path.name,
            "media_type": "application/pdf",
            "content_base64": base64.b64encode(path.read_bytes()).decode("ascii"),
        },
    }


def _draft(payload: dict[str, object]) -> dict[str, object]:
    response = client.post("/api/precheck/extract", json=payload)
    assert response.status_code == 200, response.text
    return response.json()


def test_matching_clean_pdf_has_no_document_conflicts():
    """The supplied clean fixture matches its form field-for-field.

    Its supplied DTI and debt/income numbers are mathematically inconsistent,
    so the separately documented application-consistency warning remains.
    """

    payload = _upload_payload(
        DOCUMENT_FIXTURES / "synthetic_clean_loan_application_demo.pdf",
        annual_income=120000,
        monthly_debt_obligations=1800,
        debt_to_income_ratio=30,
        property_value=325000,
    )
    draft = _draft(payload)
    facts = {name: fact["value"] for name, fact in draft["extracted_facts"].items()}

    assert facts["annual_income"] == 120000
    assert facts["property_value"] == 325000
    assert not any(item["code"] == "document_application_inconsistent" for item in draft["validation_findings"])
    assert any(item["code"] == "application_dti_inconsistent" for item in draft["validation_findings"])


def test_clean_runtime_case_is_not_routed_to_review_only_for_not_evaluable_fairness():
    response = client.post(
        "/api/precheck",
        json={**_application(), "supporting_document": "Synthetic evidence only."},
    )

    assert response.status_code == 200
    result = response.json()
    assert result["fairness_check"]["status"] == "not_evaluable"
    assert result["human_review_required"] is False
    assert result["recommendation"] == "proceed"
    assert result["pipeline_trace"]["status"] == "completed"


def test_review_rejects_form_changes_outside_the_confirmed_fields():
    payload = _upload_payload(DOCUMENT_FIXTURES / "CASE01_baseline.pdf")
    draft = _draft(payload)
    response = client.post(
        "/api/precheck/review",
        json={
            **payload,
            "loan_purpose": "refinance",
            "review_confirmed": True,
            "corrected_fields": [],
            "review_token": draft["review_token"],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "review_form_changed_reextract_required"


def test_review_rejects_a_document_that_differs_from_the_extraction_draft():
    payload = _upload_payload(DOCUMENT_FIXTURES / "CASE01_baseline.pdf")
    draft = _draft(payload)
    changed_document = _upload_payload(DOCUMENT_FIXTURES / "synthetic_clean_loan_application_demo.pdf")
    response = client.post(
        "/api/precheck/review",
        json={
            **changed_document,
            "review_confirmed": True,
            "corrected_fields": [],
            "review_token": draft["review_token"],
        },
    )

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "review_document_changed_reextract_required"


def test_malformed_extraction_worker_output_fails_as_a_safe_upload_error(monkeypatch):
    monkeypatch.setattr("backend.service.extraction_worker", lambda *_: object())
    response = client.post("/api/precheck/extract", json=_upload_payload(DOCUMENT_FIXTURES / "CASE01_baseline.pdf"))

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "document_extraction_failed"


def test_pdf_extraction_timeout_fails_with_a_typed_error(monkeypatch):
    def slow_extractor(_: bytes) -> str:
        time.sleep(0.05)
        return "Loan Amount: 250000"

    monkeypatch.setattr("mortgage_precheck.documents._extract_pdf_text", slow_extractor)
    monkeypatch.setattr("mortgage_precheck.documents.PDF_EXTRACTION_TIMEOUT_SECONDS", 0.001)
    response = client.post("/api/precheck/extract", json=_upload_payload(DOCUMENT_FIXTURES / "CASE01_baseline.pdf"))

    assert response.status_code == 422
    assert response.json()["detail"]["code"] == "document_extraction_timeout"


def test_authorized_fairness_finding_state_routes_to_review_when_supplied_by_a_separate_worker():
    def authorized_evaluation(*_args: object) -> FairnessCheckOutput:
        return FairnessCheckOutput(
            status="evaluated_with_findings",
            concerns=["Synthetic authorized evaluation finding for regression coverage."],
            inspected_rule_ids=[],
            requires_human_review=True,
        )

    request = demo_request()
    request["case_id"] = "synthetic-authorized-fairness-regression"
    result = run_pipeline(
        PipelineRequest.model_validate(request),
        config=PipelineConfig(),
        workers=WorkerSet(fairness=authorized_evaluation),
    )

    assert result.fairness is not None
    assert result.fairness.status == "evaluated_with_findings"
    assert result.status == "needs_human_review"
