# Phase 4 feature and leakage review

This is a pre-training review for `phase4-action13-logistic-v1`. It does not
approve the feature set for training or live inference.

| Field/group | Proposed | Availability and leakage review | Protected/proxy review | Decision |
|---|---:|---|---|---|
| `loan_type` | yes | Application product code; confirm available at the research decision time. | Not a protected field, but product/market proxy review required. | Pending contract |
| `loan_purpose` | yes | Application purpose; confirm timing. | May proxy for market or household segmentation. | Pending contract |
| `loan_amount` | yes | Application amount; preserve HMDA unit and no invented upper bound. | Proxy review required. | Pending contract |
| `property_value` | yes | May be determined or revised during underwriting. | Proxy review required. | Blocked pending timing |
| `combined_loan_to_value_ratio` | yes | Decision-reliant reported value; do not recompute from other columns. | Proxy review required. | Blocked pending timing |
| `occupancy_type` | yes | Confirm application-time availability. | May correlate with household or market characteristics. | Pending contract |
| `income` | yes | HMDA-reported gross annual income in thousands; preserve special and negative flags. | Proxy review required. | Pending contract |
| `debt_to_income_ratio` | yes | Numeric values and official buckets have unresolved timing and distinct semantics. | Proxy review required. | Pending contract |
| `activity_year` | no | Constant 2025 in the inspected file. | Not protected. | Exclude for no variance |
| `action_taken` | no | Historical outcome and target only. | Not protected. | Exclude for leakage |
| `interest_rate`, `rate_spread` | no | Pricing/rate-setting timing is unresolved and may be post-decision. | Possible proxy. | Exclude |
| `derived_loan_product_type`, `derived_dwelling_category` | no | Derived construction and availability timing are undocumented. | Possible proxy. | Exclude |
| `lei`, `state_code`, `county_code`, `census_tract`, `derived_msa_md` | no | Institution/geography identifiers and related-record risks. LEI is split-only. | Proxy-sensitive. | Exclude from features and workers |
| HMDA demographic fields | no | Evaluation-only data, absent from processed file. | Protected. | Isolate for governed fairness evaluation |

## Leakage controls

- Build the target before any feature matrix and never expose `action_taken` to
  model features or operational workers.
- Fit future imputers, scalers, and encoders on training data only.
- Keep all rows for a `lei` in one deterministic split.
- Do not use post-outcome fields, denial reasons, pricing fields, or unresolved
  derived fields.
- Do not infer that a non-demographic field is safe; review possible proxies.
- Do not expose protected demographics in prompts, ordinary worker inputs,
  general logs, or operational feature artifacts.

## Open risks

The dataset has no row-level application identifier, so group splitting cannot
fully prevent related-record leakage across institutions. The source
preprocessing history is not available in the repository. The timing of
property value, CLTV, DTI, income, and pricing fields is not locked. These are
approval blockers before training.
