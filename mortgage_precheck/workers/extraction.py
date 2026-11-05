"""Deterministic extraction mock with a strict typed output contract."""

from __future__ import annotations

from decimal import Decimal, InvalidOperation
import re
from typing import Any

from ..schemas import (
    ApplicationInput,
    DocumentInput,
    ExtractedFact,
    ExtractionOutput,
    FieldProvenance,
    NormalizedSummary,
    ValidationFinding,
)


class ExtractionInputError(ValueError):
    code = "extraction_input_invalid"
    retryable = False


def _parse_number(value: object) -> float | None:
    if value is None or value == "" or str(value) in {"NA", "Exempt"}:
        return None
    try:
        number = Decimal(str(value))
    except (InvalidOperation, ValueError):
        return None
    if not number.is_finite():
        return None
    return float(number)


def _fact_number(value: str) -> int | float | None:
    parsed = _parse_number(value.replace(",", "").replace("$", "").strip())
    if parsed is None:
        return None
    return int(parsed) if parsed.is_integer() else parsed


def extract_document_facts(content: str, *, source: str, confidence: float = 0.90) -> dict[str, ExtractedFact]:
    """Extract only a small, labeled set of facts from text.

    This is intentionally deterministic and conservative. It records the
    source and confidence of regex matches, but never treats document text as
    authoritative over the reviewed structured application fields.
    """

    facts: dict[str, ExtractedFact] = {}

    patterns: tuple[tuple[str, str, Any], ...] = (
        ("loan_amount", r"(?:loan\s+amount|amount\s+requested)\s*[:\-]?\s*\$?\s*([0-9][0-9,]*(?:\.\d+)?)", _fact_number),
        ("annual_income", r"(?:annual\s+income|gross\s+annual\s+income)\s*[:\-]?\s*\$?\s*([0-9][0-9,]*(?:\.\d+)?)", _fact_number),
        ("property_value", r"property\s+value\s*[:\-]?\s*\$?\s*([0-9][0-9,]*(?:\.\d+)?)", _fact_number),
        ("monthly_debt_obligations", r"monthly\s+debt(?:\s+obligations)?\s*[:\-]?\s*\$?\s*([0-9][0-9,]*(?:\.\d+)?)", _fact_number),
        ("property_units", r"(?:number\s+of\s+units|units)\s*[:\-]?\s*([0-9]+)", _fact_number),
        # Percentage signs are presentation, not part of the normalized fact.
        # Keep document facts comparable with the numeric structured DTI field.
        ("debt_to_income_ratio", r"(?:debt\s*[- ]to\s*[- ]income|dti)\s*(?:ratio)?\s*[:\-]?\s*([0-9]+(?:\.\d+)?%?)", lambda value: _fact_number(value.rstrip("%"))),
        ("loan_type", r"loan\s+type\s*[:\-]?\s*(conventional|fha|va|usda|rhs|fsa)", lambda value: value.lower()),
        ("loan_purpose", r"loan\s+purpose\s*[:\-]?\s*([A-Za-z][A-Za-z /_-]*)", lambda value: value.strip().lower()),
        ("income_type", r"income\s+type\s*[:\-]?\s*([A-Za-z][A-Za-z /_-]*)", lambda value: value.strip().lower()),
        ("property_type", r"property\s+type\s*[:\-]?\s*([A-Za-z][A-Za-z /_-]*)", lambda value: value.strip().lower()),
        ("occupancy_type", r"occupancy(?:\s+type)?\s*[:\-]?\s*([A-Za-z][A-Za-z /_-]*)", lambda value: value.strip().lower()),
    )
    for field_name, pattern, parser in patterns:
        match = re.search(pattern, content, flags=re.IGNORECASE)
        if not match:
            continue
        value = parser(match.group(1))
        if value is None:
            continue
        facts[field_name] = ExtractedFact(
            value=value,
            provenance=FieldProvenance(
                source=source,
                confidence=confidence,
                evidence=f"labeled_document_field:{field_name}:line:{content[:match.start()].count(chr(10)) + 1}",
            ),
        )
    return facts


