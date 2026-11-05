"""Regression coverage for the supplied synthetic Case 01 PDF fixture."""

from __future__ import annotations

import base64
import logging
from pathlib import Path

import pytest
from fastapi.testclient import TestClient

from backend.api import app


client = TestClient(app)


CASE01_PDF = Path(__file__).parent / "fixtures" / "documents" / "CASE01_baseline.pdf"


def test_case01_actual_pdf_upload_extracts_facts_and_surfaces_conflicts(caplog: pytest.LogCaptureFixture):
    payload = {
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
        "supporting_document": {
            "filename": CASE01_PDF.name,
            "media_type": "application/pdf",
            "content_base64": base64.b64encode(CASE01_PDF.read_bytes()).decode("ascii"),
        },
    }

    with caplog.at_level(logging.INFO, logger="uvicorn.error"):
        response = client.post("/api/precheck/extract", json=payload)

    assert response.status_code == 200
    draft = response.json()
    assert draft["document"]["filename"] == "CASE01_baseline.pdf"
    assert draft["document"]["media_type"] == "application/pdf"
    assert draft["document"]["extraction_method"] == "pdf_text"
    extracted_values = {name: fact["value"] for name, fact in draft["extracted_facts"].items()}
    assert {key: extracted_values[key] for key in ("loan_amount", "annual_income", "monthly_debt_obligations", "property_value", "debt_to_income_ratio")} == {
        "loan_amount": 180000,
        "annual_income": 84000,
        "monthly_debt_obligations": 950,
        "property_value": 210000,
        "debt_to_income_ratio": 31.5,
    }
    assert extracted_values["loan_type"] == "fha"
    assert all(
        fact["provenance"]["source"] == "uploaded_document"
        for fact in draft["extracted_facts"].values()
    )
    assert {
        finding["field"]
        for finding in draft["validation_findings"]
        if finding["code"] == "document_application_inconsistent"
    } == {"loan_amount", "annual_income", "monthly_debt_obligations", "property_value", "debt_to_income_ratio", "loan_type"}

    # Merely reviewing an upload must not make document facts authoritative.
    reviewed = client.post(
        "/api/precheck/review",
        json={
            **payload,
            "review_confirmed": True,
            "corrected_fields": [],
            "review_token": draft["review_token"],
        },
    )
    assert reviewed.status_code == 200
    result = reviewed.json()
    summary = result["pipeline_trace"]["extraction"]["summary"]
    assert {key: summary[key] for key in ("income", "monthly_debt_obligations", "property_value")} == {
        "income": 60000,
        "monthly_debt_obligations": 1900,
        "property_value": 300000,
    }
    assert result["human_review_required"] is True
    assert result["recommendation"] not in {"approved", "denied"}

    log_text = "\n".join(caplog.messages)
    assert "status=success" in log_text
    assert "filename=CASE01_baseline.pdf" in log_text
    assert "media_type=application/pdf" in log_text
    assert "extracted_field_names=" in log_text
    assert "Alex Morgan" not in log_text
    assert "84000" not in log_text
