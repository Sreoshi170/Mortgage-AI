# Runtime input versus historical dataset inventory

Audit date: 2026-10-22  
Scope: read-only inspection of `data/raw/`. No source file was modified.

## Name resolution

The requested names are conceptual names, not exact repository paths. The
actual files are:

| Requested name | Actual repository file | Format | Delimiter | Header columns | Size (bytes) | Physical lines |
|---|---|---|---|---:|---:|---:|
| `2025_public_lar.csv` | `2025_public_lar_csv.csv` | CSV | comma | 99 | 5,114,449,258 | 13,543,607 |
| `2025_lar` | `2025_lar.txt` | pipe-delimited text | `\|` | 99 | 5,120,170,192 | 13,558,307 |
| `2025_combined_mlar_header` | `2025_combined_mlar_header.txt` | pipe-delimited text with data rows | `\|` | 85 | 3,152,450,262 | 13,558,307 |
| `accepted_2007_to_2018Q4` | `accepted_2007_to_2018Q4.csv` | CSV | comma | 151 | 1,675,133,810 | 2,260,702 |
| `rejected_2007_to_2018Q4` | `rejected_2007_to_2018Q4.csv` | CSV | comma | 9 | 1,782,281,620 | 27,648,742 |

Physical line counts are reported because they are a safe, bounded file check.
They must not be treated as logical CSV record counts when quoted fields could
contain line breaks. The two pipe-delimited 2025 files have one header plus
13,558,306 observed data lines. The file named `2025_combined_mlar_header.txt`
is not header-only: it contains a header and data rows.

## HMDA 2025 files

`2025_public_lar_csv.csv` and `2025_lar.txt` have exactly the same 99-column
header in the same order. Their formats differ, and their first sampled records
are not identical, so this repository does not establish that they are the same
record set or safe interchangeable copies. The public LAR schema includes
action, application, pricing, property, demographic, denial-reason, and tract
fields. The [official HMDA public LAR schema](https://ffiec.cfpb.gov/documentation/publications/loan-level-datasets/public-lar-schema)
should remain the authority for field definitions.

`2025_combined_mlar_header.txt` has 85 columns and overlaps the HMDA core, but
it is not schema-equivalent to the 99-column public LAR extracts. It contains
applicant/co-applicant demographic fields, denial reasons, pricing fields, and
scoring-model fields. Its filename is misleading because it is a large data
extract, not a header artifact.

The 2025 public LAR files are historical research data. They are not runtime
application uploads and are not connected to the live pre-check endpoint. The
prepared file used in Phase 4 remains the primary research input, with the
approved historical target design only.

## LendingClub files

`accepted_2007_to_2018Q4.csv` has a 151-column LendingClub-style schema with
fields such as `loan_amnt`, `annual_inc`, `loan_status`, FICO ranges, payment
history, recoveries, hardship, and settlement fields. Several fields are
post-origination or post-outcome and cannot be treated as HMDA equivalents.

`rejected_2007_to_2018Q4.csv` has only 9 columns: amount requested, application
date, loan title, risk score, debt-to-income ratio, ZIP code, state,
employment length, and policy code. It does not share a row identifier or a
compatible schema with the accepted file in this repository.

The accepted and rejected LendingClub files are therefore a separate optional
research dataset. No join, target mapping, feature reuse, or live inference
connection is implemented. A separate experiment would require its own
provenance, eligibility, target, leakage, split, and fairness review.

## Provenance and relationship limitations

No source manifest, download URL, retrieval metadata, preprocessing script, or
join key was found beside the raw files. This report records only the verified
filenames, byte-level file metadata, headers, and sampled schema widths. Similar
names do not establish interchangeability or common provenance.

Runtime users upload only their supporting documents. They do not upload HMDA
or LendingClub historical files for an individual pre-check.
