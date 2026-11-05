# Mortgage Pre-Check test matrix

All automated cases use synthetic values. Most fixtures live under
`tests/fixtures/`; the Case 01 regression uses the supplied synthetic demo-pack
PDF (or `MORTGAGE_CASE01_BASELINE_PDF` when set). No raw research dataset is
used by the runtime tests.

## Automated matrix

| Area | Automated coverage | Expected interpretation |
| --- | --- | --- |
| Baseline form | `test_valid_baseline_separates_input_success_from_human_review` | A valid request can still require human review; it is never treated as an approval. |
| Required numeric fields | `test_required_numeric_fields_cannot_be_missing`; numeric matrix | `loan_amount` and `annual_income` are required and must be greater than zero. |
| Optional numeric fields | Numeric matrix and `test_optional_numeric_fields_can_be_missing_with_current_worker_handling` | `co_applicant_annual_income` and `monthly_debt_obligations` accept zero; optional fields may be absent. Current extraction only reports some optional fields as missing. |
| Numeric malformed/large values | `test_each_numeric_field_accepts_valid_and_very_large_values_but_rejects_bad_input` | Pydantic rejects malformed values for typed numeric fields; very large positive values are accepted because no maximum is configured. |
| DTI boundaries | `test_numeric_boundary_values_follow_the_actual_schema_rules`, DTI domain/property tests | Numeric DTI accepts 0 through 100 inclusive. Values outside that range are input errors. A malformed DTI string is currently preserved as a bucket. |
| Loan types | `test_every_frontend_loan_type_is_accepted_by_the_runtime_contract`; unsupported-loan regression | The UI exposes conventional/FHA/VA/USDA. The backend currently accepts every non-empty string; it has no product enum/policy check. |
| Supported uploads | `test_every_declared_upload_type_has_a_deterministic_validation_path` | TXT, Markdown, CSV, JSON, and PDF use the declared MIME/extension paths. |
| Matching facts | `test_matching_document_facts_have_upload_provenance_and_source_lines` | Extracted values have uploaded-document provenance, 0.9 confidence, and source line evidence. |
| PDF label/value layout | `test_sanitizer_preserves_only_a_safe_adjacent_value_for_pdf_style_labels`; Case 01 regression | A label followed by a constrained, expected value on the next PDF text line is retained. An adjacent unrelated name is discarded before workers receive document text. |
| Case 01 PDF regression | `test_case01_actual_pdf_upload_extracts_facts_and_surfaces_conflicts` | The supplied `CASE01_baseline.pdf` was executed from the local synthetic demo pack: PDF text extraction returned 250,000 / 1,200,000 / 1,800 / 325,000 / 38, with exactly three conflicts (income, monthly debt, property value). Matching loan amount and DTI are not flagged; the structured 60,000 / 1,900 / 300,000 values remain in the reviewed pipeline summary. |
| Conflicting facts | `test_conflicting_form_and_document_facts_are_reported_but_structured_values_remain_authoritative` | Conflicts create a warning/manual-review path; document values do not replace reviewed structured values. |
| Ambiguous text | `test_ambiguous_duplicate_labels_are_deterministic_but_not_marked_ambiguous` | The current regex takes the first match and does not emit an ambiguity finding. |
| Missing/unreadable/empty/corrupt files | `test_missing_labeled_facts_produce_missing_evidence_and_manual_review`; upload error matrix | Missing facts become evidence gaps; invalid encoding, empty/blank text, corrupt PDF, unsupported type, MIME mismatch, and invalid base64 fail safely. |
| Upload size | `test_upload_size_boundary_accepts_two_megabytes_and_rejects_one_byte_more` | The decoder accepts at most 2 MiB and rejects one byte over. |
| Duplicate/multiple documents | Duplicate hash test and single-document-contract test | Identical uploads are observable by hash but not deduplicated. A list of documents is rejected because the API has one upload slot. |
| Review/correction | `test_review_correction_changes_structured_value_and_marks_reviewer_provenance`; Case 01 regression; frontend contract tests | Review controls start from structured form values; document facts are shown separately. Only changed values are marked `reviewer_correction`. |
| Missing information | Optional-field tests and missing-facts test | Required form omissions are 422 input errors; accepted missing evidence produces `documentation_incomplete`. |
| Policy checks | Default-policy and caller-supplied DTI/LTV tests | No lending threshold is invented by default. Only caller-supplied configured limits produce policy flags. |
| Explanations/review flags | Baseline, policy/narrative, and demo regression tests | Responses expose explanations, rule IDs, fairness limitations, and `human_review_required`; no final approval/denial is inferred. |
| Worker failures/recovery | Per-worker retry tests, graph-step limit, malformed output test | Worker exceptions and malformed typed outputs retry within the graph and become typed failures. |
| API malformed requests | Required/extra fields, malformed JSON, request-size header tests | Requests fail closed with 400/413/422 responses and bounded error bodies. |
| Sensitive-data boundary | Sanitization and safe-error tests | Irrelevant/protected document lines and internal exception text are not returned to ordinary worker output. |
| Isolated worker contracts | `tests/test_worker_diagnostic_audit.py` | Extraction, policy, narrative, fairness, and typed output boundaries are tested independently of the full HTTP route. |
| Regression routes | Demo route and existing repository tests | Synthetic demo and four-worker trace remain functional. |

## Manual-testing checklist

These items cannot be fully verified by the current automated suite without a
browser or functionality that the repository does not implement:

- Open the static console, submit the baseline form, and confirm the backend health indicator changes from the initial state.
- From a clean page load, select `CASE01_baseline.pdf`, submit it for extraction, and confirm the review panel separately displays the five document facts and exactly the three conflicts (income, monthly debt, property value) before confirmation. The document and structured values must remain distinct.
- Submit a synthetic TXT file through the browser, verify the extraction review panel appears, edit at least two extracted values, and confirm the reviewed run displays reviewer provenance.
- Repeat upload flow with Markdown, CSV, JSON, and a text-bearing PDF using the browser file picker; verify client-side size messaging and server-side MIME errors.
- Select Joint applicant, verify co-applicant fields appear, then submit with and without co-applicant values.
- Try zero, negative, blank, decimal, and very large values in each browser number control and verify browser validation plus server validation agree.
- Verify malformed DTI text is rejected or clearly explained in the UI if product requirements later tighten the current permissive backend behavior.
- Confirm the browser never displays raw discarded document lines, file contents, or request payloads in the audit view.
- Confirm repeated identical uploads are surfaced for human review if duplicate detection is required; the current API does not deduplicate them.
- Verify multi-document conflict review. The current API has no multi-document contract, so cross-document conflict handling is a product gap rather than an automated claim.
- Verify any desired downloadable/report-generation workflow. The current application exposes pipeline explanations and traces but no report-generation route or downloadable report artifact.
- Exercise backend restart/unavailability and confirm the frontend shows its fail-closed health/error state.