def _validation_findings(
    application: ApplicationInput,
    facts: dict[str, ExtractedFact],
    *,
    document_is_upload: bool,
) -> list[ValidationFinding]:
    findings: list[ValidationFinding] = []
    comparisons = {
        "loan_amount": _parse_number(application.loan_amount_numeric if application.loan_amount_numeric is not None else application.loan_amount),
        "annual_income": _parse_number(application.income_numeric if application.income_numeric is not None else application.income),
        "debt_to_income_ratio": _parse_number(application.debt_to_income_ratio),
        "property_value": _parse_number(application.property_value_numeric if application.property_value_numeric is not None else application.property_value),
        "monthly_debt_obligations": _parse_number(application.monthly_debt_obligations),
        "loan_type": application.loan_type,
        "loan_purpose": application.loan_purpose,
        "income_type": application.income_type,
        "property_type": application.property_type,
        "property_units": _parse_number(application.property_units),
        "occupancy_type": application.occupancy_type,
    }
    for field_name, application_value in comparisons.items():
        fact = facts.get(field_name)
        if fact is None or application_value is None:
            continue
        if field_name in {
            "loan_amount",
            "annual_income",
            "debt_to_income_ratio",
            "property_value",
            "monthly_debt_obligations",
            "property_units",
        }:
            fact_value = _parse_number(fact.value)
            differs = fact_value is not None and abs(fact_value - application_value) > 0.01
        else:
            fact_value = str(fact.value).strip().lower().replace("-", "_").replace(" ", "_")
            expected_value = str(application_value).strip().lower().replace("-", "_").replace(" ", "_")
            differs = fact_value != expected_value
        if differs:
            findings.append(
                ValidationFinding(
                    code="document_application_inconsistent",
                    severity="warning",
                    field=field_name,
                    message=f"Uploaded-document {field_name} differs from the structured application value.",
                )
            )
    if document_is_upload and not facts:
        findings.append(
            ValidationFinding(
                code="document_no_extractable_facts",
                severity="warning",
                field=None,
                message="The uploaded document did not contain a supported labeled fact.",
            )
        )
    monthly_debt = comparisons["monthly_debt_obligations"]
    annual_income = comparisons["annual_income"]
    dti = comparisons["debt_to_income_ratio"]
    if monthly_debt is not None and annual_income and dti is not None:
        derived_dti = monthly_debt * 12 / annual_income * 100
        if abs(derived_dti - dti) > 1.0:
            findings.append(
                ValidationFinding(
                    code="application_dti_inconsistent",
                    severity="warning",
                    field="debt_to_income_ratio",
                    message="Reported debt-to-income ratio differs from the ratio derived from annual income and monthly debt obligations.",
                )
            )
    loan_amount = comparisons["loan_amount"]
    property_value = comparisons["property_value"]
    if loan_amount is not None and property_value is not None and loan_amount > property_value:
        findings.append(
            ValidationFinding(
                code="loan_exceeds_property_value",
                severity="warning",
                field="loan_amount",
                message="Requested loan amount exceeds the submitted property value.",
            )
        )
    return findings


