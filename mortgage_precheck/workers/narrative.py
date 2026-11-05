"""Deterministic decision-narrative worker."""

from __future__ import annotations

from ..schemas import DecisionNarrativeOutput, PolicyCheckOutput


def decision_narrative_worker(policy: PolicyCheckOutput) -> DecisionNarrativeOutput:
    """Create an evidence-linked non-final narrative from policy results."""

    rule_ids = [check.rule_id for check in policy.checks if check.status in {"flag", "missing"}]
    if policy.recommendation == "proceed":
        text = "The configured deterministic pre-check checks completed without a flagged rule. This is not a final lending decision."
    elif policy.recommendation == "documentation_incomplete":
        missing = ", ".join(policy.missing_fields) or "required information"
        text = f"The pre-check requires human follow-up because required information is unavailable: {missing}. This is not a final lending decision."
    else:
        evidence = "; ".join(
            check.evidence for check in policy.checks if check.status in {"flag", "missing"}
        ) or "A configured rule requires review."
        text = (
            "The pre-check requires human review because a configured rule was flagged. "
            f"Evidence: {evidence} This is not a final lending decision."
        )
    return DecisionNarrativeOutput(
        recommendation=policy.recommendation,
        narrative=text,
        evidence_rule_ids=rule_ids,
    )

