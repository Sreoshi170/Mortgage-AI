"""Versioned, reviewable design contract for the Phase 4 HMDA experiment.

The constants in this module describe a proposed research experiment only.
They are not a production underwriting policy, approval score, or live
inference contract.
"""

from __future__ import annotations

from dataclasses import asdict, dataclass
from typing import Any

from mortgage_precheck.data.ingest import (
    LEAKAGE_OR_POST_OUTCOME_FIELDS,
    OPERATIONAL_FEATURE_ALLOWLIST,
    PROTECTED_OR_PROXY_FIELDS,
)

MODEL_SPEC_VERSION = "phase4-action13-logistic-v1"
TARGET_COLUMN = "action_taken"
POSITIVE_ACTION_CODE = "1"
NEGATIVE_ACTION_CODE = "3"
EXCLUDED_ACTION_CODES = ("2", "4", "5", "6", "7", "8")
SPLIT_SEED = "phase4-action13-v1"
SPLIT_RATIOS = {"train": 0.70, "validation": 0.15, "test": 0.15}
GROUP_COLUMN = "lei"

# activity_year is constant at 2025 in the inspected file and therefore has
# no usable variation. It remains a source column but is not proposed as a
# logistic-regression feature.
PROPOSED_FEATURES = (
    "loan_type",
    "loan_purpose",
    "loan_amount",
    "property_value",
    "combined_loan_to_value_ratio",
    "occupancy_type",
    "income",
    "debt_to_income_ratio",
)

BASELINE_METRICS = (
    "class_prevalence",
    "confusion_matrix",
    "precision",
    "recall",
    "f1",
    "roc_auc",
    "pr_auc",
)


@dataclass(frozen=True)
class FeatureReview:
    name: str
    proposed: bool
    availability_status: str
    leakage_status: str
    protected_or_proxy_status: str
    rationale: str

    def to_dict(self) -> dict[str, Any]:
        return asdict(self)


def feature_leakage_review() -> tuple[FeatureReview, ...]:
    """Return the explicit feature, timing, leakage, and proxy review."""

    return (
        FeatureReview(
            "loan_type",
            True,
            "requires_task_contract_confirmation",
            "not_identified_as_outcome_leakage",
            "not_demographic_but_requires_proxy_review",
            "Application product code; retain only if available before the research decision time.",
        ),
        FeatureReview(
            "loan_purpose",
            True,
            "requires_task_contract_confirmation",
            "not_identified_as_outcome_leakage",
            "not_demographic_but_requires_proxy_review",
            "Application purpose code; timing and market-segmentation proxy risk require review.",
        ),
        FeatureReview(
            "loan_amount",
            True,
            "requires_task_contract_confirmation",
            "not_identified_as_outcome_leakage",
            "not_demographic_but_requires_proxy_review",
            "Reported covered-loan/application amount; preserve HMDA units and do not impose an invented upper bound.",
        ),
        FeatureReview(
            "property_value",
            True,
            "blocked_until_as_of_timing_is_confirmed",
            "timing_risk",
            "possible_proxy_requires_review",
            "The value relied on in the credit process may be determined or revised during underwriting.",
        ),
        FeatureReview(
            "combined_loan_to_value_ratio",
            True,
            "blocked_until_as_of_timing_is_confirmed",
            "timing_risk",
            "possible_proxy_requires_review",
            "Reported ratio must not be recomputed from loan amount and property value; decision-time availability is unresolved.",
        ),
        FeatureReview(
            "occupancy_type",
            True,
            "requires_task_contract_confirmation",
            "not_identified_as_outcome_leakage",
            "possible_proxy_requires_review",
            "Property-use code may correlate with market or household characteristics even though it is not a protected field.",
        ),
        FeatureReview(
            "income",
            True,
            "requires_task_contract_confirmation",
            "timing_and_quality_risk",
            "possible_proxy_requires_review",
            "HMDA income is gross annual income in thousands of dollars relied on in the application/processing context; preserve special and negative-value flags.",
        ),
        FeatureReview(
            "debt_to_income_ratio",
            True,
            "requires_task_contract_confirmation",
            "timing_and_quality_risk",
            "possible_proxy_requires_review",
            "Retain numeric values and official buckets as distinct representations; do not coerce buckets to arbitrary numbers.",
        ),
        FeatureReview(
            "activity_year",
            False,
            "available_but_constant_in_inspected_file",
            "not_leakage_but_no_variance",
            "not_a_protected_field",
            "All inspected rows are activity year 2025, so the field is excluded from the baseline matrix.",
        ),
        FeatureReview(
            "action_taken",
            False,
            "target_only",
            "outcome_leakage",
            "not_a_protected_field",
            "Candidate historical outcome; never a feature for this experiment or for pre-decision workers.",
        ),
        FeatureReview(
            "interest_rate",
            False,
            "timing_unresolved",
            "pricing_or_post_decision_risk",
            "possible_proxy_requires_review",
            "Excluded because rate setting timing is not locked and it may reflect later pricing or decision information.",
        ),
        FeatureReview(
            "rate_spread",
            False,
            "timing_unresolved",
            "pricing_or_post_decision_risk",
            "possible_proxy_requires_review",
            "Excluded because it is a rate-setting field and may only be known after the relevant decision process.",
        ),
        FeatureReview(
            "derived_loan_product_type",
            False,
            "timing_unresolved",
            "derived_field_risk",
            "possible_proxy_requires_review",
            "Derived representation with undocumented construction and availability time.",
        ),
        FeatureReview(
            "derived_dwelling_category",
            False,
            "timing_unresolved",
            "derived_field_risk",
            "possible_proxy_requires_review",
            "Derived representation with undocumented construction and availability time.",
        ),
        FeatureReview(
            "lei/state_code/county_code/census_tract/derived_msa_md",
            False,
            "available_but_not_operational",
            "related_record_or_geography_risk",
            "proxy_sensitive",
            "Institution and geography identifiers are excluded from features and worker inputs. LEI is used only as a hidden group key for split assignment.",
        ),
        FeatureReview(
            "demographic_fields",
            False,
            "evaluation_only",
            "not_operational_features",
            "protected",
            "Raw HMDA demographic fields remain outside operational features and ordinary worker prompts/logs; future fairness analysis must be access controlled.",
        ),
    )


