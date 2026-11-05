"""Typed state carried through the LangGraph."""

from __future__ import annotations

from typing import Literal, TypedDict

from .config import PipelineConfig
from .schemas import (
    ApplicationInput,
    AuditEvent,
    DecisionNarrativeOutput,
    ExtractionOutput,
    FairnessCheckOutput,
    NormalizedSummary,
    PolicyCheckOutput,
    DocumentInput,
    WorkerError,
)


class PipelineState(TypedDict, total=False):
    run_id: str
    case_id: str
    application: ApplicationInput
    document: DocumentInput
    config: PipelineConfig
    extraction: ExtractionOutput
    policy: PolicyCheckOutput
    narrative: DecisionNarrativeOutput
    fairness: FairnessCheckOutput
    audit_events: list[AuditEvent]
    retry_counts: dict[str, int]
    step_count: int
    next_action: Literal["success", "retry", "failure", "done"]
    run_status: Literal["running", "completed", "needs_human_review", "failed"]
    failure: WorkerError | None
    last_error: WorkerError | None

