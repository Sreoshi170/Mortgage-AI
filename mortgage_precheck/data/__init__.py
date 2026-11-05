"""Offline HMDA ingestion and feature-preparation utilities.

This package is intentionally not imported by the live FastAPI or LangGraph
recommendation path. It prepares reproducible, reviewable artifacts for a
future evaluation or training phase.
"""

from .ingest import (
    DEFAULT_REQUIRED_COLUMNS,
    OPERATIONAL_FEATURE_ALLOWLIST,
    DataQualitySummary,
    EmptyInputError,
    HmdaSchemaError,
    RowWidthError,
    iter_hmda_rows,
    load_hmda_chunks,
    parse_numeric,
    prepare_operational_features,
    quality_audit,
    save_feature_jsonl,
    save_quality_report,
)

__all__ = [
    "DEFAULT_REQUIRED_COLUMNS",
    "OPERATIONAL_FEATURE_ALLOWLIST",
    "DataQualitySummary",
    "EmptyInputError",
    "HmdaSchemaError",
    "RowWidthError",
    "iter_hmda_rows",
    "load_hmda_chunks",
    "parse_numeric",
    "prepare_operational_features",
    "quality_audit",
    "save_feature_jsonl",
    "save_quality_report",
]
