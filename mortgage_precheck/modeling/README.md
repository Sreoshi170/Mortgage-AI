# Phase 4 modeling design helpers

This package prepares a reproducible, research-only HMDA experiment design.
It does not train a model and is not connected to FastAPI, LangGraph, policy
rules, or frontend behavior.

The candidate label is `action_taken=1` versus `action_taken=3` only. It is a
historical reporting outcome, not borrower creditworthiness and not a live
underwriting decision. Protected demographic fields remain outside the
operational feature contract and are reserved for separately governed
fairness evaluation.

Run the design audit with:

```powershell
python -m mortgage_precheck.modeling.cli `
  --input data/processed/hmda_precheck_typed_v1.csv `
  --output reports/modeling/phase4_target_feature_summary.json `
  --chunk-size 50000
```

The command streams the source, writes only a summary artifact, and never
changes the source file or starts training.
