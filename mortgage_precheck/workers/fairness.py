"""Reasoning-integrity review that never claims a demographic fairness result."""

from __future__ import annotations

from ..schemas import (
    ApplicationInput,
    DecisionNarrativeOutput,
    FairnessCheckOutput,
    PolicyCheckOutput,
)

_PROHIBITED_REASONING_TERMS = (
    "race",
    "ethnicity",
    "sex",
    "gender",
    "disability",
    "neighborhood",
    "zip code",
    "zipcode",
)


def fairness_check_worker(
    application: ApplicationInput,
    policy: PolicyCheckOutput,
    narrative: DecisionNarrativeOutput,
) -> FairnessCheckOutput:
    """Review reasoning text only; never access demographic evaluation fields.

    This worker cannot make a fairness determination: protected demographic
    evaluation data is intentionally outside the runtime graph. A prohibited
    term in the narrative is therefore a *reasoning-integrity* concern that
    routes to human review, not an asserted group-fairness finding.
    """

    del application
    text = narrative.narrative.lower()
    concerns = [term for term in _PROHIBITED_REASONING_TERMS if term in text]
    if concerns:
        return FairnessCheckOutput(
            status="not_evaluable",
            concerns=[
                "Narrative references a protected attribute or possible proxy; "
                "human review is required. This is not a demographic fairness evaluation."
            ],
            inspected_rule_ids=narrative.evidence_rule_ids,
            protected_data_seen=False,
            requires_human_review=True,
        )
    return FairnessCheckOutput(
        status="not_evaluable",
        concerns=[
            "No authorized demographic evaluation ran because demographic evaluation "
            "data is intentionally unavailable to this worker. This is not evidence of fairness."
        ],
        inspected_rule_ids=[check.rule_id for check in policy.checks],
        protected_data_seen=False,
        requires_human_review=False,
    )

