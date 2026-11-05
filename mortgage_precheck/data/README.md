# HMDA ingestion and feature preparation

This package is an offline Phase 3 layer. It is not imported by the live
FastAPI/LangGraph recommendation path and does not train a model.

The input path is configurable. The reader supports comma-delimited CSV and
pipe-delimited HMDA text files, validates required columns, reads bounded row
chunks, and raises on malformed row widths instead of silently dropping data.
Source values remain strings. Numeric parsing reports `missing`, `special`,
`invalid`, `out_of_range`, or `numeric` status. `NA`, `Exempt`, and official
DTI buckets are preserved as special values.

The candidate operational allowlist excludes protected demographics, geography
and institution identifiers, `action_taken`, pricing fields, denial reasons,
and derived fields with unresolved timing. It is not a production feature
contract and is not connected to inference.

The semantics used here were checked against the official CFPB/FFIEC 2025
public HMDA field definitions:

- `income` is gross annual income in thousands of dollars; no conversion is applied.
- `loan_amount` is the amount of the covered loan or amount applied for.
- `action_taken` has eight distinct codes and is retained as a candidate outcome,
  never collapsed into a borrower-creditworthiness label.
- `combined_loan_to_value_ratio` is the reported ratio relied on in the credit
  decision; this module does not substitute `loan_amount / property_value`.
- `rate_spread` describes APR minus APOR as of the rate-set date and is excluded
  from the candidate operational allowlist until timing is approved.

References:

- <https://ffiec.cfpb.gov/documentation/publications/loan-level-datasets/lar-data-fields>
- <https://ffiec.cfpb.gov/documentation/publications/loan-level-datasets/public-lar-schema>

Run a bounded audit:

```powershell
python -m mortgage_precheck.data.cli `
  --input data/processed/hmda_precheck_typed_v1.csv `
  --report reports/data/phase3_quality_report.json `
  --max-rows 100000
```

Run a full scan by omitting `--max-rows`. Derived JSONL features are opt-in:

```powershell
python -m mortgage_precheck.data.cli `
  --input data/processed/hmda_precheck_typed_v1.csv `
  --report reports/data/phase3_quality_report.json `
  --features-output data/processed/phase3_candidate_features.jsonl
```
