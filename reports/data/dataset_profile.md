# Dataset profile

## Scope

This profile covers `data/processed/hmda_precheck_typed_v1.csv`, the actual file found in the repository in place of the requested `your_preprocessed_dataset.csv`. The supplied CSV was read in streaming mode and was not modified.

Profile date: 2026-10-21

| Property | Verified value |
|---|---|
| File size | 2,314,177,410 bytes |
| SHA-256 | `F088D3E171C6D3402BF67658B34EF48909E1876066453AC1A9B6AF1DF32932E6` |
| Data rows | 13,558,306 |
| Columns | 24 |
| Row-width errors | 0 |
| Full-row duplicate rows after first occurrence | 165,974 (1.2241%) |
| Activity year | 2025 for every row |

Duplicate detection used a BLAKE2b-64 fingerprint of the parsed field sequence. No repeated fingerprint was found that required collision investigation. Because the dataset has no application-level case identifier, the repeated rows may be source duplicates or legitimate repeated observations; they should not be deleted without provenance review.

## Repository status

The repository currently contains data directories and files only. No Git metadata, application source, dependency manifest, tests, environment examples, migrations, or LangGraph implementation were found. The raw directory contains 2025 HMDA LAR extracts and Lending Club files. The processed schema is a 24-column subset/derived representation, but the exact preprocessing script and version history are not present.

## Schema and missingness

Missing counts include both blank strings and the literal `NA` where observed. `Exempt` and DTI bucket values are reported separately because they are meaningful codes rather than ordinary blanks.

| Column | Observed type / role | Missing-like rows | Distinct / observed values | Notes |
|---|---|---:|---:|---|
| `activity_year` | integer | 0 | 1 | Constant 2025 |
| `lei` | string identifier | 0 | 4,794 | Institution identifier; not a case ID |
| `state_code` | categorical code | 170,445 (1.26%) | 55 | Includes literal `NA`; includes territories |
| `county_code` | string code | 301,875 (2.23%) | 3,224 | Five-digit codes plus `NA`; preserve leading zeroes |
| `conforming_loan_limit` | categorical code | 56,903 (0.42%) | 4 | `C`, `NC`, `U`, `NA` |
| `derived_loan_product_type` | categorical | 0 | 8 | Product/lien category |
| `derived_dwelling_category` | categorical | 0 | 4 | Dwelling category |
| `action_taken` | categorical outcome code | 0 | 8 | Candidate target; meaning not confirmed by project metadata |
| `loan_type` | categorical code | 0 | 4 | Observed values `1`–`4` |
| `loan_purpose` | categorical code | 0 | 6 | Observed values `1`, `2`, `31`, `32`, `4`, `5` |
| `loan_amount` | numeric-like | 0 | not profiled exactly | Range 5,000 to 999,000,005,000 |
| `combined_loan_to_value_ratio` | numeric-like plus codes | 4,719,698 (34.81%) | not profiled exactly | 317,276 `Exempt`; numeric range includes extreme values |
| `interest_rate` | numeric-like plus codes | 4,540,732 (33.49%) | not profiled exactly | 317,385 `Exempt`; range 0 to 100 |
| `rate_spread` | numeric-like plus codes | 6,824,807 (50.34%) | not profiled exactly | 317,742 `Exempt`; range -7,565.8 to 800 |
| `property_value` | numeric-like plus codes | 2,793,876 (20.61%) | not profiled exactly | 318,257 `Exempt`; range 5,000 to 2,147,483,647 |
| `occupancy_type` | categorical code | 0 | 3 | Observed values `1`–`3` |
| `income` | numeric-like | 2,190,048 (16.15%) | not profiled exactly | 8,091 negative values; range -1,811,129 to 120,000,000 |
| `debt_to_income_ratio` | ordinal/categorical plus codes | 4,830,623 (35.63%) | 21 | Numeric strings, buckets, `>60%`, `Exempt`, and `NA` |
| `loan_amount_numeric` | numeric companion | 0 | not profiled exactly | Parseable values matched `loan_amount` |
| `combined_loan_to_value_ratio_numeric` | numeric companion | 5,036,974 (37.15%) | not profiled exactly | `NA`/`Exempt` source values become blank |
| `interest_rate_numeric` | numeric companion | 4,858,117 (35.83%) | not profiled exactly | `NA`/`Exempt` source values become blank |
| `rate_spread_numeric` | numeric companion | 7,142,549 (52.68%) | not profiled exactly | `NA`/`Exempt` source values become blank |
| `property_value_numeric` | numeric companion | 3,112,133 (22.95%) | not profiled exactly | `NA`/`Exempt` source values become blank |
| `income_numeric` | numeric companion | 2,190,048 (16.15%) | not profiled exactly | Numeric values matched `income` |