def modeling_specification() -> dict[str, Any]:
    """Return the full Phase 4 design as a serializable mapping."""

    return {
        "spec_version": MODEL_SPEC_VERSION,
        "status": "proposed_not_approved_for_training",
        "research_question": "Can a simple logistic-regression baseline distinguish historical HMDA action_taken=1 from action_taken=3 within a defined 2025 research population, without treating the result as creditworthiness or an underwriting decision?",
        "eligible_population": {
            "source": "data/processed/hmda_precheck_typed_v1.csv",
            "activity_year": [2025],
            "target_codes": [POSITIVE_ACTION_CODE, NEGATIVE_ACTION_CODE],
            "target_definition": "action_taken=1 is historical loan originated; action_taken=3 is historical application denied. Code 1 is encoded as 1 and code 3 as 0 only for this experiment.",
        },
        "target_limitations": [
            "action_taken is an HMDA-reported historical outcome, not a borrower's true creditworthiness.",
            "The 1-versus-3 comparison excludes approvals not accepted, withdrawals, incomplete files, purchases, and preapproval outcomes.",
            "Observed historical outcomes reflect institutions, products, market conditions, policies, and reporting processes; they are not a causal estimate or approval likelihood.",
            "The candidate target must not be connected to live recommendations or used to automatically approve or deny applicants.",
        ],
        "excluded_records": {
            "action_codes": list(EXCLUDED_ACTION_CODES),
            "reasons": [
                "missing, blank, special, invalid, or unrecognized action_taken",
                "all action_taken values other than 1 and 3",
                "structurally malformed rows that fail schema validation",
            ],
            "deduplication": "No rows are silently removed in Phase 4. No application identifier is available. Exact duplicates remain observable and must be addressed by provenance review before training.",
        },
        "features": {
            "proposed": list(PROPOSED_FEATURES),
            "operational_source_allowlist": list(OPERATIONAL_FEATURE_ALLOWLIST),
            "excluded_protected_or_proxy_fields": sorted(PROTECTED_OR_PROXY_FIELDS),
            "excluded_leakage_or_post_outcome_fields": sorted(LEAKAGE_OR_POST_OUTCOME_FIELDS),
            "future_preprocessing": {
                "numeric": "Fit any imputation/scaling on the training partition only. Preserve special, invalid, out-of-range, and missing indicators. Do not replace special values with zero.",
                "categorical": "One-hot encode only the reviewed feature set using training-partition categories; handle unseen values explicitly.",
                "debt_to_income_ratio": "Keep official buckets distinct from numeric values until a documented representation is approved.",
                "income": "Retain HMDA-reported thousands-of-dollars unit; no unit conversion is applied.",
            },
        },
        "split": {
            "strategy": "deterministic_institution_group_holdout",
            "group_column": GROUP_COLUMN,
            "ratios": SPLIT_RATIOS,
            "seed": SPLIT_SEED,
            "algorithm": "SHA-256(seed + separator + LEI), mapped to train/validation/test thresholds; the raw LEI is not a feature or output field.",
            "rationale": "The inspected dataset is 2025-only, so a time split cannot separate periods. Grouping by institution is a safer first boundary than a row-random split, but it does not solve cross-institution duplicate or application-linkage risk.",
        },
        "baseline": {
            "model": "logistic_regression",
            "status": "design_only_not_trained",
            "configuration": {
                "class_weight": None,
                "max_iter": 1000,
                "random_state": 2025,
                "solver": "lbfgs",
            },
            "metrics": list(BASELINE_METRICS),
            "positive_class": "historical_action_taken_1",
            "threshold": "Must be locked before evaluation; no threshold is selected in Phase 4.",
        },
        "fairness_evaluation": {
            "operational_access": "protected attributes are excluded from model features, prompts, ordinary worker inputs, and general logs",
            "evaluation_only": "A separately governed demographic extract may be joined only in an access-controlled evaluation process after target and split approval.",
            "status": "not_run; no protected demographic fields are present in the processed 24-column file",
        },
        "limitations_and_open_decisions": [
            "Verify preprocessing provenance and as-of availability with the data owner.",
            "Decide whether property_value, CLTV, DTI, and income meet the intended decision-time contract.",
            "Resolve exact duplicates and related-record linkage before training.",
            "Approve institution-grouped holdout and any minimum group-size rules.",
            "Define treatment of negative income, special codes, invalid values, and extreme values before fitting.",
            "Define and lock the evaluation threshold and fairness metrics before any baseline run.",
        ],
    }
