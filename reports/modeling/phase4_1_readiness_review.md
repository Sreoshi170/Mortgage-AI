# Phase 4.1 modeling readiness review

**Version:** `phase4.1-readiness-v1`  
**Status:** `BLOCKED_PENDING_OWNER_APPROVAL`  
**Scope:** readiness only. No model was trained, evaluated, or connected to live inference.

## Evidence reviewed

- Phase 3 ingestion and quality reports.
- Phase 4 target, feature, leakage, and split artifacts.
- Current ingestion and modeling modules.
- Current API, LangGraph state, worker contracts, and tests.
- Full prepared source: `data/processed/hmda_precheck_typed_v1.csv`.

The full source contains 13,558,306 rows and 24 columns. The candidate target
contains 8,953,267 eligible rows: 6,837,512 with `action_taken=1` and
2,115,755 with `action_taken=3`. Other action codes remain excluded and
distinct. This target is a historical HMDA outcome, not creditworthiness or an
underwriting decision. The official HMDA documentation defines the action
codes and field semantics in the [LAR data-field documentation](https://ffiec.cfpb.gov/documentation/publications/loan-level-datasets/lar-data-fields).

## Intended prediction time and leakage

The intended research prediction time is before the historical `action_taken`
outcome is known, using application information available at the defined
decision point. The repository does not contain verified preprocessing history
or event timestamps. Therefore availability is unresolved for:

- `property_value`;
- `combined_loan_to_value_ratio`;
- `debt_to_income_ratio`;
- `income`;
- derived and pricing fields that are already excluded.

The candidate feature set remains unapproved until the data owner confirms
which values existed at the intended time. `action_taken`, interest rate, rate
spread, denial reasons, derived outcome-adjacent fields, demographics,
geography, and institution identifiers remain excluded from operational
features. LEI is used only as a split group key.

## Duplicate and related-record policy

The Phase 3 profile found 165,974 repeated full rows after the first occurrence
(1.2241%). The source has no application/case identifier. The source is not
modified and rows are not silently removed.

The approved readiness rule is:

1. Preserve and report exact duplicate counts.
2. Keep all rows for an institution in one split.
3. Do not claim that institution grouping detects related applications across
   institutions.
4. Define and review a near-duplicate diagnostic before training. A potential
   diagnostic could compare normalized core application fields within a
   reviewed scope, but the project does not yet have enough provenance to
   choose that definition without inventing semantics.

This is a training blocker, not a reason to overwrite the source or drop rows.

## Special values and units

The ingestion module preserves blank, `NA`, `Exempt`, DTI buckets, invalid, and
out-of-range states. The full eligible-population audit found:

| Field | Numeric/categorical | Special | Invalid/out-of-range |
|---|---:|---:|---:|
| `property_value` | 8,337,556 | 615,711 | 0 |
| `combined_loan_to_value_ratio` | 7,997,070 | 956,197 | 0 |
| `income` | 8,250,529 | 695,249 | 7,489 negative |
| `debt_to_income_ratio` | 3,775,321 | 5,177,946 | 0 |

HMDA income remains in thousands of dollars. Official DTI buckets are not
converted to arbitrary numeric values. No imputation, clipping, or silent
record removal is approved yet. The future fitted pipeline must learn any
imputation, encoding, or scaling from training data only.

## Split policy and class representation

Because every row is activity year 2025, a time holdout is unavailable. The
current reproducible proposal is a SHA-256 institution-grouped 70/15/15 split
using LEI only as a hidden grouping key and seed `phase4-action13-v1`.

| Split | Positive | Negative | Eligible total | Positive prevalence |
|---|---:|---:|---:|---:|
| Train | 4,514,112 | 1,571,935 | 6,086,047 | 0.741715 |
| Validation | 1,271,627 | 272,993 | 1,544,620 | 0.823262 |
| Test | 1,051,773 | 270,827 | 1,322,600 | 0.795231 |

All three partitions contain both classes. The prevalence differences are
material and must be reported, not corrected by artificial test balancing.
The split is disjoint by the 4,787 institution groups observed among eligible
rows under the deterministic assignment. It does not establish future-year
generalization.

## Baseline and evaluation plan

The first comparison will be:

1. Majority-class descriptive baseline: always predict historical class `1`.
2. Logistic regression with the reviewed preprocessing pipeline.

Required metrics are class prevalence, confusion matrix, precision, recall, F1,
ROC-AUC, and PR-AUC. Accuracy alone is not acceptable. The final test set must
remain untouched until the model and threshold are locked using training and
validation data. Calibration and uncertainty diagnostics should be added if
the environment and sample definitions support them.

No acceptance threshold is locked. No fairness conclusion is possible because
the processed file has no protected demographic fields and the evaluation-only
extract is not governed or available. A separate controlled fairness workflow
is required before any fairness claim.

## Blocking decisions for the project owner

Training must wait for explicit approval of:

1. target meaning and eligible population;
2. decision-time availability of each proposed feature;
3. treatment of negative income, special values, extremes, and missingness;
4. exact and near-duplicate policy;
5. institution-grouped split and its prevalence shift;
6. test threshold and acceptance criteria;
7. separate fairness data access and subgroup minimums.

The conservative default is to keep the current proposal unchanged, train only
as a research experiment after approval, and report all limitations. This
review does not grant that approval.

## Verification commands

```powershell
python -m pytest -q
python -m compileall -q mortgage_precheck backend tests
node --check frontend\app.js
```

All three commands were run during this review. The test suite passed with 44
tests. The existing FastAPI/Starlette `httpx` deprecation warning remains.