## Observed categories and outcome distribution

The observed categorical vocabularies contained no values outside the expected code sets used for this scan. This is a structural check, not confirmation that every code has the intended business meaning.

`action_taken` is distributed as follows:

| Observed code | Rows | Share |
|---:|---:|---:|
| 1 | 6,837,512 | 50.43% |
| 3 | 2,115,755 | 15.60% |
| 4 | 1,713,082 | 12.63% |
| 6 | 1,578,065 | 11.64% |
| 5 | 695,182 | 5.13% |
| 2 | 420,181 | 3.10% |
| 8 | 148,030 | 1.09% |
| 7 | 50,499 | 0.37% |

The code distribution is imbalanced. No threshold, positive class, or task label was inferred from it.

## Protected attributes and isolation

No obvious protected demographic columns were found in the processed schema. The inspected raw HMDA files contain demographic fields such as derived ethnicity, race, and sex, plus applicant/co-applicant demographic fields in the combined extract. Those raw fields are not in this processed CSV, which is consistent with the project requirement that protected attributes remain outside worker-visible data.

The repository's `data/evaluation_only/` directory is currently empty. Fairness evaluation therefore cannot be run from the processed file. `state_code`, `county_code`, and `lei` are not demographic attributes in the schema, but geography and institution identifiers may act as proxies and require an explicit feature review before entering worker inputs, prompts, retrieval, or logs.

## Special codes, units, and identifiers

- Literal `NA` is preserved in several source-like fields, while numeric companions use blank strings for missing values.
- `Exempt` is preserved in the source-like ratio/rate/value fields and DTI, but is blank in the corresponding numeric companions. This loses the reason-specific distinction when downstream code uses only the numeric columns.
- DTI includes meaningful buckets such as `<20%`, `20%-<30%`, `30%-<36%`, `36%-<43%`, `43%-<50%`, `50%-60%`, and `>60%`, plus numeric strings and `Exempt`. It must not be coerced to an ordinary continuous number without a documented mapping.
- Units are not documented in the repository. The file names and field names suggest HMDA-derived measures, but dollar units, rate conventions, and timing/as-of semantics remain unverified.
- `lei` identifies a lending institution, not an individual application. No original application/case identifier or row-level provenance key is present in the processed schema.
- Representative extreme values were also found in the raw HMDA extracts, including `999000005000` for loan amount and `1401111800.0` for CLTV. This shows that at least these values were preserved from the available raw source; it does not prove they are valid observations.

## Initial leakage assessment

Potential leakage or timing risks require a locked task definition:

- `action_taken` is a named outcome field and the strongest candidate target. It must not be available as a worker input if the system is intended to assess an application before that outcome.
- `rate_spread` and likely `interest_rate` can reflect pricing or post-decision information. Their event timing is undocumented.
- `property_value`, `combined_loan_to_value_ratio`, and `debt_to_income_ratio` may be application inputs or underwritten values. Their as-of timing is not documented.
- The derived product and dwelling fields may be post-processed representations rather than raw applicant inputs.
- Random row splits would risk contamination because there are 4,794 institutions, repeated observations, and 165,974 duplicate rows. A group/time split policy is needed before modeling or evaluation.

## Profile conclusion

This file is a large HMDA-derived, 2025-only table with a usable structural schema but unresolved provenance, units, case identity, event timing, special-code semantics, and extreme-value policy. It is not yet established as suitable for mortgage pre-check, and it should not be passed to AI workers until a task contract and sanitized feature allowlist are approved.
