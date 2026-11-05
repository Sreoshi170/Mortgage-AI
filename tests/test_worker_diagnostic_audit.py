"""Isolated worker contracts used by the diagnostic audit."""

from __future__ import annotations

from mortgage_precheck.config import PipelineConfig
from mortgage_precheck.schemas import (
    ApplicationInput,
    DecisionNarrativeOutput,
    FairnessCheckOutput,
    PolicyCheckOutput,
    RuleResult,
    RuntimeDocument,
)
from mortgage_precheck.workers.extraction import extraction_worker, extract_document_facts
from mortgage_precheck.workers.fairness import fairness_check_worker
from mortgage_precheck.workers.narrative import decision_narrative_worker
from mortgage_precheck.workers.policy import policy_check_worker


def application(**overrides) -> ApplicationInput:
    values = {
        "case_id": "isolated-worker-case",
        "applicant_type": "individual",
        "co_applicant_present": False,
        "loan_amount": 250000,
        "income": 60000,
        "income_type": "employment",
        "monthly_debt_obligations": 1900,
        "loan_type": "conventional",
        "loan_purpose": "purchase",
        "debt_to_income_ratio": 38,
        "property_value": 300000,
        "property_type": "single_family",
        "property_units": 1,
        "occupancy_type": "primary_residence",
    }
    values.update(overrides)
    return ApplicationInput.model_validate(values)


def document(content: str) -> RuntimeDocument:
    return RuntimeDocument(
        document_id="isolated-runtime-document",
        label="USER_UPLOAD",
        filename="synthetic.txt",
        media_type="text/plain",
        size_bytes=len(content.encode("utf-8")),
        sha256="0" * 64,
        extraction_method="utf8_text",
        content=content,
    )


def test_extraction_worker_keeps_structured_summary_separate_from_document_facts():
    output = extraction_worker(
        application(),
        document(
            "Loan Amount: 325000\n"
            "Annual Income: 1200000\n"
            "Monthly Debt Obligations: 1800\n"
            "Property Value: 325000\n"
        ),
    )

    assert output.summary.loan_amount == 250000
    assert output.summary.income == 60000
    assert output.summary.monthly_debt_obligations == 1900
    assert output.summary.property_value == 300000
    assert output.extracted_facts["annual_income"].value == 1200000
    assert output.extracted_facts["monthly_debt_obligations"].value == 1800
    assert output.extracted_facts["property_value"].value == 325000
    assert output.extracted_facts["annual_income"].provenance.source == "uploaded_document"
    assert output.extracted_facts["annual_income"].provenance.confidence == 0.9
    assert any(
        finding.code == "document_application_inconsistent" and finding.field == "annual_income"
        for finding in output.validation_findings
    )


def test_extraction_worker_reports_source_lines_and_missing_document_facts():
    facts = extract_document_facts(
        "Ignored header\nAnnual Income: 60000\nLoan Amount: 250000",
        source="uploaded_document",
    )
    output = extraction_worker(application(), document("Synthetic letter without labeled facts"))

    assert facts["annual_income"].provenance.evidence.endswith(":line:2")
    assert output.extracted_facts == {}
    assert output.missing_evidence == ["document_relevant_facts"]
    assert any(item.code == "document_no_extractable_facts" for item in output.validation_findings)


def test_extraction_worker_is_deterministic_for_repeated_labels_and_does_not_claim_ambiguity():
    facts = extract_document_facts(
        "Loan Amount: 250000 or Loan Amount: 325000",
        source="uploaded_document",
    )

    assert facts["loan_amount"].value == 250000


def test_policy_worker_clean_input_has_no_unconfigured_lending_threshold():
    extraction = extraction_worker(
        application(),
        document(
            "Loan Amount: 250000\nAnnual Income: 60000\n"
            "Monthly Debt Obligations: 1900\nProperty Value: 300000"
        ),
    )

    output = policy_check_worker(extraction, PipelineConfig())

    assert output.recommendation == "proceed"
    assert {check.rule_id for check in output.checks} == {"DOC-001", "DOC-002", "DOC-003"}
    assert not any(check.rule_id.startswith("POL-") for check in output.checks)


