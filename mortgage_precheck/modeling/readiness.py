"""Phase 4.1 readiness contract for the deferred HMDA experiment."""

from __future__ import annotations

from typing import Any

READINESS_VERSION = "phase4.1-readiness-v1"
MAJORITY_CLASS_LABEL = 1
BASELINE_COMPARISONS = ("majority_class", "logistic_regression")
REQUIRED_METRICS = (
    "class_prevalence",
    "confusion_matrix",
    "precision",
    "recall",
    "f1",
    "roc_auc",
    "pr_auc",
)


def readiness_specification() -> dict[str, Any]:
    """Return the non-training readiness rules used before Phase 5."""

    return {
        "readiness_version": READINESS_VERSION,
        "status": "blocked_pending_owner_approval",
        "majority_class_baseline": {
            "label": MAJORITY_CLASS_LABEL,
            "interpretation": "descriptive comparator only; not a useful approval model",
        },
        "model_comparisons": list(BASELINE_COMPARISONS),
        "required_metrics": list(REQUIRED_METRICS),
        "acceptance_gate": "not_locked",
        "duplicate_policy": {
            "exact_duplicates": "retain source rows and report counts; do not silently delete",
            "near_duplicates": "requires a reviewed definition and case-linkage evidence before training",
            "cross_split_control": "institution grouping by LEI where feasible; no application identifier is available",
        },
        "fairness_policy": {
            "operational_features": "protected demographic fields excluded",
            "evaluation_only": "requires governed demographic extract and sample-size review",
        },
    }
