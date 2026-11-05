"""Typed contracts shared by the graph and its four workers."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Literal

from pydantic import BaseModel, ConfigDict, Field, field_validator, model_validator

Recommendation = Literal["proceed", "flag_for_manual_review", "documentation_incomplete"]
RunStatus = Literal["completed", "needs_human_review", "failed"]
# A fairness result is only evaluable when separately governed demographic
# evaluation data is available. The runtime worker intentionally does not
# receive that data, so its normal state is ``not_evaluable``. The other two
# states are reserved for a separately authorized offline evaluation.
FairnessStatus = Literal["not_evaluable", "evaluated_no_findings", "evaluated_with_findings"]
RuleStatus = Literal["pass", "flag", "missing"]


class PipelineRequest(BaseModel):
    """External request accepted by the foundation."""

    model_config = ConfigDict(extra="forbid")

    case_id: str = Field(min_length=1)
    application: dict[str, Any]
    synthetic_document: dict[str, Any] | None = None
    runtime_document: dict[str, Any] | None = None
    evaluation_only: dict[str, Any] | None = None
    run_id: str | None = None

    @model_validator(mode="after")
    def exactly_one_document_contract(self) -> "PipelineRequest":
        if (self.synthetic_document is None) == (self.runtime_document is None):
            raise ValueError("exactly one of synthetic_document or runtime_document is required")
        return self


class ApplicationInput(BaseModel):
    """Sanitized model-visible application fields.

    Raw source values remain strings where the inspection found special codes
    such as ``NA`` or ``Exempt``. Protected and outcome fields are rejected by
    the boundary before this model is created.
    """

    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str = Field(min_length=1)
    applicant_type: Literal["individual", "joint"] = "individual"
    co_applicant_present: bool = False
    co_applicant_annual_income: str | int | float | None = None
    co_applicant_income_type: str | None = None
    activity_year: str | int | None = None
    conforming_loan_limit: str | None = None
    derived_loan_product_type: str | None = None
    derived_dwelling_category: str | None = None
    loan_type: str | None = None
    loan_purpose: str | None = None
    loan_amount: str | int | float | None = None
    combined_loan_to_value_ratio: str | int | float | None = None
    interest_rate: str | int | float | None = None
    rate_spread: str | int | float | None = None
    property_value: str | int | float | None = None
    property_type: str | None = None
    property_units: str | int | None = None
    occupancy_type: str | None = None
    income: str | int | float | None = None
    income_type: str | None = None
    monthly_debt_obligations: str | int | float | None = None
    debt_to_income_ratio: str | int | float | None = None
    loan_amount_numeric: str | int | float | None = None
    combined_loan_to_value_ratio_numeric: str | int | float | None = None
    interest_rate_numeric: str | int | float | None = None
    rate_spread_numeric: str | int | float | None = None
    property_value_numeric: str | int | float | None = None
    income_numeric: str | int | float | None = None


class SyntheticDocument(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(min_length=1)
    label: Literal["SYNTHETIC"]
    content: str = Field(min_length=1)

    @field_validator("content")
    @classmethod
    def content_must_not_be_empty(cls, value: str) -> str:
        return value


class RuntimeDocument(BaseModel):
    """Sanitized user-upload document passed to the existing extraction worker."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str = Field(min_length=1)
    label: Literal["USER_UPLOAD"]
    filename: str = Field(min_length=1)
    media_type: str = Field(min_length=1)
    size_bytes: int = Field(gt=0)
    sha256: str = Field(min_length=64, max_length=64)
    extraction_method: Literal["utf8_text", "pdf_text"]
    content: str = Field(min_length=1)
    upload_source: Literal["user_upload"] = "user_upload"


DocumentInput = SyntheticDocument | RuntimeDocument


