# Phase 4 design audit report

**Specification:** `phase4-action13-logistic-v1`  
**Run status:** design audit complete; model training not run  
**Input:** `data/processed/hmda_precheck_typed_v1.csv`

## Verified source and target counts

The full source audit streamed 13,558,306 rows and all 24 columns. The source
was not modified. The candidate population contains only `action_taken=1` and
`action_taken=3`:

| Measure | Count |
|---|---:|
| `action_taken=1` historical originated | 6,837,512 |
| `action_taken=3` historical denied | 2,115,755 |
| Candidate eligible rows | 8,953,267 |
| Candidate positive prevalence | 0.763689 |
| Other action codes excluded | 4,605,039 |

Excluded codes remain distinct in the machine-readable summary. They are not
collapsed into denial. The official HMDA field definitions describe the
additional action codes and the meanings of the candidate codes in the
[official LAR data-field documentation](https://ffiec.cfpb.gov/documentation/publications/loan-level-datasets/lar-data-fields).

## Proposed feature status in the eligible population

The proposed feature list is:
`loan_type`, `loan_purpose`, `loan_amount`, `property_value`,
`combined_loan_to_value_ratio`, `occupancy_type`, `income`, and
`debt_to_income_ratio`.

The full audit found these status counts among the 8,953,267 eligible rows:

| Field | Numeric/categorical | Special | Invalid/out-of-range |
|---|---:|---:|---:|
| `loan_type` | 8,953,267 categorical | 0 | 0 |
| `loan_purpose` | 8,953,267 categorical | 0 | 0 |
| `loan_amount` | 8,953,267 numeric | 0 | 0 |
| `property_value` | 8,337,556 numeric | 615,711 | 0 |
| `combined_loan_to_value_ratio` | 7,997,070 numeric | 956,197 | 0 |
| `occupancy_type` | 8,953,267 categorical | 0 | 0 |
| `income` | 8,250,529 numeric | 695,249 | 7,489 out-of-range |
| `debt_to_income_ratio` | 3,775,321 numeric | 5,177,946 | 0 |

Special values and official DTI buckets are not converted to zero or arbitrary
numeric values. The design helper retains missing/special/invalid status and
adds indicators; a future fitted imputer must be learned from the training
partition only.

## Split design

The full audit assigned eligible rows using a deterministic institution-grouped
70/15/15 holdout with seed `phase4-action13-v1` and group key `lei`:

| Split | Eligible rows | Distinct institution groups |
|---|---:|---:|
| Train | 6,086,047 | 3,322 |
| Validation | 1,544,620 | 689 |
| Test | 1,322,600 | 776 |

All activity year values are 2025, so a meaningful time holdout is not
available. LEI is used only in memory for grouping and is not a feature,
worker input, prompt value, or report field. The absence of an application
identifier means related records across institutions cannot be fully detected.

## Next decision required

Before training, approve the target population and split, confirm decision-time
availability of property value/CLTV/DTI/income, decide treatment of negative and
special values plus duplicates, approve the proxy review, and lock the
evaluation threshold and fairness metrics. No Phase 4 code changes the live
FastAPI/LangGraph path or connects HMDA to recommendations.

## Commands

Run the full design audit:

```powershell
python -m mortgage_precheck.modeling.cli `
  --input data/processed/hmda_precheck_typed_v1.csv `
  --output reports/modeling/phase4_target_feature_summary.json `
  --chunk-size 50000
```

Run the Phase 4 tests:

```powershell
python -m pytest -q tests/test_modeling_design.py
python -m pytest -q
```
