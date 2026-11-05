"""Explicit, bounded LangGraph orchestration for the four worker foundation."""

from __future__ import annotations

from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from dataclasses import dataclass
from typing import Any, Callable
from uuid import uuid4

from langgraph.graph import END, START, StateGraph

from .audit import make_audit_event
from .boundary import BoundaryViolation, sanitize_application, sanitize_runtime_document, sanitize_synthetic_document
from .config import PipelineConfig
from .schemas import (
    ApplicationInput,
    DecisionNarrativeOutput,
    ExtractionOutput,
    FairnessCheckOutput,
    PipelineRequest,
    PipelineResult,
    PolicyCheckOutput,
    DocumentInput,
    WorkerError,
)
from .state import PipelineState
from .workers import (
    decision_narrative_worker,
    extraction_worker,
    fairness_check_worker,
    policy_check_worker,
)


class WorkerExecutionError(RuntimeError):
    def __init__(self, code: str, retryable: bool, message: str = "worker execution failed"):
        super().__init__(message)
        self.code = code
        self.retryable = retryable


@dataclass(frozen=True)
class WorkerSet:
    extraction: Callable[[ApplicationInput, DocumentInput], ExtractionOutput] = extraction_worker
    policy: Callable[[ExtractionOutput, PipelineConfig], PolicyCheckOutput] = policy_check_worker
    narrative: Callable[[PolicyCheckOutput], DecisionNarrativeOutput] = decision_narrative_worker
    fairness: Callable[[ApplicationInput, PolicyCheckOutput, DecisionNarrativeOutput], FairnessCheckOutput] = (
        fairness_check_worker
    )


def _safe_error(exc: BaseException) -> WorkerError:
    if isinstance(exc, WorkerExecutionError):
        return WorkerError(code=exc.code, retryable=exc.retryable, message=exc.code)
    if isinstance(exc, TimeoutError):
        return WorkerError(code="worker_timeout", retryable=True, message="worker_timeout")
    return WorkerError(
        code=getattr(exc, "code", "worker_exception"),
        retryable=getattr(exc, "retryable", True),
        message="worker_exception",
    )


def _append_event(state: PipelineState, event: Any) -> list[Any]:
    return [*state.get("audit_events", []), event]


def _execute_with_timeout(function: Callable[[], Any], timeout_seconds: float) -> Any:
    executor = ThreadPoolExecutor(max_workers=1)
    future = executor.submit(function)
    timed_out = False
    try:
        return future.result(timeout=timeout_seconds)
    except FutureTimeoutError as exc:
        timed_out = True
        future.cancel()
        raise TimeoutError("worker_timeout") from exc
    finally:
        executor.shutdown(wait=not timed_out, cancel_futures=True)


def _validate_worker_output(output_key: str, output: Any) -> Any:
    """Keep malformed custom-worker results inside the typed failure boundary."""

    output_types = {
        "extraction": ExtractionOutput,
        "policy": PolicyCheckOutput,
        "narrative": DecisionNarrativeOutput,
        "fairness": FairnessCheckOutput,
    }
    output_type = output_types.get(output_key)
    if output_type is None:
        raise WorkerExecutionError("worker_output_contract_invalid", retryable=False)
    return output_type.model_validate(output)


