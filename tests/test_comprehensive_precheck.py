"""Systematic synthetic test coverage for the runtime mortgage pre-check.

This module deliberately separates three outcomes:

* HTTP/Pydantic input validation;
* deterministic extraction and document-quality findings; and
* configured policy/human-review behavior.

The application is a research pre-check.  No test interprets a recommendation
as a mortgage approval or denial.
"""

from __future__ import annotations

import base64
from copy import deepcopy
from io import BytesIO
from pathlib import Path
from typing import Any

import pytest
from fastapi.testclient import TestClient
from pypdf import PdfWriter
from pypdf.generic import DecodedStreamObject, DictionaryObject, NameObject

from backend.api import MAX_REQUEST_BYTES, app
from backend.service import demo_request
from mortgage_precheck.config import PipelineConfig, RuntimeConfig
from mortgage_precheck.documents import MAX_DOCUMENT_BYTES, decode_document_upload
from mortgage_precheck.graph import WorkerSet, run_pipeline
from mortgage_precheck.schemas import PipelineRequest, SupportingDocumentInput
from mortgage_precheck.workers.extraction import extract_document_facts


client = TestClient(app)
FIXTURE = Path(__file__).parent / "fixtures" / "synthetic_employment_verification.txt"


BASE_APPLICATION: dict[str, Any] = {
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
    "supporting_document": "Synthetic employment verification letter",
}

MATCHING_DOCUMENT = "\n".join(
    (
        "Synthetic employment verification",
        "Loan Amount: 250000",
        "Annual Income: 60000",
        "Loan Type: conventional",
        "Loan Purpose: purchase",
        "Income Type: employment",
        "Monthly Debt Obligations: 1900",
        "Property Value: 300000",
        "Property Type: single_family",
        "Number of Units: 1",
        "Occupancy Type: primary_residence",
        "Debt-to-Income Ratio: 38%",
    )
).encode("utf-8")


def precheck_payload(**overrides: Any) -> dict[str, Any]:
    payload = deepcopy(BASE_APPLICATION)
    payload.update(overrides)
    return payload


def upload_payload(
    *,
    content: bytes = MATCHING_DOCUMENT,
    filename: str = "synthetic_evidence.txt",
    media_type: str = "text/plain",
    **application_overrides: Any,
) -> dict[str, Any]:
    payload = precheck_payload(**application_overrides)
    payload["supporting_document"] = {
        "filename": filename,
        "media_type": media_type,
        "content_base64": base64.b64encode(content).decode("ascii"),
    }
    return payload


def reviewed_upload_payload(
    *,
    corrected_fields: list[str] | None = None,
    **application_overrides: Any,
) -> dict[str, Any]:
    """Create a review request from the actual extraction endpoint response."""

    payload = upload_payload(**application_overrides)
    draft = client.post("/api/precheck/extract", json=payload)
    assert draft.status_code == 200, draft.text
    payload.update(
        {
            "review_confirmed": True,
            "corrected_fields": corrected_fields or [],
            "review_token": draft.json()["review_token"],
        }
    )
    return payload


def request_for_pipeline(application: dict[str, Any] | None = None) -> PipelineRequest:
    values = precheck_payload() if application is None else deepcopy(application)
    document_text = values.pop("supporting_document", "Synthetic document")
    values["income"] = values.pop("annual_income")
    return PipelineRequest(
        case_id="comprehensive-case",
        application=values,
        synthetic_document={
            "document_id": "comprehensive-document",
            "label": "SYNTHETIC",
            "content": document_text,
        },
    )


