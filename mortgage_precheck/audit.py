"""Structured audit events with no raw application or demographic payloads."""

from __future__ import annotations

from datetime import datetime, timezone
from uuid import uuid4

from .schemas import AuditEvent

_FORBIDDEN_DETAIL_TOKENS = ("race", "ethnicity", "sex", "gender", "disability", "applicant_age")


def make_audit_event(
    *,
    run_id: str,
    case_id: str,
    node: str,
    event_type: str,
    status: str,
    attempt: int,
    details: dict[str, str | int | float | bool | None] | None = None,
) -> AuditEvent:
    """Create a small structured event; callers must provide summary details only."""

    safe_details = details or {}
    if any(any(token in key.lower() for token in _FORBIDDEN_DETAIL_TOKENS) for key in safe_details):
        raise ValueError("audit detail key is not allowed")
    return AuditEvent(
        event_id=str(uuid4()),
        timestamp=datetime.now(timezone.utc),
        run_id=run_id,
        case_id=case_id,
        node=node,
        event_type=event_type,
        status=status,
        attempt=attempt,
        details=safe_details,
    )

