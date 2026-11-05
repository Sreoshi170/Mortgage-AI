const runForm = document.querySelector("#run-form");
const submitRun = document.querySelector("#submit-run");
const documentFile = document.querySelector("#supporting-document-file");
const reviewPanel = document.querySelector("#review-panel");
const runReviewedButton = document.querySelector("#run-reviewed");
let reviewedDocumentFile = null;
const API_BASE = window.MORTGAGE_API_BASE || (
  ["127.0.0.1", "localhost"].includes(window.location.hostname)
    ? "http://127.0.0.1:8001"
    : ""
);

function apiUrl(path) {
  return `${API_BASE}${path}`;
}
const emptyState = document.querySelector("#empty-state");
const results = document.querySelector("#results");
const errorState = document.querySelector("#error-state");

const statusLabels = {
  completed: "Completed",
  needs_human_review: "Needs human review",
  failed: "Failed",
};

function text(value, fallback = "—") {
  return value === null || value === undefined || value === "" ? fallback : String(value);
}

function displayRecommendation(value) {
  return {
    proceed: "Proceed",
    flag_for_manual_review: "Flag for manual review",
    documentation_incomplete: "Documentation incomplete",
  }[value] || text(value);
}

function displayFairness(value) {
  return {
    not_evaluable: "Not evaluable",
    evaluated_no_findings: "Evaluated: no findings",
    evaluated_with_findings: "Evaluated: findings require review",
  }[value] || text(value);
}

function setText(selector, value) {
  document.querySelector(selector).textContent = text(value);
}

function listText(values, fallback = "None") {
  return Array.isArray(values) && values.length ? values.join(", ") : fallback;
}

function showError(message) {
  errorState.textContent = message;
  errorState.hidden = false;
}

function clearError() {
  errorState.hidden = true;
  errorState.textContent = "";
}

function setStatus(result) {
  const status = document.querySelector("#status-indicator");
  status.textContent = statusLabels[result.status] || result.status;
  status.className = "status-indicator";
  if (result.status === "completed") status.classList.add("completed");
  if (result.status === "needs_human_review") status.classList.add("review");
  if (result.status === "failed") status.classList.add("failed");
  const failureDetail = result.failure?.code ? `Typed backend failure: ${result.failure.code}.` : "Actual status from the LangGraph backend.";
  setText("#status-detail", result.status === "failed" ? failureDetail : "Actual status from the LangGraph backend.");
}

function renderWorkers(result) {
  const workerList = document.querySelector("#worker-list");
  const rows = [
    ["Extraction Worker", result.extraction, "Typed normalization and schema validation"],
    ["Policy-Check Worker", result.policy, "Deterministic configured rule checks"],
    ["Decision-Narrative Worker", result.narrative, "Evidence-linked non-final explanation"],
    ["Fairness-Check Worker", result.fairness, "Protected-data-isolated reasoning review"],
  ];
  workerList.replaceChildren(...rows.map(([name, output, detail], index) => {
    const item = document.createElement("li");
    item.className = "worker-row";
    const outputStatus = output
      ? (name.startsWith("Fairness") && (result.fairness.requires_human_review || result.fairness.status === "evaluated_with_findings") ? "Review" : "Completed")
      : "Not run";
    const statusClass = outputStatus === "Review" ? "worker-status review" : "worker-status";
    item.innerHTML = `<span class="worker-index">${index + 1}</span><div><div class="worker-name">${name}</div><div class="worker-detail">${detail}</div></div><span class="${statusClass}">${outputStatus}</span>`;
    return item;
  }));
}

function renderAudit(result) {
  const table = document.querySelector("#audit-table");
  table.replaceChildren(...(result.audit_events || []).map((event) => {
    const row = document.createElement("tr");
    [event.node, event.event_type, event.status, event.attempt, event.timestamp].forEach((value, index) => {
      const cell = document.createElement("td");
      if (index === 0) {
        const code = document.createElement("code");
        code.textContent = text(value);
        cell.appendChild(code);
      } else {
        cell.textContent = text(value);
      }
      row.appendChild(cell);
    });
    return row;
  }));
}

