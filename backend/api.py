"""FastAPI application exposing the typed LangGraph backend contract."""

from __future__ import annotations

from typing import Literal

from fastapi import FastAPI, HTTPException, Request
from fastapi.middleware.cors import CORSMiddleware
from fastapi.responses import JSONResponse
from pydantic import BaseModel, ConfigDict

from mortgage_precheck import PipelineRequest, PipelineResult, PrecheckRequest, PrecheckResponse, run_pipeline
from mortgage_precheck.documents import DocumentUploadError
from mortgage_precheck.boundary import BoundaryViolation
from mortgage_precheck.schemas import DocumentExtractionDraft, DocumentPrecheckRequest, ReviewedDocumentPrecheckRequest

from .service import demo_request, extract_uploaded_document, run_payload, run_precheck, run_reviewed_precheck

MAX_REQUEST_BYTES = 5_000_000


class HealthResponse(BaseModel):
    model_config = ConfigDict(extra="forbid")

    status: Literal["ok"]
    backend: Literal["langgraph"]
    api_version: str


app = FastAPI(
    title="Mortgage Pre-Check Backend",
    version="0.1.0",
    description="Bounded LangGraph research backend; not a mortgage underwriting service.",
)
app.add_middleware(
    CORSMiddleware,
    allow_origins=["http://127.0.0.1:8765", "http://localhost:8765"],
    allow_credentials=False,
    allow_methods=["GET", "POST"],
    allow_headers=["Content-Type", "Accept"],
)


@app.get("/", include_in_schema=False)
def root() -> dict[str, object]:
    """Provide a visible service landing response instead of a confusing 404."""

    return {
        "service": "Mortgage Pre-Check Backend",
        "status": "ok",
        "mode": "deterministic",
        "docs": "/docs",
        "health": "/api/health",
        "demo_run": "/api/demo-run",
        "run": "POST /api/run",
        "precheck": "POST /api/precheck",
        "document_extract": "POST /api/precheck/extract",
        "document_review": "POST /api/precheck/review",
        "note": "Research pre-check only; not a final mortgage underwriting decision.",
    }


@app.middleware("http")
async def limit_run_request_size(request: Request, call_next):
    if request.method == "POST" and request.url.path in {"/api/run", "/api/precheck", "/api/precheck/extract", "/api/precheck/review"}:
        raw_length = request.headers.get("content-length")
        try:
            content_length = int(raw_length or "0")
        except ValueError:
            return JSONResponse({"status": "failed", "error": "invalid_content_length"}, status_code=400)
        if content_length <= 0 or content_length > MAX_REQUEST_BYTES:
            return JSONResponse({"status": "failed", "error": "request_size_invalid"}, status_code=413)
    return await call_next(request)


@app.get("/api/health", response_model=HealthResponse)
def health() -> dict:
    return {"status": "ok", "backend": "langgraph", "api_version": "1"}


@app.get("/api/demo-run", response_model=PipelineResult)
def demo_run() -> dict:
    return run_payload(demo_request())


@app.post("/api/run", response_model=PipelineResult)
def run(request: PipelineRequest) -> PipelineResult:
    return run_pipeline(request)


@app.post("/api/precheck", response_model=PrecheckResponse)
def precheck(request: PrecheckRequest) -> PrecheckResponse:
    """Accept the compact applicant-facing input contract."""

    return run_precheck(request)


def _upload_error(exc: BaseException) -> HTTPException:
    code = getattr(exc, "code", "document_request_invalid")
    return HTTPException(status_code=422, detail={"code": code, "message": code})


@app.post("/api/precheck/extract", response_model=DocumentExtractionDraft)
def extract_document(request: DocumentPrecheckRequest) -> DocumentExtractionDraft:
    """Validate an upload and return a reviewable extraction draft."""

    try:
        return extract_uploaded_document(request)
    except (DocumentUploadError, BoundaryViolation) as exc:
        raise _upload_error(exc) from exc


@app.post("/api/precheck/review", response_model=PrecheckResponse)
def reviewed_precheck(request: ReviewedDocumentPrecheckRequest) -> PrecheckResponse:
    """Run the existing LangGraph after the user confirms reviewed values."""

    try:
        return run_reviewed_precheck(request)
    except (DocumentUploadError, BoundaryViolation) as exc:
        raise _upload_error(exc) from exc