def _make_worker_node(
    *,
    node_name: str,
    worker: Callable[[PipelineState], Any],
    output_key: str,
):
    def node(state: PipelineState) -> dict[str, Any]:
        config = state["config"]
        step = state.get("step_count", 0) + 1
        retry_counts = dict(state.get("retry_counts", {}))
        attempt = retry_counts.get(node_name, 0) + 1
        base_events = _append_event(
            state,
            make_audit_event(
                run_id=state["run_id"],
                case_id=state["case_id"],
                node=node_name,
                event_type="worker_started",
                status="running",
                attempt=attempt,
                details={"step": step},
            ),
        )
        if step > config.runtime.max_graph_steps:
            error = WorkerError(code="max_graph_steps_exceeded", retryable=False, message="max_graph_steps_exceeded")
            return {
                "step_count": step,
                "retry_counts": retry_counts,
                "next_action": "failure",
                "run_status": "failed",
                "failure": error,
                "last_error": error,
                "audit_events": [
                    *base_events,
                    make_audit_event(
                        run_id=state["run_id"], case_id=state["case_id"], node=node_name,
                        event_type="worker_failed", status="failed", attempt=attempt,
                        details={"error_code": error.code},
                    ),
                ],
            }

        retry_counts[node_name] = attempt
        try:
            output = _validate_worker_output(
                output_key,
                _execute_with_timeout(lambda: worker(state), config.runtime.timeout_seconds),
            )
        except BaseException as exc:  # worker boundary: convert all failures to typed state
            error = _safe_error(exc)
            retryable = error.retryable and attempt < config.runtime.max_attempts
            event_type = "worker_retry_scheduled" if retryable else "worker_failed"
            return {
                "step_count": step,
                "retry_counts": retry_counts,
                "next_action": "retry" if retryable else "failure",
                "run_status": "running" if retryable else "failed",
                "failure": None if retryable else error,
                "last_error": error,
                "audit_events": [
                    *base_events,
                    make_audit_event(
                        run_id=state["run_id"], case_id=state["case_id"], node=node_name,
                        event_type=event_type, status="retrying" if retryable else "failed", attempt=attempt,
                        details={"error_code": error.code, "max_attempts": config.runtime.max_attempts},
                    ),
                ],
            }

        return {
            "step_count": step,
            "retry_counts": retry_counts,
            output_key: output,
            "next_action": "success",
            "last_error": None,
            "audit_events": [
                *base_events,
                make_audit_event(
                    run_id=state["run_id"], case_id=state["case_id"], node=node_name,
                    event_type="worker_completed", status="completed", attempt=attempt,
                    details={},
                ),
            ],
        }

    return node


def _route(state: PipelineState) -> str:
    return state.get("next_action", "failure")


def build_graph(config: PipelineConfig | None = None, workers: WorkerSet | None = None):
    """Build a compiled graph with explicit worker and retry edges."""

    config = config or PipelineConfig()
    workers = workers or WorkerSet()
    graph = StateGraph(PipelineState)
    graph.add_node(
        "extraction_worker",
        _make_worker_node(
            node_name="extraction_worker",
            output_key="extraction",
            worker=lambda state: workers.extraction(state["application"], state["document"]),
        ),
    )
    graph.add_node(
        "policy_check_worker",
        _make_worker_node(
            node_name="policy_check_worker",
            output_key="policy",
            worker=lambda state: workers.policy(state["extraction"], state["config"]),
        ),
    )
    graph.add_node(
        "decision_narrative_worker",
        _make_worker_node(
            node_name="decision_narrative_worker",
            output_key="narrative",
            worker=lambda state: workers.narrative(state["policy"]),
        ),
    )
    graph.add_node(
        "fairness_check_worker",
        _make_worker_node(
            node_name="fairness_check_worker",
            output_key="fairness",
            worker=lambda state: workers.fairness(state["application"], state["policy"], state["narrative"]),
        ),
    )

    def finalize_success(state: PipelineState) -> dict[str, Any]:
        fairness = state.get("fairness")
        policy = state.get("policy")
        # ``not_evaluable`` means no governed demographic assessment ran. It
        # is a limitation to disclose, not a universal review trigger. Review
        # is driven by actual policy/documentation findings, worker reliability,
        # or a separately supported fairness finding or reasoning concern.
        policy_requires_review = policy is None or policy.recommendation != "proceed"
        fairness_requires_review = (
            fairness is None
            or fairness.requires_human_review
            or fairness.status == "evaluated_with_findings"
        )
        needs_review = policy_requires_review or fairness_requires_review
        status = "needs_human_review" if needs_review else "completed"
        event = make_audit_event(
            run_id=state["run_id"], case_id=state["case_id"], node="controller",
            event_type="pipeline_completed", status=status, attempt=1,
            details={"gate_status": "not_run"},
        )
        return {"run_status": status, "next_action": "done", "audit_events": _append_event(state, event)}

    def finalize_failure(state: PipelineState) -> dict[str, Any]:
        error = state.get("failure") or state.get("last_error") or WorkerError(
            code="pipeline_failed", retryable=False, message="pipeline_failed"
        )
        event = make_audit_event(
            run_id=state["run_id"], case_id=state["case_id"], node="controller",
            event_type="pipeline_failed", status="failed", attempt=1,
            details={"error_code": error.code},
        )
        return {"run_status": "failed", "next_action": "done", "failure": error, "audit_events": _append_event(state, event)}

    graph.add_node("finalize_success", finalize_success)
    graph.add_node("finalize_failure", finalize_failure)
    graph.add_edge(START, "extraction_worker")
    graph.add_conditional_edges(
        "extraction_worker", _route,
        {"success": "policy_check_worker", "retry": "extraction_worker", "failure": "finalize_failure"},
    )
    graph.add_conditional_edges(
        "policy_check_worker", _route,
        {"success": "decision_narrative_worker", "retry": "policy_check_worker", "failure": "finalize_failure"},
    )
    graph.add_conditional_edges(
        "decision_narrative_worker", _route,
        {"success": "fairness_check_worker", "retry": "decision_narrative_worker", "failure": "finalize_failure"},
    )
    graph.add_conditional_edges(
        "fairness_check_worker", _route,
        {"success": "finalize_success", "retry": "fairness_check_worker", "failure": "finalize_failure"},
    )
    graph.add_edge("finalize_success", END)
    graph.add_edge("finalize_failure", END)
    return graph.compile()