function renderExtraction(result) {
  const extraction = result.extraction;
  const summary = extraction?.summary || {};
  const fields = [
    ["Applicant type", summary.applicant_type],
    ["Co-applicant present", summary.co_applicant_present ? "Yes" : "No"],
    ["Loan amount", summary.loan_amount],
    ["Loan purpose", summary.loan_purpose],
    ["Income type", summary.income_type],
    ["Income", summary.income],
    ["Monthly debt obligations", summary.monthly_debt_obligations],
    ["Property value", summary.property_value],
    ["Property type", summary.property_type],
    ["Property units", summary.property_units],
    ["Occupancy", summary.occupancy_type],
    ["Debt-to-income", summary.debt_to_income_ratio ?? summary.debt_to_income_bucket],
    ["Combined LTV", summary.combined_loan_to_value_ratio],
    ["Interest rate", summary.interest_rate],
    ["Rate spread", summary.rate_spread],
  ];
  const container = document.querySelector("#extraction-summary");
  container.replaceChildren(...fields.map(([label, value]) => {
    const item = document.createElement("div");
    const name = document.createElement("span");
    name.className = "metric-label";
    name.textContent = label;
    const valueNode = document.createElement("strong");
    valueNode.textContent = text(value);
    item.append(name, valueNode);
    return item;
  }));
  setText("#extraction-valid", extraction ? (extraction.valid ? "Valid typed output" : "Invalid typed output") : "Not run");
  setText("#extraction-missing", listText(extraction?.missing_fields));
  const warningText = [
    ...(extraction?.warnings || []),
    ...Object.entries(summary.special_codes || {}).map(([key, value]) => `${key}=${value}`),
  ];
  setText("#extraction-warnings", listText(warningText));
  const facts = result.extracted_facts || extraction?.extracted_facts || {};
  const factsContainer = document.querySelector("#extracted-facts");
  factsContainer.replaceChildren(...Object.entries(facts).map(([name, fact]) => {
    const item = document.createElement("div");
    const label = document.createElement("span");
    label.className = "metric-label";
    label.textContent = name;
    const value = document.createElement("strong");
    value.textContent = `${text(fact.value)} · ${text(fact.provenance?.source)} · confidence ${text(fact.provenance?.confidence)}`;
    item.append(label, value);
    return item;
  }));
  if (!Object.keys(facts).length) setText("#extracted-facts", "No supported labeled facts extracted.");
  const findings = result.validation_findings || extraction?.validation_findings || [];
  setText("#validation-findings", findings.length ? findings.map((finding) => `${finding.severity}: ${finding.message}`).join("; ") : "None");
  setText("#missing-evidence", listText(result.missing_evidence || extraction?.missing_evidence));
}

function renderPolicy(result) {
  const table = document.querySelector("#policy-table");
  table.replaceChildren(...(result.policy?.checks || []).map((check) => {
    const row = document.createElement("tr");
    [check.rule_id, check.status, check.evidence].forEach((value) => {
      const cell = document.createElement("td");
      cell.textContent = text(value);
      row.appendChild(cell);
    });
    return row;
  }));
  setText("#policy-missing", listText(result.policy?.missing_fields));
}

function renderFairness(result) {
  const fairness = result.fairness;
  setText("#fairness-detail-status", displayFairness(fairness?.status));
  setText("#fairness-rule-ids", listText(fairness?.inspected_rule_ids));
  setText("#fairness-detail-concerns", listText(fairness?.concerns));
  setText("#protected-data-seen", fairness?.protected_data_seen === false ? "Protected data not exposed" : "Not available");
}

