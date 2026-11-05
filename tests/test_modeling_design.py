from copy import deepcopy

from mortgage_precheck.modeling.prepare import prepare_baseline_row
from mortgage_precheck.modeling.spec import (
    BASELINE_METRICS,
    MODEL_SPEC_VERSION,
    PROPOSED_FEATURES,
    feature_leakage_review,
)
from mortgage_precheck.modeling.splitting import assign_group_split
from mortgage_precheck.modeling.target import construct_candidate_target, summarize_candidate_target


def test_candidate_target_includes_only_action_codes_one_and_three():
    assert construct_candidate_target("1").target == 1
    assert construct_candidate_target("3").target == 0
    assert construct_candidate_target("2").included is False
    assert construct_candidate_target("NA").included is False
    assert construct_candidate_target("").included is False


def test_target_summary_counts_exclusions_without_collapsing_codes():
    summary = summarize_candidate_target(
        [
            {"action_taken": "1"},
            {"action_taken": "3"},
            {"action_taken": "4"},
            {"action_taken": "7"},
        ]
    )
    assert summary["eligible_rows"] == 2
    assert summary["positive_rows"] == 1
    assert summary["negative_rows"] == 1
    assert summary["excluded_action_code_counts"] == {"4": 1, "7": 1}


def test_feature_review_excludes_target_protected_and_leakage_fields():
    reviewed = {item.name: item for item in feature_leakage_review()}
    assert "action_taken" not in PROPOSED_FEATURES
    assert all(reviewed[name].proposed for name in PROPOSED_FEATURES)
    assert reviewed["action_taken"].leakage_status == "outcome_leakage"
    assert reviewed["demographic_fields"].protected_or_proxy_status == "protected"


def test_split_is_deterministic_and_group_stable():
    first = assign_group_split("institution-a", seed="test-seed", ratios={"train": 0.7, "validation": 0.15, "test": 0.15})
    second = assign_group_split("institution-a", seed="test-seed", ratios={"train": 0.7, "validation": 0.15, "test": 0.15})
    assert first == second


def test_missing_and_special_values_are_not_imputed_or_source_mutated():
    source = {
        "action_taken": "1",
        "loan_type": "1",
        "loan_purpose": "1",
        "loan_amount": "250000",
        "property_value": "Exempt",
        "combined_loan_to_value_ratio": "NA",
        "occupancy_type": "1",
        "income": "-10",
        "debt_to_income_ratio": "30%-<36%",
    }
    before = deepcopy(source)
    prepared = prepare_baseline_row(source)
    assert source == before
    assert prepared["features"]["property_value"] is None
    assert prepared["features"]["property_value__is_missing_or_special"] == 1
    assert prepared["features"]["combined_loan_to_value_ratio"] is None
    assert prepared["features"]["income"] is None
    assert prepared["features"]["income__is_invalid_or_out_of_range"] == 1
    assert prepared["features"]["debt_to_income_ratio"] is None
    assert prepared["field_status"]["debt_to_income_ratio"] == "special"


def test_baseline_contract_is_versioned_and_metrics_are_not_accuracy_only():
    assert MODEL_SPEC_VERSION == "phase4-action13-logistic-v1"
    assert "confusion_matrix" in BASELINE_METRICS
    assert "precision" in BASELINE_METRICS
    assert "recall" in BASELINE_METRICS
    assert "f1" in BASELINE_METRICS
    assert "roc_auc" in BASELINE_METRICS
    assert "pr_auc" in BASELINE_METRICS
