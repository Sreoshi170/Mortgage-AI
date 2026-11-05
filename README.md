# Mortgage Pre-Check AI

A deterministic, multi-agent AI pipeline for mortgage pre-check evaluation, built with FastAPI, LangGraph, and Pydantic v2.

> [!NOTE]
> **Research Pre-Check Only**: This system performs an exploratory pre-check validation of application data and supporting documents. It **never** issues an automated final loan approval or denial.

---

## Overview

Mortgage Pre-Check AI evaluates loan applications against uploaded or synthetic documents through a bounded 4-worker LangGraph pipeline:

1. **Extraction Worker**: Normalizes structured application fields, extracts labeled facts from supporting documents (PDF, TXT, CSV, JSON, Markdown), captures line-level provenance, and detects document-to-form discrepancies.
2. **Policy-Check Worker**: Evaluates applications against documentation completeness requirements (DOC-001 through DOC-004) and caller-configured policy limits (POL-001 for DTI, POL-002 for LTV).
3. **Decision-Narrative Worker**: Generates an evidence-grounded explanation identifying passed rules, flagged discrepancies, missing documents, and specific review triggers.
4. **Fairness-Check Worker**: Enforces reasoning integrity by screening narratives against prohibited attribute terms, maintaining complete isolation from demographic data at runtime.

---

## System Architecture

```
User / Form / Upload
        │
        ├── Direct /api/precheck (Synthetic or Text Document)
        └── Document Upload:
              POST /api/precheck/extract  -->  Draft Review UI
                                                      │ (User Confirmation / Corrections)
                                                      ▼
                                          POST /api/precheck/review
                                                      │
                                                      ▼
                                        LangGraph 4-Worker Pipeline:
                                        [Extraction] -> [Policy] -> [Narrative] -> [Fairness]
                                                      │
                                                      ▼
                                          Typed PipelineResult Response
```

---

## Quickstart

### Prerequisites
- Python 3.11+ (Python 3.13 tested)
- pip / virtualenv

### 1. Install Dependencies
```bash
pip install -e .
# or install dependencies directly:
pip install fastapi uvicorn pydantic langgraph pypdf
```

### 2. Start the Backend Server
```bash
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8001
```
Verify backend health:
```bash
curl http://127.0.0.1:8001/api/health
# Returns: {"status": "ok", "backend": "langgraph", "api_version": "1"}
```

### 3. Start the Frontend Server
In a separate terminal:
```bash
python frontend/static_server.py --port 8765
```
Open your browser to:
[http://127.0.0.1:8765/index.html](http://127.0.0.1:8765/index.html)

---

## Running the Automated Test Suite

Run the full pytest suite (256 tests covering API, workers, graph state, boundary, and PDF extraction):
```bash
pytest tests/ -v --tb=short
```

For isolated worker audit tests:
```bash
pytest tests/test_worker_diagnostic_audit.py -v
```

For end-to-end API and upload regression tests:
```bash
pytest tests/test_comprehensive_precheck.py -v
```

---

## Review Decision Outcomes

The system produces distinct, explainable results based on input evidence:

| Case | Status | Recommendation | Human Review Required |
|---|---|---|---|
| Complete application, matching document, no policy flags | `completed` | `proceed` | `false` |
| Discrepancy between document and form values | `needs_human_review` | `flag_for_manual_review` | `true` |
| Missing required application or document evidence | `needs_human_review` | `documentation_incomplete` | `true` |
| Caller-configured policy limit exceeded (e.g. DTI > 40%) | `needs_human_review` | `flag_for_manual_review` | `true` |
| Prohibited reasoning terms in narrative | `needs_human_review` | `flag_for_manual_review` | `true` |
| Worker failure or timeout | `failed` | `None` | `true` |

---

## Reports & Documentation

- [Initial Diagnostic Report](file:///d:/Mortgage%20AI/reports/agent_debugging/INITIAL_DIAGNOSTIC_REPORT.md)
- [Root Cause Analysis](file:///d:/Mortgage%20AI/reports/agent_debugging/ROOT_CAUSE_ANALYSIS.md)
- [Agent Regression Test Report](file:///d:/Mortgage%20AI/reports/agent_debugging/AGENT_REGRESSION_TEST_REPORT.md)
- [Final Agent Verification Report](file:///d:/Mortgage%20AI/reports/agent_debugging/FINAL_AGENT_VERIFICATION_REPORT.md)
- [Known Limitations](file:///d:/Mortgage%20AI/reports/agent_debugging/KNOWN_LIMITATIONS.md)
- [Architecture Details](file:///d:/Mortgage%20AI/docs/ARCHITECTURE.md)
- [Testing Guide](file:///d:/Mortgage%20AI/docs/TESTING_GUIDE.md)
- [Local Startup Instructions](file:///d:/Mortgage%20AI/docs/LOCAL_STARTUP.md)
