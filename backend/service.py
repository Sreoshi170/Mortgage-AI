"""Application service boundary for the deterministic LangGraph backend."""

from __future__ import annotations

import logging
import base64
import hashlib
import hmac
import json
from pathlib import Path
import secrets
import time
from typing import Any
from uuid import uuid4

from mortgage_precheck import PipelineConfig, PrecheckRequest, PrecheckResponse, run_pipeline
from mortgage_precheck.boundary import sanitize_application
from mortgage_precheck.documents import DocumentUploadError, decode_document_upload, describe_runtime_document
from mortgage_precheck.schemas import (
    DocumentExtractionDraft,
    DocumentPrecheckRequest,
    ExtractionOutput,
    PipelineRequest,
    ReviewedDocumentPrecheckRequest,
)
from mortgage_precheck.workers.extraction import extraction_worker


# Uvicorn owns the local service log handler. Reuse it so upload diagnostics
# are emitted in the running backend rather than being silently discarded.
logger = logging.getLogger("uvicorn.error")

_REVIEW_TOKEN_SECRET = secrets.token_bytes(32)
_REVIEW_TOKEN_MAX_AGE_SECONDS = 30 * 60
_REVIEWABLE_FIELDS = frozenset(
    {
        "loan_amount",
        "income",
        "property_value",
        "monthly_debt_obligations",
        "loan_type",
        "debt_to_income_ratio",
    }
)


def _review_snapshot(request: DocumentPrecheckRequest) -> dict[str, Any]:
    """Return the non-sensitive, typed application values that were reviewed."""

    application = _runtime_application(request, case_id="review-snapshot")
    application.pop("case_id", None)
    return application


def _token_encode(value: bytes) -> str:
    return base64.urlsafe_b64encode(value).decode("ascii").rstrip("=")


def _token_decode(value: str) -> bytes:
    return base64.urlsafe_b64decode(value + "=" * (-len(value) % 4))


def _issue_review_token(*, case_id: str, application: dict[str, Any], document_sha256: str) -> str:
    """Create a stateless review context without retaining document contents."""

    payload = {
        "version": 1,
        "case_id": case_id,
        "application": application,
        "document_sha256": document_sha256,
        "issued_at": int(time.time()),
    }
    encoded_payload = _token_encode(json.dumps(payload, separators=(",", ":"), sort_keys=True).encode("utf-8"))
    signature = _token_encode(hmac.new(_REVIEW_TOKEN_SECRET, encoded_payload.encode("ascii"), hashlib.sha256).digest())
    return f"{encoded_payload}.{signature}"


def _read_review_token(token: str) -> dict[str, Any]:
    """Verify and decode one review context; never expose token contents in errors."""

    try:
        encoded_payload, encoded_signature = token.split(".", 1)
        expected_signature = _token_encode(
            hmac.new(_REVIEW_TOKEN_SECRET, encoded_payload.encode("ascii"), hashlib.sha256).digest()
        )
        if not hmac.compare_digest(encoded_signature, expected_signature):
            raise ValueError("signature")
        payload = json.loads(_token_decode(encoded_payload))
        issued_at = int(payload["issued_at"])
        if int(time.time()) - issued_at > _REVIEW_TOKEN_MAX_AGE_SECONDS or issued_at > int(time.time()) + 60:
            raise DocumentUploadError("review_token_expired")
        if (
            payload.get("version") != 1
            or not isinstance(payload.get("case_id"), str)
            or not isinstance(payload.get("application"), dict)
            or not isinstance(payload.get("document_sha256"), str)
        ):
            raise ValueError("payload")
        return payload
    except DocumentUploadError:
        raise
    except Exception as exc:
        raise DocumentUploadError("review_token_invalid") from exc


def _verify_review_context(request: ReviewedDocumentPrecheckRequest, *, document_sha256: str) -> str:
    """Ensure the confirmed values belong to the extracted form/document pair."""

    if not request.review_token:
        raise DocumentUploadError("review_token_required")
    context = _read_review_token(request.review_token)
    if not hmac.compare_digest(context["document_sha256"], document_sha256):
        raise DocumentUploadError("review_document_changed_reextract_required")

    original = context["application"]
    current = _review_snapshot(request)
    if set(original) != set(current):
        raise DocumentUploadError("review_context_invalid")
    changed_fields = {field for field in _REVIEWABLE_FIELDS if original[field] != current[field]}
    changed_outside_review = {
        field for field in current if field not in _REVIEWABLE_FIELDS and original[field] != current[field]
    }
    if changed_outside_review:
        raise DocumentUploadError("review_form_changed_reextract_required")
    requested_corrections = set(request.corrected_fields)
    if not requested_corrections.issubset(_REVIEWABLE_FIELDS) or requested_corrections != changed_fields:
        raise DocumentUploadError("review_corrections_invalid")
    return context["case_id"]


