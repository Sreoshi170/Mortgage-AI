"""Research-only HMDA target and baseline-model design helpers.

This package intentionally does not train a model and is not imported by the
live FastAPI or LangGraph recommendation path. It creates reviewable target,
feature, split, and missing-value contracts for a future experiment.
"""

from .prepare import prepare_baseline_row
from .readiness import readiness_specification
from .spec import (
    BASELINE_METRICS,
    MODEL_SPEC_VERSION,
    PROPOSED_FEATURES,
    feature_leakage_review,
    modeling_specification,
)
from .splitting import assign_group_split
from .target import TargetRecord, construct_candidate_target, summarize_candidate_target

__all__ = [
    "BASELINE_METRICS",
    "MODEL_SPEC_VERSION",
    "PROPOSED_FEATURES",
    "TargetRecord",
    "assign_group_split",
    "construct_candidate_target",
    "feature_leakage_review",
    "modeling_specification",
    "prepare_baseline_row",
    "readiness_specification",
    "summarize_candidate_target",
]
