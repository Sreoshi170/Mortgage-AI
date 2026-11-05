# Data-quality report

## Finding

Status: `INCOMPLETE — DATASET NOT APPROVED FOR WORKER USE`

The actual processed file is `data/processed/hmda_precheck_typed_v1.csv`. It can be profiled reproducibly, but the repository does not contain the preprocessing code, source metadata, field dictionary, case identifiers, units, event-time definitions, or an experiment contract. The file must not be treated as ready for training, agent execution, or a mortgage pre-check claim.

## Checks performed

| Check | Result | Evidence / interpretation |
|---|---|---|
| File located | Pass | Requested filename differed; actual file found and profiled |
| Schema read | Pass | 24 columns; 13,558,306 rows |
| Row width | Pass | 0 rows with a field-count mismatch |
| Categorical code scan | Pass with limitation | Observed action, loan type, loan purpose, occupancy, conforming-limit, state, and county values fit the scan vocabularies; meanings still need source documentation |
| Missingness | Warning | Large missing-like fractions, including 50.34% rate spread and 35.63% DTI |
| Special-code preservation | Warning | `NA` and `Exempt` survive in source-like fields, but numeric companions collapse them to blank |
| Duplicate rows | Warning | 165,974 repeated full-row observations (1.2241%); no case ID is available to adjudicate them |
| Numeric validity | Fail for downstream readiness | Extreme values and negative income require a documented source-code/outlier policy; no values were silently changed |
| Protected-field separation | Partial pass | Demographics are absent from processed columns; the evaluation-only directory is empty and enforcement has not been implemented |
| Target definition | Incomplete | `action_taken` is a candidate outcome field, but its intended role and label mapping are not confirmed |
| Leakage/timing review | Incomplete | Pricing, outcome, derived, and underwritten fields lack as-of semantics |
| Reproducible provenance | Fail | No preprocessing script, manifest, or version history existed before this report |

## Material data issues

### P0: resolve before any worker or model input

1. Define the pre-check task and the prediction/evaluation time boundary. Explicitly decide whether `action_taken`, `rate_spread`, `interest_rate`, property value, CLTV, DTI, and derived fields are available at that boundary.
2. Create a feature allowlist and a separate evaluation-only schema. The processed file has no demographics, but no automated separation mechanism exists yet.
3. Document the meaning and treatment of `NA`, `Exempt`, DTI buckets, `9999`-style source codes if they are reintroduced, and extreme numeric values. Do not map them to zero.
4. Establish an application/case identifier or a documented stable row-provenance key. `lei` is not an application identifier.

### P1: resolve before evaluation design

1. Investigate the 165,974 repeated rows and choose a deduplication or retention policy based on source provenance.
2. Investigate extreme values: loan amount up to 999,000,005,000, CLTV up to 1,401,111,800, property value up to 2,147,483,647, income down to -1,811,129, and 8,091 negative income values. Preserve raw values while recording an explicit validity status.
3. Recover the verified preprocessing history and source version. The available raw HMDA files have overlapping field names and matching representative records, but exact row selection and transformations are unverified.
4. Define group/time splitting to prevent leakage across repeated institutions, geography, or duplicated records.

### P2: resolve before research claims

1. Define the label mapping for `action_taken`, including handling of withdrawn, incomplete, and other outcomes.
2. Define the difference between historical lending outcomes and ground-truth creditworthiness. Do not use the historical outcome as unquestionable merit.
3. Populate a governed evaluation-only demographic extract with access controls and aggregate fairness metrics only. Do not place those fields in worker state, prompts, retrieval, or general logs.

## Target/outcome assessment

`action_taken` is the only obvious outcome-like column in the processed schema. It has eight observed codes and no missing values. This report deliberately does not assign code meanings or designate it as the final target because the repository lacks the field dictionary and the project has not locked the pre-check task. Treat it as a candidate label requiring human confirmation and an explicit experiment contract.

## Protected attributes and worker safety

The processed column list contains no race, ethnicity, sex, gender, age, or similarly named demographic fields. Raw source files do contain HMDA demographic fields. The current separation is therefore a property of this file, not an enforced pipeline invariant. Until schemas and tests exist, do not expose raw files, geography, LEI, or evaluation-only attributes to AI workers by default.

## Leakage assessment

The main concern is temporal and label leakage, not just column naming. `action_taken` is an outcome candidate. `rate_spread` and `interest_rate` may be determined after pricing or underwriting. `property_value`, CLTV, DTI, and derived product fields may be values available only after additional processing. The dataset does not provide timestamps or a data dictionary sufficient to prove availability before the intended pre-check.

The duplicate rate and repeated LEIs also create split leakage risk. A random row split should not be used until the project defines grouping and time boundaries.

## Recommended next implementation steps

1. Confirm the task contract with the project owner: allowed recommendation labels, as-of point, candidate label, treatment of all action codes, and whether this dataset is for plumbing only or the main evaluation.
2. Add a verified source/preprocessing note and a row-level provenance strategy. Keep raw files immutable.
3. Build a typed ingestion adapter that preserves raw strings, parses only approved fields, records parse/validity status, and maintains `NA` versus `Exempt` versus true zero.
4. Create separate model-visible and evaluation-only schemas plus automated tests that fail if protected fields cross the boundary.
5. Define and lock a deduplication, outlier, group/time split, and missingness policy before any model or LangGraph work.
6. Only after approval, implement the smallest ingestion/validation slice. Do not build workers, examiner calls, fairness claims, or a release gate from this dataset yet.

## Verification record

- Read `PRD.md`, `RULES.md`, and `DESIGN.md` before making report changes.
- Inspected repository tree, raw/processed files, headers, and file metadata.
- Streamed the full processed CSV without editing it.
- Confirmed the processed SHA-256 as `F088D3E171C6D3402BF67658B34EF48909E1876066453AC1A9B6AF1DF32932E6`.
- No model training, agent construction, or dataset overwrite was performed.