def _upload_metadata(request: DocumentPrecheckRequest) -> dict[str, str]:
    """Return safe upload diagnostics; never include document bytes or text."""

    return {
        "filename": Path(request.supporting_document.filename).name,
        "media_type": request.supporting_document.media_type,
    }


def demo_request() -> dict[str, Any]:
    """Return a clearly synthetic fixture for local UI and API testing."""

    return {
        "case_id": "demo-phase2-001",
        "application": {
            "applicant_type": "individual",
            "co_applicant_present": False,
            "activity_year": 2025,
            "loan_amount": "195000",
            "property_value": "215000",
            "income": "86000",
            "income_type": "employment",
            "monthly_debt_obligations": "2938.33",
            "debt_to_income_ratio": "41",
            "combined_loan_to_value_ratio": "95.0",
            "interest_rate": "6.125",
            "rate_spread": "0.166",
            "loan_type": "1",
            "loan_purpose": "1",
            "property_type": "single_family",
            "property_units": 1,
            "occupancy_type": "1",
        },
        "synthetic_document": {
            "document_id": "demo-doc-001",
            "label": "SYNTHETIC",
            "content": "Synthetic employment verification letter for deterministic UI testing.",
        },
    }


def run_payload(payload: dict[str, Any]) -> dict[str, Any]:
    """Validate and execute one request through the bounded graph."""

    return run_pipeline(payload, config=PipelineConfig()).model_dump(mode="json")


def demo_run_payload() -> dict[str, Any]:
    """Execute the standard synthetic fixture through the real graph."""

    return run_payload(demo_request())


def run_precheck(payload: PrecheckRequest | dict[str, Any]) -> PrecheckResponse:
    """Run the applicant-facing contract through the same bounded graph.

    The compact input is deliberately expanded into the internal typed contract;
    the full trace is retained in ``pipeline_trace`` for explanation and audit.
    """

    request = payload if isinstance(payload, PrecheckRequest) else PrecheckRequest.model_validate(payload)
    case_id = f"case-{uuid4()}"
    pipeline = run_pipeline(
        {
            "case_id": case_id,
            "application": {
                "applicant_type": request.applicant_type,
                "co_applicant_present": request.co_applicant_present,
                "co_applicant_annual_income": request.co_applicant_annual_income,
                "co_applicant_income_type": request.co_applicant_income_type,
                "loan_amount": request.loan_amount,
                "income": request.annual_income,
                "income_type": request.income_type,
                "monthly_debt_obligations": request.monthly_debt_obligations,
                "loan_type": request.loan_type,
                "loan_purpose": request.loan_purpose,
                "debt_to_income_ratio": request.debt_to_income_ratio,
                "property_value": request.property_value,
                "property_type": request.property_type,
                "property_units": request.property_units,
                "occupancy_type": request.occupancy_type,
            },
            "synthetic_document": {
                "document_id": f"document-{uuid4()}",
                "label": "SYNTHETIC",
                "content": request.supporting_document,
            },
        },
        config=PipelineConfig(),
    )

    return _precheck_response(pipeline, review_status="not_applicable")


def _precheck_response(pipeline, *, review_status: str) -> PrecheckResponse:
    extraction_success = pipeline.extraction is not None and pipeline.extraction.valid
    flagged_checks = [
        check for check in (pipeline.policy.checks if pipeline.policy else []) if check.status != "pass"
    ]
    policy_flagged = (
        pipeline.policy is None
        or pipeline.policy.recommendation != "proceed"
        or pipeline.status == "failed"
    )
    policy_reason = (
        "Requires review against configured policy rules"
        if policy_flagged
        else "No configured policy rule was flagged"
    )

    fairness = pipeline.fairness
    if fairness is None:
        fairness_status = "not_evaluable"
        fairness_reason = "Fairness worker did not produce a reliable result; human review is required."
        fairness_requires_review = True
    elif fairness.status == "not_evaluable":
        fairness_status = "not_evaluable"
        fairness_reason = (
            "No authorized demographic fairness evaluation ran. This is not evidence of fairness. "
            + " ".join(fairness.concerns)
        )
        fairness_requires_review = fairness.requires_human_review
    elif fairness.status == "evaluated_with_findings":
        fairness_status = "evaluated_with_findings"
        fairness_reason = " ".join(fairness.concerns) or "Authorized fairness evaluation reported findings."
        fairness_requires_review = True
    else:
        fairness_status = "evaluated_no_findings"
        fairness_reason = "Authorized fairness evaluation reported no findings."
        fairness_requires_review = fairness.requires_human_review

    human_review_required = policy_flagged or fairness_requires_review or pipeline.status != "completed"
    recommendation = "flag for manual review" if human_review_required else "proceed"

    detail_parts = [check.evidence for check in flagged_checks]
    if pipeline.extraction is not None:
        detail_parts.extend(pipeline.extraction.missing_evidence)
    detail = "; ".join(detail_parts) or "All configured checks passed."
    explanation = (
        f"Extraction {('succeeded' if extraction_success else 'failed')} for the submitted application. "
        f"Policy check: {policy_reason}. {detail} "
        f"Fairness check: {fairness_reason}. "
        f"Recommendation: {recommendation}. This is a research pre-check, not a final mortgage approval or denial."
    )
    return PrecheckResponse(
        extraction_status="success" if extraction_success else "failed",
        policy_check={"status": "flagged" if policy_flagged else "clear", "reason": policy_reason},
        recommendation=recommendation,
        fairness_check={
            "status": fairness_status,
            "reason": fairness_reason,
        },
        human_review_required=human_review_required,
        explanation=explanation,
        pipeline_trace=pipeline,
        extracted_facts=pipeline.extraction.extracted_facts if pipeline.extraction else {},
        validation_findings=pipeline.extraction.validation_findings if pipeline.extraction else [],
        missing_evidence=pipeline.extraction.missing_evidence if pipeline.extraction else [],
        review_status=review_status,
    )


