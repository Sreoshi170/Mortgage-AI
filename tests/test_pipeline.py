from __future__ import annotations

import time

import pytest

from mortgage_precheck.boundary import BoundaryViolation, sanitize_application
from mortgage_precheck.config import EvaluationThresholds, PipelineConfig, RuntimeConfig
from mortgage_precheck.graph import WorkerSet, run_pipeline
from mortgage_precheck.schemas import ExtractionOutput, PipelineRequest, PolicyCheckOutput, RuleResult


def request(**overrides):
    application = {
        "activity_year": 2025,
        "loan_amount": "195000",
        "property_value": "215000",
        "income": "86",
        "debt_to_income_ratio": "41",
        "combined_loan_to_value_ratio": "95.0",
        "interest_rate": "6.125",
        "rate_spread": "0.166",
        "loan_type": "1",
        "loan_purpose": "1",
        "occupancy_type": "1",
    }
    application.update(overrides.pop("application", {}))
    return PipelineRequest(
        case_id="case-1",
        application=application,
        synthetic_document={"document_id": "doc-1", "label": "SYNTHETIC", "content": "Income letter"},
        **overrides,
    )


def test_successful_execution_runs_four_workers_and_is_not_a_gate_pass():
    result = run_pipeline(request())
    assert result.extraction is not None
    assert result.policy is not None
    assert result.narrative is not None
    assert result.fairness is not None
    assert result.status == "needs_human_review"
    assert result.gate_status == "not_run"
    nodes = {event.node for event in result.audit_events if event.event_type == "worker_completed"}
    assert nodes == {
        "extraction_worker",
        "policy_check_worker",
        "decision_narrative_worker",
        "fairness_check_worker",
    }


def test_missing_document_fails_at_boundary_without_worker_calls():
    payload = request().model_dump()
    payload.pop("synthetic_document")
    result = run_pipeline(payload)
    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == "request_schema_invalid"
    assert not any(event.event_type == "worker_started" for event in result.audit_events)


def test_invalid_loan_amount_fails_closed_after_bounded_attempts():
    result = run_pipeline(request(application={"loan_amount": "not-a-number"}))
    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == "extraction_input_invalid"
    attempts = [event.attempt for event in result.audit_events if event.node == "extraction_worker" and event.event_type == "worker_started"]
    # Deterministic input validation is non-retryable by design.
    assert attempts == [1]


def test_worker_failure_retries_then_fails_at_limit():
    calls = {"count": 0}

    def always_fails(application, document):
        calls["count"] += 1
        raise RuntimeError("simulated failure")

    result = run_pipeline(
        request(),
        config=PipelineConfig(runtime=RuntimeConfig(max_attempts=2, timeout_seconds=1, max_graph_steps=5)),
        workers=WorkerSet(extraction=always_fails),
    )
    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == "worker_exception"
    assert calls["count"] == 2


def test_retry_then_success_continues_graph():
    calls = {"count": 0}
    from mortgage_precheck.workers.extraction import extraction_worker

    def flaky(application, document):
        calls["count"] += 1
        if calls["count"] == 1:
            raise TimeoutError("retry me")
        return extraction_worker(application, document)

    result = run_pipeline(request(), workers=WorkerSet(extraction=flaky))
    assert result.extraction is not None
    assert calls["count"] == 2
    assert result.policy is not None


def test_timeout_is_bounded_and_recorded():
    def slow(application, document):
        time.sleep(0.2)
        raise RuntimeError("too slow")

    started = time.perf_counter()
    result = run_pipeline(
        request(),
        config=PipelineConfig(runtime=RuntimeConfig(max_attempts=1, timeout_seconds=0.01, max_graph_steps=5)),
        workers=WorkerSet(extraction=slow),
    )
    elapsed = time.perf_counter() - started
    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == "worker_timeout"
    assert elapsed < 0.15


def test_protected_fields_are_rejected_and_never_enter_worker_or_audit_state():
    payload = request(application={"race": "Black"}).model_dump()
    result = run_pipeline(payload)
    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == "protected_field_detected"
    serialized = result.model_dump_json().lower()
    assert "black" not in serialized
    assert '"race"' not in serialized

    with pytest.raises(BoundaryViolation):
        sanitize_application("case-1", {"sex_code": "1", "loan_amount": "195000"})


def test_outcome_field_is_rejected_from_worker_input():
    result = run_pipeline(request(application={"action_taken": "1"}))
    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == "outcome_field_detected"


def test_proxy_fields_are_rejected_until_explicitly_reviewed():
    result = run_pipeline(request(application={"county_code": "55069"}))
    assert result.status == "failed"
    assert result.failure is not None
    assert result.failure.code == "proxy_field_requires_review"


def test_locked_thresholds_fail_closed_when_not_locked_or_incomplete():
    with pytest.raises(ValueError):
        EvaluationThresholds(version="exp-1", correctness=0.9, fairness=0.9).require_locked()
    with pytest.raises(ValueError):
        EvaluationThresholds(version="exp-1", locked=True).require_locked()
    locked = EvaluationThresholds(version="exp-1", correctness=0.9, fairness=0.9, locked=True)
    locked.require_locked()

