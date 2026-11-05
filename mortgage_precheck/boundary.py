"""Fail-closed boundary between source/evaluation data and workers."""

from __future__ import annotations

import re
from typing import Any

from pydantic import ValidationError

from .schemas import ApplicationInput, RuntimeDocument, SyntheticDocument

PROTECTED_FIELD_NAMES = frozenset(
    {
        "race",
        "race_code",
        "ethnicity",
        "ethnicity_code",
        "sex",
        "sex_code",
        "gender",
        "gender_code",
        "applicant_race",
        "co_applicant_race",
        "applicant_ethnicity",
        "co_applicant_ethnicity",
        "applicant_sex",
        "co_applicant_sex",
        "applicant_age",
        "co_applicant_age",
        "age",
        "disability",
    }
)
FORBIDDEN_WORKER_FIELDS = frozenset({"action_taken", "target", "label", "outcome"})
PROXY_FIELDS_REQUIRING_REVIEW = frozenset({"lei", "state_code", "county_code", "zip_code", "zipcode"})


class BoundaryViolation(ValueError):
    """Raised when data cannot safely enter ordinary worker state."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


def _normalized_key(key: object) -> str:
    return re.sub(r"[^a-z0-9]+", "_", str(key).strip().lower()).strip("_")


def _is_protected_key(key: object) -> bool:
    normalized = _normalized_key(key)
    if normalized in PROTECTED_FIELD_NAMES:
        return True
    return any(
        token in normalized
        for token in ("race", "ethnicity", "sex", "gender", "age", "disability")
    )


def sanitize_application(case_id: str, payload: dict[str, Any]) -> ApplicationInput:
    """Validate a worker-visible application without silently dropping fields."""

    if any(_is_protected_key(key) for key in payload):
        raise BoundaryViolation("protected_field_detected")
    if any(_normalized_key(key) in FORBIDDEN_WORKER_FIELDS for key in payload):
        raise BoundaryViolation("outcome_field_detected")
    if any(_normalized_key(key) in PROXY_FIELDS_REQUIRING_REVIEW for key in payload):
        raise BoundaryViolation("proxy_field_requires_review")

    candidate = dict(payload)
    candidate["case_id"] = case_id
    try:
        return ApplicationInput.model_validate(candidate)
    except ValidationError as exc:
        raise BoundaryViolation("application_schema_invalid") from exc


def sanitize_synthetic_document(payload: dict[str, Any]) -> SyntheticDocument:
    try:
        return SyntheticDocument.model_validate(payload)
    except ValidationError as exc:
        raise BoundaryViolation("synthetic_document_invalid") from exc


def sanitize_runtime_document(payload: dict[str, Any]) -> RuntimeDocument:
    """Validate a decoded upload envelope without retaining protected metadata."""

    try:
        return RuntimeDocument.model_validate(payload)
    except ValidationError as exc:
        raise BoundaryViolation("runtime_document_invalid") from exc