def make_text_pdf(
    *,
    loan_amount: int = 250000,
    annual_income: int = 60000,
    monthly_debt_obligations: int | None = None,
    property_value: int | None = None,
) -> bytes:
    """Build a small in-memory synthetic PDF with extractable labeled facts."""

    writer = PdfWriter()
    page = writer.add_blank_page(width=612, height=792)
    font = DictionaryObject(
        {
            NameObject("/Type"): NameObject("/Font"),
            NameObject("/Subtype"): NameObject("/Type1"),
            NameObject("/BaseFont"): NameObject("/Helvetica"),
        }
    )
    page[NameObject("/Resources")] = DictionaryObject(
        {NameObject("/Font"): DictionaryObject({NameObject("/F1"): writer._add_object(font)})}
    )
    stream = DecodedStreamObject()
    lines = [f"Loan Amount: {loan_amount}", f"Annual Income: {annual_income}"]
    if monthly_debt_obligations is not None:
        lines.append(f"Monthly Debt Obligations: {monthly_debt_obligations}")
    if property_value is not None:
        lines.append(f"Property Value: {property_value}")
    text_commands = " ".join(
        f"{'' if index == 0 else '0 -20 Td '}( {line}) Tj".replace("( ", "(")
        for index, line in enumerate(lines)
    )
    stream.set_data(f"BT /F1 12 Tf 72 720 Td {text_commands} ET".encode("ascii"))
    page[NameObject("/Contents")] = writer._add_object(stream)
    output = BytesIO()
    writer.write(output)
    return output.getvalue()


def error_code(response) -> str | None:
    body = response.json()
    detail = body.get("detail")
    return detail.get("code") if isinstance(detail, dict) else None


def test_valid_baseline_separates_input_success_from_human_review():
    response = client.post("/api/precheck", json=precheck_payload())

    assert response.status_code == 200
    result = response.json()
    assert result["extraction_status"] == "success"
    assert result["policy_check"]["status"] == "clear"
    assert result["fairness_check"]["status"] == "not_evaluable"
    assert result["human_review_required"] is False
    assert result["recommendation"] == "proceed"
    assert result["research_only"] is True
    assert "not a final mortgage approval or denial" in result["explanation"]
    assert result["pipeline_trace"]["gate_status"] == "not_run"


@pytest.mark.parametrize("loan_type", ["conventional", "fha", "va", "usda"])
def test_every_frontend_loan_type_is_accepted_by_the_runtime_contract(loan_type: str):
    response = client.post("/api/precheck", json=precheck_payload(loan_type=loan_type))

    assert response.status_code == 200
    assert response.json()["extraction_status"] == "success"


@pytest.mark.parametrize("loan_type", ["jumbo", "hecm", "not-a-configured-product"])
def test_nonempty_unsupported_loan_types_are_currently_not_rejected(loan_type: str):
    """Regression coverage for the current permissive string contract.

    The UI offers four values, but the backend schema only requires a
    non-empty string. This test records that gap without treating the value as
    an approval or denial rule.
    """

    response = client.post("/api/precheck", json=precheck_payload(loan_type=loan_type))

    assert response.status_code == 200


def test_empty_loan_type_is_an_input_validation_error():
    response = client.post("/api/precheck", json=precheck_payload(loan_type=""))

    assert response.status_code == 422


NUMERIC_FIELDS = (
    ("loan_amount", 250000, 0, -1, "not-a-number", 10**30, True),
    ("annual_income", 60000, 0, -1, "not-a-number", 10**30, True),
    ("co_applicant_annual_income", 40000, 0, -1, "not-a-number", 10**30, False),
    ("monthly_debt_obligations", 1900, 0, -1, "not-a-number", 10**30, False),
    ("property_value", 300000, 0, -1, "not-a-number", 10**30, False),
    ("property_units", 1, 0, -1, "many", 10**30, False),
)