def _initial_state(request: PipelineRequest, config: PipelineConfig) -> PipelineState:
    application = sanitize_application(request.case_id, request.application)
    if request.runtime_document is not None:
        document = sanitize_runtime_document(request.runtime_document)
    else:
        document = sanitize_synthetic_document(request.synthetic_document or {})
    return {
        "run_id": request.run_id or str(uuid4()),
        "case_id": request.case_id,
        "application": application,
        "document": document,
        "config": config,
        "audit_events": [],
        "retry_counts": {},
        "step_count": 0,
        "run_status": "running",
        "failure": None,
        "last_error": None,
    }


def _rejected_result(request: Any, code: str) -> PipelineResult:
    case_id = request.case_id if isinstance(request, PipelineRequest) else "unknown"
    run_id = request.run_id if isinstance(request, PipelineRequest) and request.run_id else str(uuid4())
    event = make_audit_event(
        run_id=run_id, case_id=case_id, node="boundary", event_type="input_rejected",
        status="failed", attempt=1, details={"error_code": code},
    )
    return PipelineResult(
        run_id=run_id, case_id=case_id, status="failed", audit_events=[event],
        failure=WorkerError(code=code, retryable=False, message=code), gate_status="not_run",
    )


def run_pipeline(
    request: PipelineRequest | dict[str, Any],
    *,
    config: PipelineConfig | None = None,
    workers: WorkerSet | None = None,
) -> PipelineResult:
    """Validate the boundary, invoke the graph, and return a typed result."""

    try:
        parsed_request = request if isinstance(request, PipelineRequest) else PipelineRequest.model_validate(request)
        cfg = config or PipelineConfig()
        initial = _initial_state(parsed_request, cfg)
    except BoundaryViolation as exc:
        return _rejected_result(request, exc.code)
    except Exception:
        return _rejected_result(request, "request_schema_invalid")

    final_state = build_graph(cfg, workers).invoke(initial)
    policy = final_state.get("policy")
    recommendation = policy.recommendation if policy is not None and final_state.get("run_status") != "failed" else None
    return PipelineResult(
        run_id=final_state["run_id"],
        case_id=final_state["case_id"],
        status=final_state.get("run_status", "failed"),
        recommendation=recommendation,
        extraction=final_state.get("extraction"),
        policy=policy,
        narrative=final_state.get("narrative"),
        fairness=final_state.get("fairness"),
        audit_events=final_state.get("audit_events", []),
        failure=final_state.get("failure"),
        gate_status="not_run",
    )