def test_policy_worker_executes_caller_configured_rule_and_traces_evidence():
    extraction = extraction_worker(
        application(debt_to_income_ratio=50, monthly_debt_obligations=2500),
        document(
            "Loan Amount: 250000\nAnnual Income: 60000\n"
            "Monthly Debt Obligations: 2500\nProperty Value: 300000"
        ),
    )

    output = policy_check_worker(extraction, PipelineConfig(policy_dti_max=40))

    dti_check = next(check for check in output.checks if check.rule_id == "POL-001")
    assert dti_check.status == "flag"
    assert "50" in dti_check.evidence
    assert "40" in dti_check.evidence
    assert output.recommendation == "flag_for_manual_review"


def test_policy_worker_marks_missing_evidence_incomplete():
    extraction = extraction_worker(
        application(income=None, property_value=None, monthly_debt_obligations=None),
        document("Synthetic letter"),
    )

    output = policy_check_worker(extraction, PipelineConfig())

    assert output.recommendation == "documentation_incomplete"
    assert {"income", "property_value", "monthly_debt_obligations"} <= set(output.missing_fields)
    assert {check.rule_id for check in output.checks if check.status == "missing"} >= {"DOC-002", "DOC-003"}


def test_policy_worker_conflict_evidence_names_affected_fields():
    extraction = extraction_worker(
        application(),
        document("Loan Amount: 325000\nAnnual Income: 1200000\n"),
    )

    output = policy_check_worker(extraction, PipelineConfig())
    conflict_check = next(check for check in output.checks if check.rule_id == "DOC-004")

    assert conflict_check.status == "flag"
    assert "annual_income" in conflict_check.evidence
    assert "loan_amount" in conflict_check.evidence
    assert output.recommendation == "flag_for_manual_review"


def test_narrative_worker_describes_missing_evidence_without_approval_language():
    policy = PolicyCheckOutput(
        recommendation="documentation_incomplete",
        checks=[RuleResult(rule_id="DOC-002", status="missing", evidence="Property value is unavailable.")],
        missing_fields=["property_value"],
    )

    output = decision_narrative_worker(policy)

    assert "property_value" in output.narrative
    assert "not a final lending decision" in output.narrative
    assert "approve" not in output.narrative.lower()
    assert "deny" not in output.narrative.lower()


def test_narrative_worker_describes_conflict_evidence_from_policy():
    policy = PolicyCheckOutput(
        recommendation="flag_for_manual_review",
        checks=[
            RuleResult(
                rule_id="DOC-004",
                status="flag",
                evidence="Document/application validation found information requiring human review for: annual_income.",
            )
        ],
    )

    output = decision_narrative_worker(policy)

    assert "annual_income" in output.narrative
    assert output.evidence_rule_ids == ["DOC-004"]
    assert "approve" not in output.narrative.lower()
    assert "deny" not in output.narrative.lower()


def test_fairness_worker_returns_not_evaluable_without_authorized_demographic_evaluation_inputs():
    policy = PolicyCheckOutput(
        recommendation="proceed",
        checks=[RuleResult(rule_id="DOC-001", status="pass", evidence="Typed output passed.")],
    )
    narrative = DecisionNarrativeOutput(
        recommendation="proceed",
        narrative="The configured deterministic checks completed. This is not a final lending decision.",
        evidence_rule_ids=[],
    )

    output = fairness_check_worker(application(), policy, narrative)

    assert output.status == "not_evaluable"
    assert output.protected_data_seen is False
    assert "unavailable" in output.concerns[0]


def test_fairness_worker_can_flag_prohibited_reasoning_terms_without_receiving_protected_data():
    policy = PolicyCheckOutput(
        recommendation="flag_for_manual_review",
        checks=[RuleResult(rule_id="DOC-004", status="flag", evidence="Review required.")],
    )
    narrative = DecisionNarrativeOutput(
        recommendation="flag_for_manual_review",
        narrative="Review because of race-related reasoning. This is not a final lending decision.",
        evidence_rule_ids=["DOC-004"],
    )

    output = fairness_check_worker(application(), policy, narrative)

    assert output.status == "not_evaluable"
    assert output.protected_data_seen is False
    assert output.requires_human_review is True
