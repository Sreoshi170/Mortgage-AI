"""Candidate historical target construction for HMDA action_taken."""

from __future__ import annotations

from collections import Counter
from dataclasses import dataclass
from typing import Any, Iterable, Mapping

from .spec import NEGATIVE_ACTION_CODE, POSITIVE_ACTION_CODE


@dataclass(frozen=True)
class TargetRecord:
    raw_code: str
    included: bool
    target: int | None
    status: str
    reason: str


def _normalize_action_code(value: object) -> str:
    if value is None:
        return ""
    return str(value).strip()


def construct_candidate_target(action_taken: object) -> TargetRecord:
    """Map only action codes 1 and 3 to a research label.

    The returned target is deliberately named and documented as a historical
    outcome label. It is not a creditworthiness or underwriting label.
    """

    raw_code = _normalize_action_code(action_taken)
    if raw_code == POSITIVE_ACTION_CODE:
        return TargetRecord(raw_code, True, 1, "positive_historical_outcome", "action_taken=1")
    if raw_code == NEGATIVE_ACTION_CODE:
        return TargetRecord(raw_code, True, 0, "negative_historical_outcome", "action_taken=3")
    if raw_code in {"", "NA", "Exempt"}:
        return TargetRecord(raw_code, False, None, "excluded_missing_or_special", "action_taken is missing or special")
    return TargetRecord(raw_code, False, None, "excluded_other_action_code", "only action_taken=1 and action_taken=3 are eligible")


def summarize_candidate_target(rows: Iterable[Mapping[str, Any]]) -> dict[str, Any]:
    """Summarize target eligibility without changing or retaining source rows."""

    action_counts: Counter[str] = Counter()
    excluded_counts: Counter[str] = Counter()
    total = eligible = positive = negative = 0
    for row in rows:
        total += 1
        record = construct_candidate_target(row.get("action_taken"))
        action_counts[record.raw_code or "<missing>"] += 1
        if record.included:
            eligible += 1
            if record.target == 1:
                positive += 1
            else:
                negative += 1
        else:
            excluded_counts[record.raw_code or "<missing>"] += 1
    return {
        "rows_inspected": total,
        "eligible_rows": eligible,
        "positive_rows": positive,
        "negative_rows": negative,
        "positive_prevalence": (positive / eligible) if eligible else None,
        "excluded_rows": total - eligible,
        "action_code_counts": dict(action_counts),
        "excluded_action_code_counts": dict(excluded_counts),
    }