function render(result) {
  const trace = result.pipeline_trace || result;
  const status = trace.status === "failed"
    ? "failed"
    : (result.human_review_required ? "needs_human_review" : "completed");
  const view = { ...trace, status };
  emptyState.hidden = true;
  results.hidden = false;
  setStatus(view);
  setText("#case-id", trace.case_id);
  setText("#run-id", trace.run_id);
  setText("#last-updated", trace.audit_events?.at(-1)?.timestamp || "No timestamp");
  setText("#recommendation", result.recommendation || displayRecommendation(trace.recommendation));
  setText("#policy-contract-status", result.policy_check?.status || "Not available");
  setText("#policy-contract-reason", result.policy_check?.reason || "Not available");
  setText("#human-review", result.human_review_required === true ? "Required" : "Not required");
  setText("#fairness-status", result.fairness_check?.status || displayFairness(trace.fairness?.status));
  setText("#gate-status", trace.gate_status === "not_run" ? "Not run" : trace.gate_status);
  setText("#audit-count", trace.audit_events?.length || 0);
  setText("#narrative", result.explanation || trace.narrative?.narrative);
  setText("#fairness-concern", result.fairness_check?.reason || trace.fairness?.concerns?.join(" "));
  setText("#evidence-rule-ids", listText(trace.narrative?.evidence_rule_ids));
  renderWorkers(trace);
  renderExtraction(trace);
  renderPolicy(trace);
  renderFairness(trace);
  renderAudit(trace);
}

async function executeRun(url, options, button, idleLabel, pendingLabel) {
  clearError();
  button.disabled = true;
  button.textContent = pendingLabel;
  try {
    const response = await fetch(apiUrl(url), options);
    const payload = await response.json().catch(() => ({}));
    if (!response.ok) {
      throw new Error(payload.error || "The backend returned an HTTP error.");
    }
    render(payload);
  } catch (error) {
    showError(error.message || "Unable to load the backend response.");
  } finally {
    button.disabled = false;
    button.textContent = idleLabel;
  }
}

function formPayload() {
  const values = Object.fromEntries(new FormData(runForm).entries());
  const optionalNumber = (value) => value === undefined || value === "" ? null : Number(value);
  return {
    applicant_type: values.applicant_type,
    co_applicant_present: values.co_applicant_present === "on",
    co_applicant_annual_income: optionalNumber(values.co_applicant_annual_income),
    co_applicant_income_type: values.co_applicant_income_type || null,
    loan_amount: values.loan_amount,
    annual_income: values.annual_income,
    income_type: values.income_type,
    monthly_debt_obligations: optionalNumber(values.monthly_debt_obligations),
    loan_type: values.loan_type,
    loan_purpose: values.loan_purpose,
    debt_to_income_ratio: values.debt_to_income_ratio,
    property_value: optionalNumber(values.property_value),
    property_type: values.property_type,
    property_units: optionalNumber(values.property_units),
    occupancy_type: values.occupancy_type,
    supporting_document: values.supporting_document,
  };
}

function mediaTypeFor(file) {
  if (file.type) return file.type;
  return {
    ".txt": "text/plain",
    ".md": "text/markdown",
    ".csv": "text/csv",
    ".json": "application/json",
    ".pdf": "application/pdf",
  }[file.name.slice(file.name.lastIndexOf(".")).toLowerCase()] || "application/octet-stream";
}

async function fileBase64(file) {
  const bytes = new Uint8Array(await file.arrayBuffer());
  let binary = "";
  const chunkSize = 0x8000;
  for (let index = 0; index < bytes.length; index += chunkSize) {
    binary += String.fromCharCode(...bytes.subarray(index, index + chunkSize));
  }
  return btoa(binary);
}

async function uploadPayload(file = documentFile.files[0]) {
  if (!file) throw new Error("Choose a supporting document or clear the upload field to use synthetic mode.");
  if (file.size <= 0 || file.size > 2 * 1024 * 1024) throw new Error("The document must be between 1 byte and 2 MB.");
  return {
    ...formPayload(),
    supporting_document: {
      filename: file.name,
      media_type: mediaTypeFor(file),
      content_base64: await fileBase64(file),
    },
  };
}

function logUploadDiagnostic(file, extractionStatus, extractedFieldNames = []) {
  // Metadata only: do not log document text, base64 bytes, or extracted values.
  console.info("mortgage-precheck document extraction", {
    filename: file.name,
    media_type: mediaTypeFor(file),
    extraction_status: extractionStatus,
    extracted_field_names: extractedFieldNames,
  });
}

function setUploadStatus(message, isError = false) {
  const status = document.querySelector("#upload-status");
  status.textContent = message;
  status.classList.toggle("upload-error", isError);
}

