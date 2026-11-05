# Local Startup Instructions — Mortgage Pre-Check AI

Follow these instructions to run the Mortgage Pre-Check AI backend and frontend locally.

---

## 1. Prerequisites

- Python 3.11 or higher
- PowerShell or standard POSIX terminal
- Web browser (Chrome, Firefox, Edge, Safari)

Verify your Python version:
```bash
python --version
```

---

## 2. Environment Setup

From the repository root (`D:\Mortgage AI`):

```bash
# Optional: create a virtual environment
python -m venv .venv

# Activate on Windows:
.venv\Scripts\activate

# Install dependencies
pip install -e .
```

---

## 3. Starting the Backend API

The backend is powered by FastAPI and Uvicorn.

```bash
python -m uvicorn backend.api:app --host 127.0.0.1 --port 8001
```

### Verifying the Backend
In another terminal or browser:
```bash
curl http://127.0.0.1:8001/api/health
```
Expected response:
```json
{
  "status": "ok",
  "backend": "langgraph",
  "api_version": "1"
}
```

Interactive API documentation (Swagger UI) is available at:
[http://127.0.0.1:8001/docs](http://127.0.0.1:8001/docs)

---

## 4. Starting the Frontend Console

The frontend is served via a dedicated static file server that also handles reverse-proxying API calls:

```bash
python frontend/static_server.py --port 8765
```

Open the application:
[http://127.0.0.1:8765/index.html](http://127.0.0.1:8765/index.html)

---

## 5. Port Configuration Reference

| Service | Host | Port | Endpoint |
|---|---|---|---|
| Backend (FastAPI) | `127.0.0.1` | `8001` | `/api/health`, `/api/precheck`, `/api/demo-run` |
| Frontend Console | `127.0.0.1` | `8765` | `/index.html`, `/styles.css`, `/app.js` |
| Frontend Proxy | `127.0.0.1` | `8765` | `/api/*` proxies to `http://127.0.0.1:8001/api/*` |

---

## 6. Testing End-to-End Workflows

### A. Quick Synthetic Demo (No File Required)
1. Navigate to [http://127.0.0.1:8765/index.html](http://127.0.0.1:8765/index.html).
2. The default form is pre-populated with a clean loan application.
3. Click **"Submit and run pre-check"**.
4. Result:
   - Status: **Completed**
   - Recommendation: **Proceed**
   - Audit Trail: 4 worker events completed

### B. Uploading a Document with Conflicts
1. In the file input, select `tests/fixtures/documents/CASE01_baseline.pdf`.
2. Click **"Submit and run pre-check"**.
3. A review panel will display:
   - Extracted document facts (Income: \$1,200,000, Property Value: \$325,000, Debt: \$1,800)
   - Discrepancy warnings highlighted
4. Click **"Confirm reviewed values and run pre-check"**.
5. Result:
   - Status: **Needs human review**
   - Recommendation: **Flag for manual review**
   - Findings: Explicit conflict details surfaced