@pytest.mark.parametrize(
    "field,valid,zero,negative,malformed,very_large,required",
    NUMERIC_FIELDS,
)
def test_each_numeric_field_accepts_valid_and_very_large_values_but_rejects_bad_input(
    field: str,
    valid: Any,
    zero: Any,
    negative: Any,
    malformed: Any,
    very_large: Any,
    required: bool,
):
    context = {"applicant_type": "joint", "co_applicant_present": True} if field == "co_applicant_annual_income" else {}
    valid_response = client.post("/api/precheck", json=precheck_payload(**context, **{field: valid}))
    assert valid_response.status_code == 200

    zero_response = client.post("/api/precheck", json=precheck_payload(**context, **{field: zero}))
    expected_zero_status = 422 if field in {"loan_amount", "annual_income", "property_value", "property_units"} else 200
    assert zero_response.status_code == expected_zero_status

    negative_response = client.post("/api/precheck", json=precheck_payload(**context, **{field: negative}))
    assert negative_response.status_code == 422

    malformed_response = client.post("/api/precheck", json=precheck_payload(**context, **{field: malformed}))
    assert malformed_response.status_code == 422

    large_response = client.post("/api/precheck", json=precheck_payload(**context, **{field: very_large}))
    assert large_response.status_code == 200


@pytest.mark.parametrize("field", ["loan_amount", "annual_income"])
def test_required_numeric_fields_cannot_be_missing(field: str):
    payload = precheck_payload()
    payload.pop(field)

    response = client.post("/api/precheck", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "field,expected_missing",
    [
        ("co_applicant_annual_income", True),
        ("monthly_debt_obligations", True),
        ("property_value", True),
        ("property_units", False),
    ],
)
def test_optional_numeric_fields_can_be_missing_with_current_worker_handling(field: str, expected_missing: bool):
    context = {"applicant_type": "joint", "co_applicant_present": True} if field == "co_applicant_annual_income" else {}
    payload = precheck_payload(**context)
    payload.pop(field, None)

    response = client.post("/api/precheck", json=payload)

    assert response.status_code == 200
    result = response.json()
    assert (field in result["pipeline_trace"]["extraction"]["missing_fields"]) is expected_missing
    if expected_missing:
        assert result["pipeline_trace"]["policy"]["recommendation"] == "documentation_incomplete"


@pytest.mark.parametrize(
    "field,value,expected_status",
    [
        ("loan_amount", 0.01, 200),
        ("annual_income", 0.01, 200),
        ("co_applicant_annual_income", 0, 200),
        ("monthly_debt_obligations", 0, 200),
        ("property_value", 0.01, 200),
        ("property_units", 1, 200),
        ("property_units", 0, 422),
        ("debt_to_income_ratio", 0, 200),
        ("debt_to_income_ratio", 100, 200),
        ("debt_to_income_ratio", -0.01, 422),
        ("debt_to_income_ratio", 100.01, 422),
    ],
)
def test_numeric_boundary_values_follow_the_actual_schema_rules(field: str, value: Any, expected_status: int):
    context = {"applicant_type": "joint", "co_applicant_present": True} if field == "co_applicant_annual_income" else {}
    response = client.post("/api/precheck", json=precheck_payload(**context, **{field: value}))

    assert response.status_code == expected_status


def test_dti_string_values_are_allowed_by_the_current_union_and_preserved_as_buckets():
    response = client.post("/api/precheck", json=precheck_payload(debt_to_income_ratio="not-a-number"))

    assert response.status_code == 200
    summary = response.json()["pipeline_trace"]["extraction"]["summary"]
    assert summary["debt_to_income_ratio"] is None
    assert summary["debt_to_income_bucket"] == "not-a-number"


@pytest.mark.parametrize("value", list(range(0, 101)))
def test_dti_numeric_domain_property_is_closed_over_zero_through_one_hundred(value: int):
    response = client.post("/api/precheck", json=precheck_payload(debt_to_income_ratio=value))

    assert response.status_code == 200


@pytest.mark.parametrize("value", [-1, 101, 1000])
def test_dti_numeric_values_outside_the_configured_input_domain_are_rejected(value: int):
    response = client.post("/api/precheck", json=precheck_payload(debt_to_income_ratio=value))

    assert response.status_code == 422