def extraction_worker(application: ApplicationInput, document: DocumentInput) -> ExtractionOutput:
    """Normalize fields and attach document facts with provenance.

    Synthetic fixtures retain their original path. User uploads use the same
    worker and add deterministic text facts; structured reviewed fields remain
    the values used by downstream policy checks.
    """

    if document.label not in {"SYNTHETIC", "USER_UPLOAD"}:
        raise ExtractionInputError("document_label_invalid")
    loan_amount = _parse_number(application.loan_amount_numeric)
    if loan_amount is None:
        loan_amount = _parse_number(application.loan_amount)
    if loan_amount is None or loan_amount <= 0:
        raise ExtractionInputError("loan_amount_missing_or_invalid")

    raw_values = {
        "income": application.income_numeric if application.income_numeric is not None else application.income,
        "co_applicant_annual_income": application.co_applicant_annual_income,
        "monthly_debt_obligations": application.monthly_debt_obligations,
        "property_units": application.property_units,
        "property_value": application.property_value_numeric
        if application.property_value_numeric is not None
        else application.property_value,
        "combined_loan_to_value_ratio": application.combined_loan_to_value_ratio_numeric
        if application.combined_loan_to_value_ratio_numeric is not None
        else application.combined_loan_to_value_ratio,
        "interest_rate": application.interest_rate_numeric
        if application.interest_rate_numeric is not None
        else application.interest_rate,
        "rate_spread": application.rate_spread_numeric
        if application.rate_spread_numeric is not None
        else application.rate_spread,
    }
    parsed = {key: _parse_number(value) for key, value in raw_values.items()}
    dti_raw = application.debt_to_income_ratio
    dti_numeric = _parse_number(dti_raw)
    dti_bucket = str(dti_raw) if dti_raw not in (None, "") and dti_numeric is None else None
    special_codes = {
        key: str(value)
        for key, value in {**raw_values, "debt_to_income_ratio": dti_raw}.items()
        if str(value) in {"NA", "Exempt"}
    }
    warnings = [
        f"unparsed_{key}"
        for key, value in parsed.items()
        if raw_values[key] not in (None, "", "NA", "Exempt") and value is None
    ]

    missing_fields = [name for name in ("income", "property_value", "loan_purpose", "income_type", "monthly_debt_obligations") if getattr(application, name, None) in (None, "")]
    if application.co_applicant_present and parsed["co_applicant_annual_income"] is None:
        missing_fields.append("co_applicant_annual_income")
    document_facts = extract_document_facts(
        document.content,
        source="synthetic_fixture" if document.label == "SYNTHETIC" else "uploaded_document",
    )
    findings = _validation_findings(application, document_facts, document_is_upload=document.label == "USER_UPLOAD")
    provenance = {
        name: FieldProvenance(
            source="synthetic_fixture" if document.label == "SYNTHETIC" else "structured_application",
            confidence=1.0,
            evidence="structured application field",
        )
        for name in (
            "loan_amount",
            "income",
            "property_value",
            "combined_loan_to_value_ratio",
            "debt_to_income_ratio",
            "loan_purpose",
            "income_type",
            "monthly_debt_obligations",
        )
    }
    # ``provenance`` describes values in the structured summary. Document
    # facts carry separate provenance inside ``extracted_facts`` and must not
    # silently replace the reviewed application source.
    missing_evidence = ["document_relevant_facts"] if document.label == "USER_UPLOAD" and not document_facts else []
    return ExtractionOutput(
        valid=True,
        summary=NormalizedSummary(
            case_id=application.case_id,
            applicant_type=application.applicant_type,
            co_applicant_present=application.co_applicant_present,
            co_applicant_annual_income=parsed["co_applicant_annual_income"],
            co_applicant_income_type=application.co_applicant_income_type,
            loan_amount=loan_amount,
            loan_purpose=application.loan_purpose,
            income_type=application.income_type,
            income=parsed["income"],
            monthly_debt_obligations=parsed["monthly_debt_obligations"],
            property_value=parsed["property_value"],
            property_type=application.property_type,
            property_units=(int(_parse_number(application.property_units)) if _parse_number(application.property_units) is not None else None),
            occupancy_type=application.occupancy_type,
            combined_loan_to_value_ratio=parsed["combined_loan_to_value_ratio"],
            interest_rate=parsed["interest_rate"],
            rate_spread=parsed["rate_spread"],
            debt_to_income_ratio=dti_numeric,
            debt_to_income_bucket=dti_bucket,
            special_codes=special_codes,
        ),
        missing_fields=missing_fields,
        warnings=warnings,
        extracted_facts=document_facts,
        provenance=provenance,
        confidence={name: fact.provenance.confidence for name, fact in document_facts.items()},
        validation_findings=findings,
        missing_evidence=missing_evidence,
    )