def _runtime_application(request: DocumentPrecheckRequest, case_id: str) -> dict[str, Any]:
    return {
        "case_id": case_id,
        "applicant_type": request.applicant_type,
        "co_applicant_present": request.co_applicant_present,
        "co_applicant_annual_income": request.co_applicant_annual_income,
        "co_applicant_income_type": request.co_applicant_income_type,
        "loan_amount": request.loan_amount,
        "income": request.annual_income,
        "income_type": request.income_type,
        "monthly_debt_obligations": request.monthly_debt_obligations,
        "loan_type": request.loan_type,
        "loan_purpose": request.loan_purpose,
        "debt_to_income_ratio": request.debt_to_income_ratio,
        "property_value": request.property_value,
        "property_type": request.property_type,
        "property_units": request.property_units,
        "occupancy_type": request.occupancy_type,
    }


def extract_uploaded_document(payload: DocumentPrecheckRequest | dict[str, Any]) -> DocumentExtractionDraft:
    """Run the existing extraction worker for an upload and return a review draft."""

    request = payload if isinstance(payload, DocumentPrecheckRequest) else DocumentPrecheckRequest.model_validate(payload)
    metadata = _upload_metadata(request)
    case_id = f"case-{uuid4()}"
    try:
        document = decode_document_upload(request.supporting_document, document_id=f"document-{uuid4()}")
    except DocumentUploadError as exc:
        logger.warning(
            "document_extraction status=failed filename=%s media_type=%s error_code=%s",
            metadata["filename"],
            metadata["media_type"],
            exc.code,
        )
        raise
    application = sanitize_application(case_id, _runtime_application(request, case_id))
    try:
        extraction = ExtractionOutput.model_validate(extraction_worker(application, document))
    except Exception as exc:
        logger.warning(
            "document_extraction status=failed filename=%s media_type=%s error_code=document_extraction_failed",
            metadata["filename"],
            metadata["media_type"],
        )
        raise DocumentUploadError("document_extraction_failed") from exc
    logger.info(
        "document_extraction status=success filename=%s media_type=%s extraction_method=%s extracted_field_names=%s",
        metadata["filename"],
        metadata["media_type"],
        document.extraction_method,
        ",".join(sorted(extraction.extracted_facts)),
    )
    return DocumentExtractionDraft(
        case_id=case_id,
        document=describe_runtime_document(document),
        extracted_facts=extraction.extracted_facts,
        validation_findings=extraction.validation_findings,
        missing_evidence=extraction.missing_evidence,
        review_token=_issue_review_token(
            case_id=case_id,
            application=_review_snapshot(request),
            document_sha256=document.sha256,
        ),
        review_required=True,
    )


def run_reviewed_precheck(payload: ReviewedDocumentPrecheckRequest | dict[str, Any]) -> PrecheckResponse:
    """Run the full LangGraph workflow after the user confirms/corrects the draft."""

    request = payload if isinstance(payload, ReviewedDocumentPrecheckRequest) else ReviewedDocumentPrecheckRequest.model_validate(payload)
    if not request.review_confirmed:
        raise DocumentUploadError("review_confirmation_required")
    document = decode_document_upload(request.supporting_document, document_id=f"document-{uuid4()}")
    case_id = _verify_review_context(request, document_sha256=document.sha256)
    pipeline = run_pipeline(
        PipelineRequest(
            case_id=case_id,
            application=_runtime_application(request, case_id),
            runtime_document=document.model_dump(),
        ),
        config=PipelineConfig(),
    )
    if pipeline.extraction is not None and request.corrected_fields:
        for field_name in request.corrected_fields:
            if field_name in pipeline.extraction.provenance:
                pipeline.extraction.provenance[field_name] = pipeline.extraction.provenance[field_name].model_copy(
                    update={"source": "reviewer_correction", "evidence": "user_confirmed_review_value"}
                )
    return _precheck_response(pipeline, review_status="reviewed")

