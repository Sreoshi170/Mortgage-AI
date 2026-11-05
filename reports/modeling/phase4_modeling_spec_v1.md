# Phase 4 modeling specification

**Version:** `phase4-action13-logistic-v1`  
**Status:** Proposed design only. Phase 4.1 readiness is documented, but owner approval is still required. Training and live integration are explicitly deferred.  
**Source:** `data/processed/hmda_precheck_typed_v1.csv`

## Research question

Can a simple logistic-regression baseline distinguish the historical HMDA
outcome `action_taken=1` from `action_taken=3` in the inspected 2025 file,
using only a reviewed candidate application feature set? This is a research
question about reported historical outcomes. It is not a claim about borrower
creditworthiness, approval likelihood, causal effects, or a valid underwriting
decision.

The official HMDA definitions identify `action_taken=1` as loan originated and
`action_taken=3` as application denied. The full official action vocabulary
also includes approved-not-accepted, withdrawn, incomplete, purchased, and
preapproval outcomes, so those codes are not collapsed into denial for this
design. See the [official HMDA field definitions](https://ffiec.cfpb.gov/documentation/publications/loan-level-datasets/lar-data-fields).

## Population and target

- Include rows with `activity_year=2025` and `action_taken` equal to `1` or
  `3`.
- Encode code `1` as research label `1` and code `3` as research label `0`.
- Exclude all other action codes, missing/special/unrecognized target values,
  and structurally malformed rows. The excluded rows remain in the source and
  are counted in the audit.
- Do not silently deduplicate. The Phase 3 profile found 165,974 repeated full
  rows and no application-level identifier. Duplicate handling needs provenance
  review before any training run.

The label is named `historical_action_1_vs_3`, not `creditworthiness` or
`approval_probability`. Historical action reflects reporting, institution,
product, market, and policy processes. It is not a borrower-level causal or
underwriting construct.

The full pre-training audit observed 6,837,512 rows with code `1`, 2,115,755
rows with code `3`, and 4,605,039 rows with other action codes. The eligible
population is therefore 8,953,267 rows and the observed positive prevalence is
0.763689. These are descriptive source counts, not performance results.

## Proposed feature contract

The proposed features are:

1. `loan_type`
2. `loan_purpose`
3. `loan_amount`
4. `property_value`
5. `combined_loan_to_value_ratio`
6. `occupancy_type`
7. `income`
8. `debt_to_income_ratio`

The Phase 3 operational allowlist is the source of this candidate set. The
constant `activity_year` field is excluded from the model matrix. `action_taken`
is target-only. `lei`, geography fields, demographic fields, pricing fields,
denial reasons, and derived fields with unresolved timing are excluded from
operational features and worker inputs. LEI is used only in memory as a group
key for the split and is never written into the modeling summary.

HMDA `income` is reported in thousands of dollars in the official definition;
the design applies no unit conversion. `debt_to_income_ratio` includes numeric
values and official buckets, which must remain distinguishable. The reported
CLTV is retained as reported and is not replaced with a ratio recomputed from
loan amount and property value. See the [official HMDA data-field definitions](https://ffiec.cfpb.gov/documentation/publications/loan-level-datasets/lar-data-fields).

## Feature and leakage review

The review is recorded separately in
`reports/modeling/phase4_feature_leakage_review.md`. The key unresolved issue is
as-of timing: property value, reported CLTV, DTI, income, and some derived or
pricing fields may be determined or revised during processing. A field is not
safe merely because its name does not mention a protected characteristic.

The candidate fields also require proxy review. Product, purpose, occupancy,
income, DTI, property value, institution, and geography may correlate with
protected characteristics or market segmentation. Protected demographic data
is reserved for a separately governed evaluation process and is not available
to operational workers, prompts, ordinary worker inputs, or general logs.

## Missing and special-value policy

Phase 4 does not fit a preprocessing pipeline. Its preparation helper retains
`None` for missing, special, invalid, or out-of-range numeric values and adds
status indicators. It never replaces a special value with zero. Before a
future training run, any numeric imputation and scaling must be fit on the
training partition only. Categorical encoding must likewise be fit only on
training data and must specify unknown-category behavior. Negative income,
extreme values, and special codes require an approved policy before training.

## Splitting and evaluation

All inspected records have activity year 2025, so a time-aware holdout is not
available. The proposed split is a deterministic 70/15/15 institution-grouped
holdout using SHA-256 of `seed + separator + LEI` with seed
`phase4-action13-v1`. Every row for an institution stays in one partition and
the raw group identifier is not a feature. This reduces institution leakage
relative to a row-random split, but it cannot identify related applications
across institutions because no case identifier is available.

The baseline is logistic regression with `lbfgs`, `max_iter=1000`, no class
weight override, and `random_state=2025`. The evaluation threshold remains
unlocked until review. The required metric set is class prevalence, confusion
matrix, precision, recall, F1, ROC-AUC, and PR-AUC. Accuracy alone is not an
acceptable gate.

## Required approval before training

1. Confirm preprocessing provenance, HMDA units, and decision-time availability.
2. Approve the target population and institution-grouped split.
3. Decide treatment of negative income, special codes, invalid values, extreme
   values, and duplicate/related records.
4. Approve the exact feature matrix and proxy review.
5. Lock the evaluation threshold, regression suite, and separately governed
   fairness metrics before fitting or evaluating any model.

No model is trained by this phase, and no API, LangGraph node, policy rule, or
frontend behavior is changed.

Phase 4.1 readiness evidence and the approval gate are recorded in
`reports/modeling/phase4_1_readiness_review.md`.