def test_missing_income_cannot_be_replaced_by_an_uploaded_document():
    payload = upload_payload()
    payload.pop("annual_income")

    response = client.post("/api/precheck/extract", json=payload)

    assert response.status_code == 422


@pytest.mark.parametrize(
    "extension,media_type",
    [
        (".txt", "text/plain"),
        (".md", "text/markdown"),
        (".csv", "text/csv"),
        (".json", "application/json"),
        (".pdf", "application/pdf"),
    ],
)
def test_every_declared_upload_type_has_a_deterministic_validation_path(extension: str, media_type: str):
    content = make_text_pdf() if extension == ".pdf" else MATCHING_DOCUMENT
    response = client.post(
        "/api/precheck/extract",
        json=upload_payload(content=content, filename=f"synthetic{extension}", media_type=media_type),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["document"]["extraction_method"] == ("pdf_text" if extension == ".pdf" else "utf8_text")
    assert result["extracted_facts"]["loan_amount"]["value"] == 250000
    assert result["extracted_facts"]["loan_amount"]["provenance"]["confidence"] == 0.9


def test_matching_document_facts_have_upload_provenance_and_source_lines():
    response = client.post("/api/precheck/extract", json=upload_payload())

    assert response.status_code == 200
    result = response.json()
    assert result["validation_findings"] == []
    assert result["extracted_facts"]["annual_income"]["provenance"]["source"] == "uploaded_document"
    assert ":line:2" in result["extracted_facts"]["loan_amount"]["provenance"]["evidence"]
    assert result["review_required"] is True


def test_case01_pdf_surfaces_all_form_document_discrepancies_before_confirmation():
    case01_pdf = make_text_pdf(
        loan_amount=250000,
        annual_income=1200000,
        monthly_debt_obligations=1800,
        property_value=325000,
    )
    payload = upload_payload(
        content=case01_pdf,
        filename="case01_synthetic.pdf",
        media_type="application/pdf",
    )

    draft_response = client.post("/api/precheck/extract", json=payload)

    assert draft_response.status_code == 200
    draft = draft_response.json()
    assert {
        field
        for finding in draft["validation_findings"]
        if finding["code"] == "document_application_inconsistent"
        for field in [finding["field"]]
    } == {"annual_income", "monthly_debt_obligations", "property_value"}
    assert draft["extracted_facts"]["annual_income"]["value"] == 1200000
    assert draft["extracted_facts"]["monthly_debt_obligations"]["value"] == 1800
    assert draft["extracted_facts"]["property_value"]["value"] == 325000

    reviewed_payload = {
        **payload,
        "review_confirmed": True,
        "corrected_fields": [],
        "review_token": draft["review_token"],
    }
    reviewed_response = client.post("/api/precheck/review", json=reviewed_payload)

    assert reviewed_response.status_code == 200
    result = reviewed_response.json()
    summary = result["pipeline_trace"]["extraction"]["summary"]
    assert summary["income"] == 60000
    assert summary["monthly_debt_obligations"] == 1900
    assert summary["property_value"] == 300000
    assert result["pipeline_trace"]["extraction"]["extracted_facts"]["annual_income"]["value"] == 1200000
    assert result["pipeline_trace"]["policy"]["recommendation"] == "flag_for_manual_review"
    assert "annual_income" in result["pipeline_trace"]["narrative"]["narrative"]
    assert "monthly_debt_obligations" in result["pipeline_trace"]["narrative"]["narrative"]
    assert "property_value" in result["pipeline_trace"]["narrative"]["narrative"]


def test_named_synthetic_employment_fixture_is_used_as_data_not_instructions():
    content = FIXTURE.read_text(encoding="utf-8")

    facts = extract_document_facts(content, source="synthetic_fixture")

    assert "SYNTHETIC" in content
    assert facts["loan_amount"].value == 250000
    assert facts["annual_income"].value == 1200000
    assert facts["loan_type"].value == "conventional"
    assert facts["loan_amount"].provenance.source == "synthetic_fixture"


def test_conflicting_form_and_document_facts_are_reported_but_structured_values_remain_authoritative():
    response = client.post(
        "/api/precheck/review",
        json=reviewed_upload_payload(content=b"Loan Amount: 400000\nAnnual Income: 60000\n"),
    )

    assert response.status_code == 200
    result = response.json()
    assert any(item["code"] == "document_application_inconsistent" for item in result["validation_findings"])
    assert result["pipeline_trace"]["extraction"]["summary"]["loan_amount"] == 250000
    assert result["pipeline_trace"]["extraction"]["extracted_facts"]["loan_amount"]["value"] == 400000
    assert result["pipeline_trace"]["policy"]["recommendation"] == "flag_for_manual_review"
    assert result["human_review_required"] is True


def test_ambiguous_duplicate_labels_are_deterministic_but_not_marked_ambiguous():
    content = b"Loan Amount: 250000 or Loan Amount: 300000\nAnnual Income: 60000\n"
    response = client.post("/api/precheck/extract", json=upload_payload(content=content))

    assert response.status_code == 200
    result = response.json()
    assert result["extracted_facts"]["loan_amount"]["value"] == 250000
    assert not any(item["code"] == "document_ambiguous" for item in result["validation_findings"])


def test_missing_labeled_facts_produce_missing_evidence_and_manual_review():
    response = client.post(
        "/api/precheck/review",
        json=reviewed_upload_payload(content=b"This synthetic letter contains no labeled numeric facts."),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["extracted_facts"] == {}
    assert "document_relevant_facts" in result["missing_evidence"]
    assert any(item["code"] == "document_no_extractable_facts" for item in result["validation_findings"])
    assert result["pipeline_trace"]["policy"]["recommendation"] == "documentation_incomplete"
    assert result["review_status"] == "reviewed"


@pytest.mark.parametrize(
    "content,filename,media_type,expected_code",
    [
        (b"", "empty.txt", "text/plain", None),
        (b"   \n", "blank.txt", "text/plain", "document_text_empty"),
        (b"\xff\xfe", "binary.txt", "text/plain", "document_encoding_unsupported"),
        (b"not a pdf", "broken.pdf", "application/pdf", "document_pdf_invalid"),
        (b"Loan Amount: 250000", "unsupported.exe", "application/octet-stream", "document_file_type_unsupported"),
        (b"Loan Amount: 250000", "wrong.txt", "application/json", "document_media_type_mismatch"),
    ],
)
def test_unreadable_empty_corrupt_and_unsupported_uploads_fail_with_safe_codes(
    content: bytes, filename: str, media_type: str, expected_code: str
):
    response = client.post(
        "/api/precheck/extract",
        json=upload_payload(content=content, filename=filename, media_type=media_type),
    )

    assert response.status_code == 422
    assert error_code(response) == expected_code
    assert "Loan Amount" not in response.text


def test_invalid_base64_is_rejected_without_echoing_the_payload():
    payload = upload_payload()
    payload["supporting_document"]["content_base64"] = "not-valid-base64-with-sensitive-marker"

    response = client.post("/api/precheck/extract", json=payload)

    assert response.status_code == 422
    assert error_code(response) == "document_base64_invalid"
    assert "sensitive-marker" not in response.text


def test_upload_size_boundary_accepts_two_megabytes_and_rejects_one_byte_more():
    prefix = b"Loan Amount: 250000\n"
    exact_content = prefix + (b"x" * (MAX_DOCUMENT_BYTES - len(prefix)))
    accepted = client.post("/api/precheck/extract", json=upload_payload(content=exact_content))
    rejected = client.post(
        "/api/precheck/extract",
        json=upload_payload(content=exact_content + b"x"),
    )

    assert accepted.status_code == 200
    assert rejected.status_code == 422
    assert error_code(rejected) == "document_size_exceeded"


def test_duplicate_uploads_have_same_hash_but_are_not_silently_collapsed():
    first = client.post("/api/precheck/extract", json=upload_payload())
    second = client.post("/api/precheck/extract", json=upload_payload())

    assert first.status_code == second.status_code == 200
    first_doc = first.json()["document"]
    second_doc = second.json()["document"]
    assert first_doc["sha256"] == second_doc["sha256"]
    assert first_doc["document_id"] != second_doc["document_id"]


def test_multiple_documents_are_rejected_by_the_current_single_document_contract():
    payload = precheck_payload(
        supporting_document=[
            {"filename": "one.txt", "media_type": "text/plain", "content_base64": base64.b64encode(MATCHING_DOCUMENT).decode()},
            {"filename": "two.txt", "media_type": "text/plain", "content_base64": base64.b64encode(MATCHING_DOCUMENT).decode()},
        ]
    )

    response = client.post("/api/precheck/extract", json=payload)

    assert response.status_code == 422


def test_review_correction_changes_structured_value_and_marks_reviewer_provenance():
    payload = upload_payload()
    draft = client.post("/api/precheck/extract", json=payload)
    assert draft.status_code == 200
    payload.update(
        {
            "loan_amount": 275000,
            "review_confirmed": True,
            "corrected_fields": ["loan_amount"],
            "review_token": draft.json()["review_token"],
        }
    )

    response = client.post("/api/precheck/review", json=payload)

    assert response.status_code == 200
    result = response.json()
    extraction = result["pipeline_trace"]["extraction"]
    assert extraction["summary"]["loan_amount"] == 275000
    assert extraction["extracted_facts"]["loan_amount"]["value"] == 250000
    assert extraction["provenance"]["loan_amount"]["source"] == "reviewer_correction"
    assert extraction["provenance"]["loan_amount"]["evidence"] == "user_confirmed_review_value"
    assert result["review_status"] == "reviewed"


def test_review_requires_explicit_confirmation_and_does_not_run_workers():
    response = client.post("/api/precheck/review", json=upload_payload(review_confirmed=False))

    assert response.status_code == 422
    assert error_code(response) == "review_confirmation_required"


@pytest.mark.parametrize("field", ["loan_amount", "annual_income", "loan_type", "debt_to_income_ratio", "supporting_document"])
def test_required_api_fields_are_not_silently_defaulted(field: str):
    payload = precheck_payload()
    payload.pop(field)

    response = client.post("/api/precheck", json=payload)

    assert response.status_code == 422


def test_extra_api_fields_are_rejected_fail_closed():
    response = client.post("/api/precheck", json=precheck_payload(unexpected_internal_flag=True))

    assert response.status_code == 422


def test_malformed_json_and_bad_request_size_headers_are_safe():
    malformed = client.post("/api/precheck", content=b"not-json", headers={"Content-Type": "application/json"})
    invalid_length = client.post(
        "/api/precheck",
        content=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": "not-a-number"},
    )
    too_large = client.post(
        "/api/precheck",
        content=b"{}",
        headers={"Content-Type": "application/json", "Content-Length": str(MAX_REQUEST_BYTES + 1)},
    )

    assert malformed.status_code == 422
    assert invalid_length.status_code == 400
    assert invalid_length.json() == {"status": "failed", "error": "invalid_content_length"}
    assert too_large.status_code == 413
    assert too_large.json() == {"status": "failed", "error": "request_size_invalid"}


def test_sensitive_document_lines_are_sanitized_before_worker_and_error_outputs():
    sensitive = b"Race: SyntheticValue\nAddress: 123 Synthetic Street\nLoan Amount: 250000\n"
    response = client.post("/api/precheck/review", json=reviewed_upload_payload(content=sensitive))

    assert response.status_code == 200
    assert "SyntheticValue" not in response.text
    assert "Synthetic Street" not in response.text
    assert response.json()["extracted_facts"]["loan_amount"]["value"] == 250000


def test_single_document_path_never_uses_filename_as_a_filesystem_path():
    response = client.post(
        "/api/precheck/extract",
        json=upload_payload(filename="..\\..\\synthetic.txt"),
    )

    assert response.status_code == 200
    assert response.json()["document"]["filename"] == "..\\..\\synthetic.txt"


def test_pairwise_low_income_high_loan_is_a_policy_review_case_not_an_approval_decision():
    response = client.post(
        "/api/precheck",
        json=precheck_payload(annual_income=1, loan_amount=10**30),
    )

    assert response.status_code == 200
    result = response.json()
    assert result["recommendation"] == "flag for manual review"
    assert result["pipeline_trace"]["extraction"]["summary"]["loan_amount"] == float(10**30)
    assert "not a final mortgage approval or denial" in result["explanation"]


def test_pairwise_missing_income_with_upload_fails_input_validation_before_extraction():
    payload = upload_payload()
    payload.pop("annual_income")

    response = client.post("/api/precheck/review", json=payload)

    assert response.status_code == 422


def test_default_policy_has_no_invented_dti_or_ltv_thresholds():
    result = run_pipeline(request_for_pipeline())
    rule_ids = {check.rule_id for check in result.policy.checks}

    assert "POL-001" not in rule_ids
    assert "POL-002" not in rule_ids
    assert result.policy.recommendation == "proceed"
    assert result.status == "completed"


@pytest.mark.parametrize(
    "dti,expected_status,expected_recommendation",
    [(40, "pass", "proceed"), (40.01, "flag", "flag_for_manual_review")],
)
def test_configured_dti_policy_uses_only_the_caller_supplied_boundary(
    dti: float, expected_status: str, expected_recommendation: str
):
    application = precheck_payload(debt_to_income_ratio=dti, monthly_debt_obligations=2000)
    result = run_pipeline(request_for_pipeline(application), config=PipelineConfig(policy_dti_max=40))
    dti_check = next(check for check in result.policy.checks if check.rule_id == "POL-001")

    assert dti_check.status == expected_status
    assert result.policy.recommendation == expected_recommendation


def test_policy_and_narrative_outputs_explain_flags_without_final_decision_language():
    result = run_pipeline(
        request_for_pipeline(
            precheck_payload(
                debt_to_income_ratio=50,
                monthly_debt_obligations=2500,
                combined_loan_to_value_ratio=90,
            )
        ),
        config=PipelineConfig(policy_dti_max=40, policy_ltv_max=80),
    )

    assert result.policy.recommendation == "flag_for_manual_review"
    assert {check.rule_id for check in result.policy.checks if check.status == "flag"} >= {"POL-001", "POL-002"}
    assert set(result.narrative.evidence_rule_ids) >= {"POL-001", "POL-002"}
    assert "not a final lending decision" in result.narrative.narrative
    assert result.fairness.protected_data_seen is False


def test_demo_route_and_frontend_regression_contract_remain_functional():
    response = client.get("/api/demo-run")

    assert response.status_code == 200
    result = response.json()
    assert result["case_id"] == demo_request()["case_id"]
    assert result["status"] == "completed"
    assert result["gate_status"] == "not_run"
    assert {event["node"] for event in result["audit_events"] if event["event_type"] == "worker_completed"} == {
        "extraction_worker",
        "policy_check_worker",
        "decision_narrative_worker",
        "fairness_check_worker",
    }


def test_pipeline_request_requires_exactly_one_document_contract():
    payload = request_for_pipeline().model_dump()
    payload["runtime_document"] = {
        "document_id": "runtime-doc",
        "label": "USER_UPLOAD",
        "filename": "synthetic.txt",
        "media_type": "text/plain",
        "size_bytes": 1,
        "sha256": "0" * 64,
        "extraction_method": "utf8_text",
        "content": "Loan Amount: 250000",
    }
    result = run_pipeline(payload)

    assert result.status == "failed"
    assert result.failure.code == "request_schema_invalid"
    assert not any(event.event_type == "worker_started" for event in result.audit_events)


@pytest.mark.parametrize("worker_name", ["extraction", "policy", "narrative", "fairness"])
def test_each_worker_failure_retries_then_returns_a_typed_safe_failure(worker_name: str):
    calls = {"count": 0}

    def failing(*args: Any, **kwargs: Any):
        del args, kwargs
        calls["count"] += 1
        raise RuntimeError("synthetic internal secret")

    workers = WorkerSet(**{worker_name: failing})
    result = run_pipeline(
        request_for_pipeline(),
        config=PipelineConfig(runtime=RuntimeConfig(max_attempts=2, timeout_seconds=1, max_graph_steps=12)),
        workers=workers,
    )

    assert result.status == "failed"
    assert result.failure.code == "worker_exception"
    assert result.failure.message == "worker_exception"
    assert calls["count"] == 2
    assert "synthetic internal secret" not in result.model_dump_json()
    worker_nodes = {
        "extraction": "extraction_worker",
        "policy": "policy_check_worker",
        "narrative": "decision_narrative_worker",
        "fairness": "fairness_check_worker",
    }
    assert any(
        event.node == worker_nodes[worker_name] and event.event_type == "worker_failed"
        for event in result.audit_events
    )


def test_malformed_worker_output_is_retried_and_converted_to_typed_failure():
    calls = {"count": 0}

    def malformed_extraction(*args: Any, **kwargs: Any):
        del args, kwargs
        calls["count"] += 1
        return {"valid": True}

    result = run_pipeline(
        request_for_pipeline(),
        config=PipelineConfig(runtime=RuntimeConfig(max_attempts=2, timeout_seconds=1, max_graph_steps=12)),
        workers=WorkerSet(extraction=malformed_extraction),
    )

    assert result.status == "failed"
    assert result.failure.code == "worker_exception"
    assert calls["count"] == 2


def test_graph_step_limit_prevents_unbounded_recovery():
    result = run_pipeline(
        request_for_pipeline(),
        config=PipelineConfig(runtime=RuntimeConfig(max_attempts=2, timeout_seconds=1, max_graph_steps=1)),
    )

    assert result.status == "failed"
    assert result.failure.code == "max_graph_steps_exceeded"


def test_incomplete_extraction_values_are_reported_as_documentation_gaps():
    payload = precheck_payload(property_value=None, monthly_debt_obligations=None)
    response = client.post("/api/precheck", json=payload)

    assert response.status_code == 200
    result = response.json()
    assert result["pipeline_trace"]["extraction"]["valid"] is True
    assert set(result["pipeline_trace"]["policy"]["missing_fields"]) >= {
        "property_value",
        "monthly_debt_obligations",
    }
    assert result["pipeline_trace"]["policy"]["recommendation"] == "documentation_incomplete"


def test_extraction_numeric_fact_parser_handles_generated_finite_decimal_values_without_sensitive_state():
    generated_values = [f"{index}.{index % 10}" for index in range(0, 51)]

    for value in generated_values:
        facts = extract_document_facts(
            f"Loan Amount: {value}", source="synthetic_fixture", confidence=0.9
        )
        assert facts["loan_amount"].provenance.source == "synthetic_fixture"
        assert facts["loan_amount"].provenance.confidence == 0.9
        assert float(facts["loan_amount"].value) == pytest.approx(float(value))


def test_direct_document_decode_returns_metadata_only_and_hashes_bytes():
    upload = SupportingDocumentInput(
        filename="synthetic.txt",
        media_type="text/plain",
        content_base64=base64.b64encode(MATCHING_DOCUMENT).decode("ascii"),
    )

    document = decode_document_upload(upload, document_id="document-1")

    assert document.document_id == "document-1"
    assert document.label == "USER_UPLOAD"
    assert document.size_bytes == len(MATCHING_DOCUMENT)
    assert len(document.sha256) == 64
    assert "Synthetic employment verification" not in document.content
    assert "Loan Amount: 250000" in document.content

