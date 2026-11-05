"""Deterministic policy-check mock with configurable, caller-supplied limits."""

from __future__ import annotations

from ..config import PipelineConfig
from ..schemas import ExtractionOutput, PolicyCheckOutput, Recommendation, RuleResult


def policy_check_worker(extraction: ExtractionOutput, config: PipelineConfig) -> PolicyCheckOutput:
    checks: list[RuleResult] = []
    missing = [*extraction.missing_fields, *extraction.missing_evidence]

    checks.append(
        RuleResult(
            rule_id="DOC-001",
            status="pass" if extraction.valid else "missing",
            evidence="Extraction output passed the typed schema contract." if extraction.valid else "Extraction output was not valid.",
        )
    )
    if extraction.summary.property_value is None:
        checks.append(RuleResult(rule_id="DOC-002", status="missing", evidence="Property value is unavailable."))
    else:
        checks.append(RuleResult(rule_id="DOC-002", status="pass", evidence="Property value is present."))
    if extraction.summary.income is None:
        checks.append(RuleResult(rule_id="DOC-003", status="missing", evidence="Income is unavailable."))
    else:
        checks.append(RuleResult(rule_id="DOC-003", status="pass", evidence="Income is present."))

    if extraction.validation_findings:
        finding_fields = sorted(
            {finding.field for finding in extraction.validation_findings if finding.field}
        )
        finding_scope = ", ".join(finding_fields) or "the submitted evidence"
        checks.append(
            RuleResult(
                rule_id="DOC-004",
                status="flag",
                evidence=(
                    "Document/application validation found information requiring human review "
                    f"for: {finding_scope}."
                ),
            )
        )

    flags: list[str] = []
    dti = extraction.summary.debt_to_income_ratio
    if extraction.summary.debt_to_income_bucket == ">60%":
        flags.append("POL-001")
        checks.append(RuleResult(rule_id="POL-001", status="flag", evidence="DTI is reported in the >60% bucket."))
    elif config.policy_dti_max is not None and dti is not None:
        status = "flag" if dti > config.policy_dti_max else "pass"
        checks.append(
            RuleResult(
                rule_id="POL-001",
                status=status,
                evidence=f"Numeric DTI {dti:g} compared with configured limit {config.policy_dti_max:g}.",
            )
        )
        if status == "flag":
            flags.append("POL-001")

    ltv = extraction.summary.combined_loan_to_value_ratio
    if config.policy_ltv_max is not None and ltv is not None:
        status = "flag" if ltv > config.policy_ltv_max else "pass"
        checks.append(
            RuleResult(
                rule_id="POL-002",
                status=status,
                evidence=f"Numeric CLTV {ltv:g} compared with configured limit {config.policy_ltv_max:g}.",
            )
        )
        if status == "flag":
            flags.append("POL-002")

    recommendation: Recommendation
    if missing:
        recommendation = "documentation_incomplete"
    elif flags or extraction.validation_findings:
        recommendation = "flag_for_manual_review"
    else:
        recommendation = "proceed"
    return PolicyCheckOutput(recommendation=recommendation, checks=checks, missing_fields=missing)