function renderReviewDraft(draft) {
  reviewPanel.hidden = false;
  const values = formPayload();
  const reviewValues = {
    loan_amount: values.loan_amount,
    income: values.annual_income,
    property_value: values.property_value || "",
    monthly_debt_obligations: values.monthly_debt_obligations || "",
    loan_type: values.loan_type,
    debt_to_income_ratio: values.debt_to_income_ratio,
  };
  document.querySelector("#review-loan-amount").value = reviewValues.loan_amount;
  document.querySelector("#review-annual-income").value = reviewValues.income;
  document.querySelector("#review-property-value").value = reviewValues.property_value;
  document.querySelector("#review-monthly-debt").value = reviewValues.monthly_debt_obligations;
  document.querySelector("#review-loan-type").value = reviewValues.loan_type;
  document.querySelector("#review-dti").value = reviewValues.debt_to_income_ratio;
  reviewPanel.dataset.initialValues = JSON.stringify(reviewValues);
  reviewPanel.dataset.formSnapshot = JSON.stringify(values);
  reviewPanel.dataset.reviewToken = draft.review_token || "";
  const facts = Object.entries(draft.extracted_facts || {});
  document.querySelector("#review-extracted-facts").textContent = facts.length
    ? facts.map(([name, fact]) => `${name}: ${text(fact.value)} · ${text(fact.provenance?.source)} · confidence ${text(fact.provenance?.confidence)}`).join("; ")
    : "No supported labeled facts extracted from the document.";
  const findings = draft.validation_findings || [];
  document.querySelector("#review-findings").textContent = findings.length
    ? findings.map((finding) => `${finding.severity}: ${finding.message}`).join("; ")
    : "No deterministic inconsistencies found. Confirm the values before running.";
  submitRun.textContent = "Re-extract document for review";
}

async function beginDocumentReview(event) {
  event.preventDefault();
  clearError();
  submitRun.disabled = true;
  submitRun.textContent = "Extracting document…";
  try {
    const file = documentFile.files[0];
    reviewedDocumentFile = null;
    const requestPayload = await uploadPayload(file);
    logUploadDiagnostic(file, "request_prepared");
    const response = await fetch(apiUrl("/api/precheck/extract"), {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(requestPayload),
    });
    const responsePayload = await response.json().catch(() => ({}));
    if (!response.ok) {
      logUploadDiagnostic(file, "failed");
      throw new Error(responsePayload.detail?.message || responsePayload.detail?.code || "Document extraction failed.");
    }
    logUploadDiagnostic(file, "success", Object.keys(responsePayload.extracted_facts || {}));
    reviewedDocumentFile = file;
    setUploadStatus(`Validated ${responsePayload.document.filename}; extraction draft ready for review.`);
    renderReviewDraft(responsePayload);
  } catch (error) {
    setUploadStatus(error.message || "Document extraction failed.", true);
    showError(error.message || "Unable to extract the document.");
  } finally {
    submitRun.disabled = false;
    if (!reviewPanel.hidden) submitRun.textContent = "Re-extract document for review";
    else submitRun.textContent = "Submit and run pre-check";
  }
}

