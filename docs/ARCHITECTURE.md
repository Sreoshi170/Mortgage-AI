# Mortgage Pre-Check AI architecture

## Runtime request path

```text
Browser structured application form + optional file
        |
        | JSON application contract plus upload envelope: filename, media type, base64 bytes
        v
FastAPI /api/precheck/extract
        |
        | validate type/size/encoding; decode text; compute SHA-256
        v
Existing extraction worker
        |
        | extracted facts + provenance + confidence + validation findings
        v
Frontend review/correction step
        |
        v
FastAPI /api/precheck/review
        |
        v
Existing LangGraph
  Extraction -> Policy-Check -> Decision-Narrative -> Fairness-Check
        |
        v
Typed research-only response + audit events
```

The direct `/api/precheck` JSON route remains available for the established
synthetic workflow and accepts the expanded structured form fields. The new upload route does not create a second extraction or
orchestration pipeline: it decodes the file, calls the existing extraction
worker for the review draft, and passes the same sanitized document type into
the existing graph after confirmation.

## Modules

- `backend/api.py`: FastAPI routes, request-size limit, typed HTTP errors.
- `backend/service.py`: runtime upload draft, reviewed submission, and compact
  response composition.
- `mortgage_precheck/documents.py`: file type, media type, size, base64, text,
  PDF, digest validation, and a labeled-fact text allowlist. Binary content and
  unrecognized/protected document lines are not returned or passed to workers.
- `mortgage_precheck/workers/extraction.py`: existing normalization worker,
  extended with deterministic labeled-fact extraction, line-level provenance,
  and cross-field consistency checks.
- `mortgage_precheck/graph.py`: unchanged bounded LangGraph topology with the
  new runtime document union accepted at its boundary.
- `mortgage_precheck/boundary.py`: protected/proxy/outcome field boundary and
  runtime-document validation.
- `frontend/index.html` and `frontend/app.js`: file selection, extraction
  draft, review correction, final run, and result rendering.

## Data boundaries

Historical HMDA and LendingClub datasets are never read by runtime routes.
Operational workers receive only sanitized non-sensitive application fields and a sanitized
document text envelope. Protected demographic and evaluation-only fields are
not part of that envelope. The Phase 4 historical-outcome experiment remains a
separate offline design artifact and is not loaded by inference.

Runtime application units and validation:

- Currency fields (`loan_amount`, `annual_income`, `monthly_debt_obligations`,
  `property_value`, and co-applicant income) are positive USD amounts, except
  monthly debt may be zero.
- `debt_to_income_ratio` is a reported percentage; the backend does not silently
  replace it with a derived value. If income and monthly debt are supplied, a
  difference greater than one percentage point is a warning.
- `property_units` is a positive count; `property_type`, `occupancy_type`,
  `loan_type`, `loan_purpose`, and income types are controlled form values.
- Applicant type is individual or joint. Joint applications must explicitly
  indicate a co-applicant; co-applicant fields are rejected when none is present.
- The compact legacy request remains compatible, so fields not present in that
  contract are reported as missing evidence rather than fabricated.

## Failure behavior

Invalid JSON contracts are handled by FastAPI validation. Unsupported file
types, MIME mismatches, invalid base64, oversized files, invalid PDFs, empty
text, and missing review confirmation return explicit 422 errors. Worker
failures remain typed, bounded, retry-limited LangGraph failures. No failed run
is represented as a successful recommendation.
