# Frontend runtime design

## Main screen

The Overview screen remains the synthetic research console. It now supports a
structured runtime application plus two document paths from the same form:

- The form collects applicant/co-applicant status, loan amount/purpose/type,
  income and income type, monthly debt, DTI, property value/type/units, and
  occupancy. It intentionally excludes names, government IDs, protected
  characteristics, and free-form sensitive notes.

- Without a file: the existing synthetic text path calls `/api/precheck`.
- With a file: the form calls `/api/precheck/extract`, opens a review panel,
  and then calls `/api/precheck/review` after the user confirms or corrects the
  extracted values.

## Upload contract

The browser accepts `.txt`, `.md`, `.csv`, `.json`, and `.pdf` files up to 2 MB.
The selected file is sent as a JSON-safe base64 envelope. The backend verifies
the extension/MIME pair, size, encoding, and PDF parseability. Only labeled
allowlisted fact lines reach the existing extraction worker; raw document text
and unrelated/protected lines do not cross the worker boundary.

The browser displays upload status, metadata, extracted fact values, provenance
source/location, validation findings, and deterministic confidence. It never
displays protected demographic data, raw upload text in audit output, or raw
historical dataset rows.

## Review contract

The review panel exposes the structured values that will be passed into policy
checks. Document-derived values are suggestions with provenance, not automatic
overwrites. The user must confirm the review before the LangGraph run starts.
Corrected fields are marked with `reviewer_correction` provenance in the typed
trace. Missing or conflicting values remain visible and do not silently become
facts.
Document/application inconsistencies remain visible in validation findings and
produce human-review behavior in the result.

## Result contract

The result view displays:

- extraction status and normalized facts;
- extracted facts with provenance and confidence;
- validation findings and missing evidence;
- configured policy flags and evidence;
- research-only recommendation and explanation;
- fairness status and protected-data boundary status;
- human-review requirement;
- LangGraph worker timeline and structured audit events.

The UI labels the workflow as synthetic/deterministic research mode and does
not present the historical HMDA target as an approval model.
