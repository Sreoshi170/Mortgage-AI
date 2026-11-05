"""Safe, deterministic decoding for user-uploaded supporting documents."""

from __future__ import annotations

import base64
import binascii
import hashlib
import re
from concurrent.futures import ThreadPoolExecutor, TimeoutError as FutureTimeoutError
from io import BytesIO
from pathlib import Path

from .schemas import DocumentDescriptor, RuntimeDocument, SupportingDocumentInput

MAX_DOCUMENT_BYTES = 2 * 1024 * 1024
PDF_EXTRACTION_TIMEOUT_SECONDS = 2.0
ALLOWED_DOCUMENT_TYPES = {
    ".txt": {"text/plain"},
    ".md": {"text/markdown", "text/plain"},
    ".csv": {"text/csv"},
    ".json": {"application/json"},
    ".pdf": {"application/pdf"},
}


class DocumentUploadError(ValueError):
    """Raised when an upload cannot safely become a runtime document."""

    def __init__(self, code: str):
        super().__init__(code)
        self.code = code


_ALLOWLISTED_FACT_LABELS = re.compile(
    r"\b(?:loan\s+amount|amount\s+requested|annual\s+income|gross\s+annual\s+income|income\s+type|loan\s+type|loan\s+purpose|monthly\s+debt(?:\s+obligations)?|property\s+value|property\s+type|occupancy(?:\s+type)?|number\s+of\s+units|units|debt\s*[- ]to\s*[- ]income|dti)\b",
    flags=re.IGNORECASE,
)

# PDFs often expose a label and its value as adjacent text lines. Retain that
# value only when it has the constrained shape accepted for that label; this
# avoids carrying an unrelated name, address, or narrative sentence forward.
_FOLLOWING_VALUE_PATTERNS: tuple[tuple[re.Pattern[str], re.Pattern[str]], ...] = (
    (
        re.compile(r"\b(?:loan\s+amount|amount\s+requested|annual\s+income|gross\s+annual\s+income|monthly\s+debt(?:\s+obligations)?|property\s+value|number\s+of\s+units|units|debt\s*[- ]to\s*[- ]income|dti)\b", re.IGNORECASE),
        re.compile(r"\$?\s*[0-9][0-9,]*(?:\.\d+)?%?"),
    ),
    (re.compile(r"\bloan\s+type\b", re.IGNORECASE), re.compile(r"(?:conventional|fha|va|usda|rhs|fsa)", re.IGNORECASE)),
    (re.compile(r"\bloan\s+purpose\b", re.IGNORECASE), re.compile(r"(?:purchase|refinance|home[ _-]?improvement|other)", re.IGNORECASE)),
    (re.compile(r"\bincome\s+type\b", re.IGNORECASE), re.compile(r"(?:employment|self[ _-]?employment|retirement|other)", re.IGNORECASE)),
    (re.compile(r"\bproperty\s+type\b", re.IGNORECASE), re.compile(r"(?:single[ _-]?family|condominium|townhouse|multi[ _-]?unit)", re.IGNORECASE)),
    (re.compile(r"\boccupancy(?:\s+type)?\b", re.IGNORECASE), re.compile(r"(?:primary[ _-]?residence|second[ _-]?home|investment)", re.IGNORECASE)),
)


def _following_value_pattern(label_line: str) -> re.Pattern[str] | None:
    for label_pattern, value_pattern in _FOLLOWING_VALUE_PATTERNS:
        if label_pattern.search(label_line):
            return value_pattern
    return None


def sanitize_document_text(text: str) -> str:
    """Keep labeled fact lines while preserving safe source line positions.

    Discarded lines become empty placeholders. This preserves line-number
    provenance without passing unrelated or sensitive text to workers.
    """

    safe_lines: list[str] = []
    expected_value_pattern: re.Pattern[str] | None = None
    for line in text.splitlines():
        stripped = line.strip()
        if _ALLOWLISTED_FACT_LABELS.search(stripped):
            safe_lines.append(stripped)
            expected_value_pattern = _following_value_pattern(stripped)
        elif expected_value_pattern is not None and expected_value_pattern.fullmatch(stripped):
            safe_lines.append(stripped)
            expected_value_pattern = None
        else:
            safe_lines.append("")
            if stripped:
                expected_value_pattern = None
    return "\n".join(safe_lines) if any(safe_lines) else "[no_supported_labeled_fields]"


def _decode_base64(value: str) -> bytes:
    try:
        return base64.b64decode(value, validate=True)
    except (binascii.Error, ValueError) as exc:
        raise DocumentUploadError("document_base64_invalid") from exc


def _extract_pdf_text(binary: bytes) -> str:
    """Extract text from a validated PDF without retaining its bytes."""

    from pypdf import PdfReader

    reader = PdfReader(BytesIO(binary))
    return "\n".join(page.extract_text() or "" for page in reader.pages).strip()


def _extract_pdf_text_bounded(binary: bytes) -> str:
    """Bound PDF parsing so a slow decoder cannot hold an API request open."""

    executor = ThreadPoolExecutor(max_workers=1)
    timed_out = False
    future = executor.submit(_extract_pdf_text, binary)
    try:
        return future.result(timeout=PDF_EXTRACTION_TIMEOUT_SECONDS)
    except FutureTimeoutError as exc:
        timed_out = True
        future.cancel()
        raise DocumentUploadError("document_extraction_timeout") from exc
    except DocumentUploadError:
        raise
    except Exception as exc:
        raise DocumentUploadError("document_pdf_invalid") from exc
    finally:
        executor.shutdown(wait=not timed_out, cancel_futures=True)


def decode_document_upload(upload: SupportingDocumentInput, *, document_id: str) -> RuntimeDocument:
    """Validate extension/MIME/size and extract text without retaining binary data."""

    suffix = Path(upload.filename).suffix.lower()
    allowed_media_types = ALLOWED_DOCUMENT_TYPES.get(suffix)
    if allowed_media_types is None:
        raise DocumentUploadError("document_file_type_unsupported")
    if upload.media_type.lower() not in allowed_media_types:
        raise DocumentUploadError("document_media_type_mismatch")

    binary = _decode_base64(upload.content_base64)
    if not binary:
        raise DocumentUploadError("document_empty")
    if len(binary) > MAX_DOCUMENT_BYTES:
        raise DocumentUploadError("document_size_exceeded")

    if suffix == ".pdf":
        text = _extract_pdf_text_bounded(binary)
        extraction_method = "pdf_text"
    else:
        try:
            text = binary.decode("utf-8").strip()
        except UnicodeDecodeError as exc:
            raise DocumentUploadError("document_encoding_unsupported") from exc
        extraction_method = "utf8_text"
    if not text:
        raise DocumentUploadError("document_text_empty")
    safe_text = sanitize_document_text(text)

    return RuntimeDocument(
        document_id=document_id,
        label="USER_UPLOAD",
        filename=upload.filename,
        media_type=upload.media_type,
        size_bytes=len(binary),
        sha256=hashlib.sha256(binary).hexdigest(),
        extraction_method=extraction_method,
        content=safe_text,
    )


def describe_runtime_document(document: RuntimeDocument) -> DocumentDescriptor:
    """Return metadata only; document text is never sent to the browser."""

    return DocumentDescriptor(
        document_id=document.document_id,
        filename=document.filename,
        media_type=document.media_type,
        size_bytes=document.size_bytes,
        sha256=document.sha256,
        extraction_method=document.extraction_method,
    )
