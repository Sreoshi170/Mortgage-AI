# Phase 3 HMDA ingestion and feature-preparation report

Audit date: 2026-10-22

## Scope

Phase 3 adds an offline, streaming HMDA ingestion and candidate-feature layer.
It does not train a model, change the target, modify source files, or connect
HMDA data to the live FastAPI/LangGraph recommendation path.

## Actual input audited

| Property | Verified value |
|---|---|
| Input | `data/processed/hmda_precheck_typed_v1.csv` |
| Format | Comma-delimited CSV |
| Rows inspected | 13,558,306 |
| Columns | 24 |
| Chunks | 272 at chunk size 50,000 |
| Row-width errors | 0 |
| Source modification | None |
| Machine-readable report | `reports/data/phase3_quality_report.json` |

The raw 2025 files were also inspected for headers. The public LAR CSV and
pipe-delimited LAR each expose 99 columns, including derived ethnicity, race,
and sex fields. The processed file audited here contains 24 columns and no
obvious protected demographic columns.

## Quality results

The audit preserves source strings and reports status instead of silently
coercing values:

| Field | Missing | Special | Invalid | Out of range |
|---|---:|---:|---:|---:|
| `income` | 0 | 2,190,048 | 0 | 8,091 |
| `debt_to_income_ratio` | 0 | 9,510,049 | 0 | 0 |
| `combined_loan_to_value_ratio` | 0 | 5,036,974 | 0 | 0 |
| `interest_rate` | 0 | 4,858,117 | 0 | 0 |
| `rate_spread` | 0 | 7,142,549 | 0 | 0 |

In this table, `special` includes literal `NA`, `Exempt`, and official DTI
bucket values. The machine-readable report contains the per-code counts.
The `income` out-of-range count is the observed negative-income count. No
upper bound was invented for income or loan amount because official HMDA
documentation warns that those fields have no upper limit and may contain
outliers.

## Semantics and safeguards

- `income` remains in the HMDA-reported unit: gross annual income in thousands
  of dollars. No conversion to dollars is applied.
- `action_taken` remains an eight-code candidate outcome and is excluded from
  candidate operational features. It is not treated as borrower
  creditworthiness.
- Reported `combined_loan_to_value_ratio` is preserved. The module does not
  replace it with `loan_amount / property_value`.
- The candidate operational allowlist excludes protected demographics,
  geography/institution identifiers, `action_taken`, pricing fields, denial
  reasons, and derived fields with unresolved timing.
- Derived feature records retain raw allowlisted values, parse status, and a
  source-row hash. They are written only to a separate JSONL output when
  explicitly requested.
- No HMDA fields are passed to ordinary LangGraph workers by this phase.

Official definitions checked:

- [Public HMDA LAR data fields](https://ffiec.cfpb.gov/documentation/publications/loan-level-datasets/lar-data-fields)
- [Public HMDA LAR schema](https://ffiec.cfpb.gov/documentation/publications/loan-level-datasets/public-lar-schema)

## Commands

Run a full audit:

```powershell
python -m mortgage_precheck.data.cli `
  --input data/processed/hmda_precheck_typed_v1.csv `
  --report reports/data/phase3_quality_report.json `
  --chunk-size 50000
```

Run a bounded preview:

```powershell
python -m mortgage_precheck.data.cli `
  --input data/processed/hmda_precheck_typed_v1.csv `
  --report reports/data/phase3_quality_preview.json `
  --max-rows 100000
```

Write separate candidate features without touching the source:

```powershell
python -m mortgage_precheck.data.cli `
  --input data/processed/hmda_precheck_typed_v1.csv `
  --report reports/data/phase3_quality_report.json `
  --features-output data/processed/phase3_candidate_features.jsonl
```

## Limitations and next approval gate

The project still lacks verified preprocessing history, row-level application
identifiers, as-of timing, a locked target contract, deduplication policy,
and a governed evaluation-only demographic extract. The candidate feature
allowlist therefore remains offline and unapproved for training or inference.
Training and live HMDA connection are intentionally deferred.
