from mortgage_precheck.modeling.readiness import (
    BASELINE_COMPARISONS,
    MAJORITY_CLASS_LABEL,
    READINESS_VERSION,
    REQUIRED_METRICS,
    readiness_specification,
)


def test_readiness_contract_requires_owner_approval_before_training():
    spec = readiness_specification()
    assert READINESS_VERSION == "phase4.1-readiness-v1"
    assert spec["status"] == "blocked_pending_owner_approval"
    assert spec["acceptance_gate"] == "not_locked"
    assert spec["majority_class_baseline"]["label"] == MAJORITY_CLASS_LABEL


def test_readiness_compares_majority_baseline_with_logistic_regression():
    assert BASELINE_COMPARISONS == ("majority_class", "logistic_regression")
    assert set(REQUIRED_METRICS) == {
        "class_prevalence",
        "confusion_matrix",
        "precision",
        "recall",
        "f1",
        "roc_auc",
        "pr_auc",
    }


def test_readiness_duplicate_and_fairness_controls_are_explicit():
    spec = readiness_specification()
    assert "retain source rows" in spec["duplicate_policy"]["exact_duplicates"]
    assert "case-linkage" in spec["duplicate_policy"]["near_duplicates"]
    assert spec["fairness_policy"]["operational_features"] == "protected demographic fields excluded"