async function runReviewed(event) {
  event.preventDefault();
  clearError();
  runReviewedButton.disabled = true;
  runReviewedButton.textContent = "Running reviewed pre-check…";
  try {
    const file = documentFile.files[0];
    if (!file || file !== reviewedDocumentFile) {
      throw new Error("The selected document changed after extraction. Re-extract it before confirming reviewed values.");
    }
    const payload = await uploadPayload(file);
    const initialForm = JSON.parse(reviewPanel.dataset.formSnapshot || "{}");
    const reviewFieldNames = new Set([
      "loan_amount",
      "annual_income",
      "property_value",
      "monthly_debt_obligations",
      "loan_type",
      "debt_to_income_ratio",
    ]);
    const formChangedOutsideReview = Object.entries(formPayload()).some(([name, value]) => (
      name !== "supporting_document" && !reviewFieldNames.has(name) && String(value ?? "") !== String(initialForm[name] ?? "")
    ));
    if (formChangedOutsideReview) {
      throw new Error("The application form changed after extraction. Re-extract the document before confirming reviewed values.");
    }
    if (!reviewPanel.dataset.reviewToken) {
      throw new Error("The extraction review context is unavailable. Re-extract the document before confirming values.");
    }
    payload.loan_amount = document.querySelector("#review-loan-amount").value;
    payload.annual_income = document.querySelector("#review-annual-income").value;
    payload.property_value = document.querySelector("#review-property-value").value || null;
    payload.monthly_debt_obligations = document.querySelector("#review-monthly-debt").value || null;
    payload.loan_type = document.querySelector("#review-loan-type").value;
    payload.debt_to_income_ratio = document.querySelector("#review-dti").value;
    payload.review_confirmed = true;
    const initialValues = JSON.parse(reviewPanel.dataset.initialValues || "{}");
    const currentValues = {
      loan_amount: payload.loan_amount,
      income: payload.annual_income,
      property_value: payload.property_value || "",
      monthly_debt_obligations: payload.monthly_debt_obligations || "",
      loan_type: payload.loan_type,
      debt_to_income_ratio: payload.debt_to_income_ratio,
    };
    payload.corrected_fields = Object.entries(currentValues)
      .filter(([name, value]) => String(value) !== String(initialValues[name] ?? ""))
      .map(([name]) => name);
    payload.review_token = reviewPanel.dataset.reviewToken;
    const response = await fetch(apiUrl("/api/precheck/review"), {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(payload),
    });
    const result = await response.json().catch(() => ({}));
    if (!response.ok) throw new Error(result.detail?.message || result.detail?.code || "Reviewed pre-check failed.");
    render(result);
  } catch (error) {
    showError(error.message || "Unable to run the reviewed pre-check.");
  } finally {
    runReviewedButton.disabled = false;
    runReviewedButton.textContent = "Confirm reviewed values and run pre-check";
  }
}

function runDynamic(event) {
  if (documentFile.files.length) return beginDocumentReview(event);
  event.preventDefault();
  return executeRun(
    "/api/precheck",
    {
      method: "POST",
      headers: { Accept: "application/json", "Content-Type": "application/json" },
      body: JSON.stringify(formPayload()),
    },
    submitRun,
    "Submit and run pre-check",
    "Submitting…",
  );
}

function updateCoApplicantFields() {
  const present = document.querySelector("#co-applicant-present").checked;
  document.querySelector("#co-applicant-income-field").hidden = !present;
  document.querySelector("#co-applicant-income-type-field").hidden = !present;
  if (!present) {
    document.querySelector("[name=co_applicant_annual_income]").value = "";
    document.querySelector("[name=co_applicant_income_type]").value = "";
  }
}

documentFile.addEventListener("change", () => {
  const file = documentFile.files[0];
  reviewedDocumentFile = null;
  reviewPanel.dataset.reviewToken = "";
  if (!file) {
    setUploadStatus("No file selected; the synthetic text fallback will be used.");
    return;
  }
  if (file.size <= 0 || file.size > 2 * 1024 * 1024) {
    setUploadStatus("File must be between 1 byte and 2 MB.", true);
    return;
  }
  setUploadStatus(`Selected ${file.name} (${Math.ceil(file.size / 1024)} KB); validation runs on submit.`);
});

document.querySelector("#co-applicant-present").addEventListener("change", updateCoApplicantFields);
updateCoApplicantFields();

async function loadHealth() {
  try {
    const response = await fetch(apiUrl("/api/health"), { headers: { Accept: "application/json" } });
    const health = await response.json();
    if (!response.ok || health.status !== "ok") throw new Error("Backend health check failed.");
    const modelMode = document.querySelector("#model-mode");
    const backendMode = document.querySelector("#backend-mode");
    const backendModel = document.querySelector("#backend-model");
    modelMode.textContent = "DETERMINISTIC MODE";
    backendMode.textContent = "Local deterministic mode";
    backendModel.textContent = "No paid model calls";
  } catch (error) {
    document.querySelector("#backend-mode").textContent = "Backend health unavailable";
    document.querySelector("#backend-model").textContent = "Run may fail closed";
  }
}

runForm.addEventListener("submit", runDynamic);
runReviewedButton.addEventListener("click", runReviewed);
loadHealth();
