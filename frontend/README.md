# Frontend and backend

The review console is a separate static frontend connected to the FastAPI LangGraph backend. It does not display fabricated metrics.

Run the backend from the repository root:

```powershell
python -m pip install -e ".[api]"
python -m backend.api_server --port 8001
```

Run the frontend in a second terminal:

```powershell
python -m frontend.static_server --port 8765
```

Open <http://127.0.0.1:8765>. The applicant form submits this non-sensitive
runtime contract to `POST /api/precheck`:

```json
{
  "applicant_type": "individual",
  "co_applicant_present": false,
  "loan_amount": 250000,
  "annual_income": 60000,
  "income_type": "employment",
  "monthly_debt_obligations": 1900,
  "loan_type": "conventional",
  "loan_purpose": "purchase",
  "debt_to_income_ratio": 38,
  "property_value": 300000,
  "property_type": "single_family",
  "property_units": 1,
  "occupancy_type": "primary_residence",
  "supporting_document": "Synthetic employment verification letter"
}
```

The response includes `extraction_status`, `policy_check`, `recommendation`, `fairness_check`, `human_review_required`, an explanation, and the complete worker/audit trace.

When a file is selected, the browser first sends the structured form plus a
base64 upload envelope to `POST /api/precheck/extract`. The response contains
deterministically extracted facts, provenance, confidence, validation findings,
and missing evidence. The user can correct the displayed values and confirm a
reviewed submission to `POST /api/precheck/review`, which runs the existing
LangGraph. Corrected values are marked with reviewer provenance. Supported
files are TXT, Markdown, CSV, JSON, and PDF up to 2 MB; discarded document
lines are never passed to ordinary workers, while safe blank line positions are
retained for source-location provenance.

HMDA and LendingClub files in `data/raw/` are historical research datasets,
not runtime upload inputs.

The fixture is labelled `SYNTHETIC`. The current frontend intentionally does not provide application approval/denial controls or a quality-gate result.