class FieldProvenance(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    source: Literal["structured_application", "uploaded_document", "reviewer_correction", "synthetic_fixture"]
    confidence: float = Field(ge=0, le=1)
    evidence: str = Field(min_length=1)


class ExtractedFact(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    value: str | int | float
    provenance: FieldProvenance


class ValidationFinding(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str = Field(min_length=1)
    severity: Literal["info", "warning", "error"]
    field: str | None = None
    message: str = Field(min_length=1)


class NormalizedSummary(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    applicant_type: Literal["individual", "joint"] = "individual"
    co_applicant_present: bool = False
    co_applicant_annual_income: float | None = None
    co_applicant_income_type: str | None = None
    loan_amount: float
    loan_purpose: str | None = None
    income_type: str | None = None
    income: float | None = None
    monthly_debt_obligations: float | None = None
    property_value: float | None = None
    property_type: str | None = None
    property_units: int | None = None
    occupancy_type: str | None = None
    combined_loan_to_value_ratio: float | None = None
    interest_rate: float | None = None
    rate_spread: float | None = None
    debt_to_income_ratio: float | None = None
    debt_to_income_bucket: str | None = None
    special_codes: dict[str, str] = Field(default_factory=dict)


class ExtractionOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    valid: bool
    summary: NormalizedSummary
    missing_fields: list[str] = Field(default_factory=list)
    warnings: list[str] = Field(default_factory=list)
    extracted_facts: dict[str, ExtractedFact] = Field(default_factory=dict)
    provenance: dict[str, FieldProvenance] = Field(default_factory=dict)
    confidence: dict[str, float] = Field(default_factory=dict)
    validation_findings: list[ValidationFinding] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)


class RuleResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    rule_id: str
    status: RuleStatus
    evidence: str = Field(min_length=1)


class PolicyCheckOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recommendation: Recommendation
    checks: list[RuleResult]
    missing_fields: list[str] = Field(default_factory=list)


class DecisionNarrativeOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    recommendation: Recommendation
    narrative: str = Field(min_length=1)
    evidence_rule_ids: list[str]


class FairnessCheckOutput(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: FairnessStatus
    concerns: list[str] = Field(default_factory=list)
    inspected_rule_ids: list[str]
    protected_data_seen: bool = False
    # A reasoning-integrity concern can require review even though no
    # demographic fairness evaluation was possible. This field deliberately
    # keeps that operational routing separate from the fairness status.
    requires_human_review: bool = False

    @field_validator("protected_data_seen")
    @classmethod
    def protected_data_must_never_be_seen(cls, value: bool) -> bool:
        if value:
            raise ValueError("fairness worker received protected data")
        return value


class WorkerError(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    code: str
    retryable: bool
    message: str


class AuditEvent(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    event_id: str
    timestamp: datetime
    run_id: str
    case_id: str
    node: str
    event_type: str
    status: str
    attempt: int = Field(ge=1)
    details: dict[str, str | int | float | bool | None] = Field(default_factory=dict)


class PipelineResult(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    run_id: str
    case_id: str
    status: RunStatus
    recommendation: Recommendation | None = None
    extraction: ExtractionOutput | None = None
    policy: PolicyCheckOutput | None = None
    narrative: DecisionNarrativeOutput | None = None
    fairness: FairnessCheckOutput | None = None
    audit_events: list[AuditEvent]
    failure: WorkerError | None = None
    gate_status: Literal["not_run"] = "not_run"


class RuntimeApplicationFields(BaseModel):
    """Non-sensitive runtime application fields accepted from the form.

    Names, contact details, government identifiers, protected attributes, and
    free-form applicant narratives are intentionally not collected here.
    Values are kept separate from historical HMDA research inputs.
    """

    model_config = ConfigDict(extra="forbid")

    applicant_type: Literal["individual", "joint"] = "individual"
    co_applicant_present: bool = False
    co_applicant_annual_income: int | float | None = Field(default=None, ge=0)
    co_applicant_income_type: str | None = Field(default=None, min_length=1)
    loan_amount: int | float = Field(gt=0)
    annual_income: int | float = Field(gt=0)
    income_type: str | None = Field(default=None, min_length=1)
    monthly_debt_obligations: int | float | None = Field(default=None, ge=0)
    loan_type: str = Field(min_length=1)
    loan_purpose: str | None = Field(default=None, min_length=1)
    debt_to_income_ratio: int | float | str
    property_value: int | float | None = Field(default=None, gt=0)
    property_type: str | None = Field(default=None, min_length=1)
    property_units: int | None = Field(default=None, ge=1)
    occupancy_type: str | None = Field(default=None, min_length=1)

    @model_validator(mode="after")
    def validate_joint_application(self) -> "RuntimeApplicationFields":
        if isinstance(self.debt_to_income_ratio, (int, float)) and not 0 <= self.debt_to_income_ratio <= 100:
            raise ValueError("debt_to_income_ratio must be between 0 and 100")
        if self.applicant_type == "joint" and not self.co_applicant_present:
            raise ValueError("co_applicant_present must be true for a joint application")
        if not self.co_applicant_present and (
            self.co_applicant_annual_income is not None or self.co_applicant_income_type is not None
        ):
            raise ValueError("co-applicant fields require co_applicant_present=true")
        return self


class PrecheckRequest(RuntimeApplicationFields):
    """Applicant-facing form contract with a synthetic text document path."""

    supporting_document: str = Field(min_length=1)


class SupportingDocumentInput(BaseModel):
    """JSON-safe upload envelope used by the browser without multipart dependencies."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    filename: str = Field(min_length=1, max_length=255)
    media_type: str = Field(min_length=1, max_length=120)
    content_base64: str = Field(min_length=1)


class DocumentPrecheckRequest(RuntimeApplicationFields):
    """Runtime application plus an uploaded supporting document."""

    supporting_document: SupportingDocumentInput


class ReviewedDocumentPrecheckRequest(DocumentPrecheckRequest):
    review_confirmed: bool = False
    corrected_fields: list[str] = Field(default_factory=list)
    review_token: str | None = Field(default=None, min_length=32, max_length=10_000)


class DocumentDescriptor(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    document_id: str
    filename: str
    media_type: str
    size_bytes: int
    sha256: str
    extraction_method: Literal["utf8_text", "pdf_text"]


class DocumentExtractionDraft(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    case_id: str
    document: DocumentDescriptor
    extracted_facts: dict[str, ExtractedFact] = Field(default_factory=dict)
    validation_findings: list[ValidationFinding] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    # Signed, short-lived context tying a subsequent review to this exact
    # document digest and structured-form snapshot. It contains no document
    # content and is not written to audit events.
    review_token: str = Field(min_length=32)
    review_required: bool = True


class PrecheckPolicyCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: Literal["clear", "flagged"]
    reason: str = Field(min_length=1)


class PrecheckFairnessCheck(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True)

    status: FairnessStatus
    reason: str = Field(min_length=1)


class PrecheckResponse(BaseModel):
    """Applicant-facing response with the complete typed trace retained."""

    model_config = ConfigDict(extra="forbid", frozen=True)

    extraction_status: Literal["success", "failed"]
    policy_check: PrecheckPolicyCheck
    recommendation: str
    fairness_check: PrecheckFairnessCheck
    human_review_required: bool
    explanation: str = Field(min_length=1)
    pipeline_trace: PipelineResult
    extracted_facts: dict[str, ExtractedFact] = Field(default_factory=dict)
    validation_findings: list[ValidationFinding] = Field(default_factory=list)
    missing_evidence: list[str] = Field(default_factory=list)
    review_status: Literal["not_applicable", "review_required", "reviewed"] = "not_applicable"
    research_only: Literal[True] = True

