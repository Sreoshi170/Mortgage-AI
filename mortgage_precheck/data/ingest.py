"""Streaming HMDA ingestion, quality auditing, and candidate feature preparation.

The module preserves raw source values and never edits source files. Numeric
parsing distinguishes blank/missing, HMDA special values such as ``NA`` and
``Exempt``, invalid text, and finite numeric values outside conservative
non-negative checks. It does not infer a target, collapse ``action_taken``,
convert income units, or recompute reported combined LTV.

The operational feature allowlist is a candidate schema only. It deliberately
excludes protected fields, geography/institution identifiers, ``action_taken``,
pricing fields, denial reasons, and derived fields whose timing is not locked.
The resulting features are not connected to the live application.
"""

from __future__ import annotations

import csv
import hashlib
import json
import math
import sys
from collections import Counter
from dataclasses import asdict, dataclass, field
from decimal import Decimal, InvalidOperation
from pathlib import Path
from typing import Any, Iterable, Iterator, Literal, Mapping, Sequence

csv.field_size_limit(sys.maxsize)

DEFAULT_REQUIRED_COLUMNS = frozenset(
    {
        "activity_year",
        "action_taken",
        "loan_type",
        "loan_purpose",
        "loan_amount",
        "combined_loan_to_value_ratio",
        "interest_rate",
        "rate_spread",
        "property_value",
        "occupancy_type",
        "income",
        "debt_to_income_ratio",
    }
)

# Candidate-only fields. Timing availability must be approved before any model
# or operational worker consumes them. These are the fields closest to an
# application record and exclude target, demographics, proxies, pricing, and
# post-processed/derived columns.
OPERATIONAL_FEATURE_ALLOWLIST = (
    "activity_year",
    "loan_type",
    "loan_purpose",
    "loan_amount",
    "property_value",
    "combined_loan_to_value_ratio",
    "occupancy_type",
    "income",
    "debt_to_income_ratio",
)

PROTECTED_OR_PROXY_FIELDS = frozenset(
    {
        "derived_ethnicity",
        "derived_race",
        "derived_sex",
        "applicant_ethnicity_1",
        "applicant_race_1",
        "applicant_sex",
        "co_applicant_ethnicity_1",
        "co_applicant_race_1",
        "co_applicant_sex",
        "applicant_age",
        "co_applicant_age",
        "ageapplicant",
        "lei",
        "state_code",
        "county_code",
        "census_tract",
        "derived_msa_md",
    }
)

LEAKAGE_OR_POST_OUTCOME_FIELDS = frozenset(
    {
        "action_taken",
        "rate_spread",
        "interest_rate",
        "denial_reason_1",
        "denial_reason_2",
        "denial_reason_3",
        "denial_reason_4",
        "derived_loan_product_type",
        "derived_dwelling_category",
    }
)

NUMERIC_FIELDS = (
    "loan_amount",
    "combined_loan_to_value_ratio",
    "interest_rate",
    "rate_spread",
    "property_value",
    "income",
    "debt_to_income_ratio",
)

# Official HMDA 2025 definitions identify DTI bins as meaningful values. They
# are retained as special values and are not coerced to arbitrary numbers.
DTI_BUCKETS = frozenset(
    {
        "<20%",
        "20%-<30%",
        "30%-<36%",
        "50%-60%",
        ">60%",
    }
    | {f"{value}%" for value in range(36, 50)}
)


class HmdaSchemaError(ValueError):
    """The input header cannot satisfy the declared schema contract."""


class EmptyInputError(ValueError):
    """The input has no header or no data rows."""


class RowWidthError(ValueError):
    """A row has a different number of fields than the header."""


ParseStatus = Literal["numeric", "missing", "special", "invalid", "out_of_range"]


@dataclass(frozen=True)
class ParsedNumeric:
    raw: str
    value: float | None
    status: ParseStatus
    special_code: str | None = None
    reason: str | None = None


@dataclass
class FieldQuality:
    rows: int = 0
    missing: int = 0
    special: int = 0
    special_values: Counter[str] = field(default_factory=Counter)
    invalid: int = 0
    out_of_range: int = 0

    def to_dict(self) -> dict[str, Any]:
        result = asdict(self)
        result["special_values"] = dict(self.special_values)
        result["rates"] = {
            key: (value / self.rows if self.rows else 0.0)
            for key, value in {
                "missing": self.missing,
                "special": self.special,
                "invalid": self.invalid,
                "out_of_range": self.out_of_range,
            }.items()
        }
        return result


@dataclass
class DataQualitySummary:
    input_path: str
    delimiter: str
    columns: list[str]
    required_columns: list[str]
    rows_inspected: int = 0
    chunks: int = 0
    row_width_errors: int = 0
    empty_input: bool = False
    field_quality: dict[str, FieldQuality] = field(default_factory=dict)
    notes: list[str] = field(default_factory=list)

    def to_dict(self) -> dict[str, Any]:
        return {
            "input_path": self.input_path,
            "delimiter": self.delimiter,
            "columns": self.columns,
            "required_columns": self.required_columns,
            "rows_inspected": self.rows_inspected,
            "chunks": self.chunks,
            "row_width_errors": self.row_width_errors,
            "empty_input": self.empty_input,
            "field_quality": {name: quality.to_dict() for name, quality in self.field_quality.items()},
            "operational_feature_allowlist": list(OPERATIONAL_FEATURE_ALLOWLIST),
            "excluded_protected_or_proxy_fields": sorted(PROTECTED_OR_PROXY_FIELDS),
            "excluded_leakage_or_post_outcome_fields": sorted(LEAKAGE_OR_POST_OUTCOME_FIELDS),
            "notes": self.notes,
        }


def detect_delimiter(path: str | Path, explicit: str | None = None) -> str:
    if explicit:
        if explicit not in {",", "|", "\t"}:
            raise ValueError("delimiter must be ',', '|', or tab")
        return explicit
    suffix = Path(path).suffix.lower()
    if suffix in {".txt", ".psv", ".pipe"}:
        return "|"
    return ","


def _read_header(path: Path, delimiter: str) -> list[str]:
    try:
        with path.open("r", encoding="utf-8-sig", newline="") as handle:
            row = next(csv.reader(handle, delimiter=delimiter), None)
    except FileNotFoundError as exc:
        raise FileNotFoundError(f"HMDA input file not found: {path}") from exc
    if not row:
        raise EmptyInputError(f"HMDA input has no header: {path}")
    header = [value.strip() for value in row]
    if any(not value for value in header):
        raise HmdaSchemaError("HMDA header contains an empty column name")
    if len(set(header)) != len(header):
        raise HmdaSchemaError("HMDA header contains duplicate column names")
    return header


def validate_required_columns(columns: Sequence[str], required: Iterable[str] = DEFAULT_REQUIRED_COLUMNS) -> None:
    missing = sorted(set(required) - set(columns))
    if missing:
        raise HmdaSchemaError(f"missing required HMDA columns: {', '.join(missing)}")


def iter_hmda_rows(
    path: str | Path,
    *,
    delimiter: str | None = None,
    required_columns: Iterable[str] = DEFAULT_REQUIRED_COLUMNS,
) -> Iterator[dict[str, str]]:
    """Yield rows without loading the entire file and without dropping malformed rows."""

    source = Path(path)
    resolved_delimiter = detect_delimiter(source, delimiter)
    header = _read_header(source, resolved_delimiter)
    validate_required_columns(header, required_columns)
    with source.open("r", encoding="utf-8-sig", newline="") as handle:
        reader = csv.reader(handle, delimiter=resolved_delimiter)
        next(reader, None)
        saw_row = False
        for row_number, values in enumerate(reader, start=2):
            saw_row = True
            if len(values) != len(header):
                raise RowWidthError(
                    f"row {row_number} has {len(values)} fields; expected {len(header)}"
                )
            yield dict(zip(header, values))
    if not saw_row:
        raise EmptyInputError(f"HMDA input has a header but no data rows: {source}")


def load_hmda_chunks(
    path: str | Path,
    *,
    chunk_size: int = 10_000,
    delimiter: str | None = None,
    required_columns: Iterable[str] = DEFAULT_REQUIRED_COLUMNS,
) -> Iterator[list[dict[str, str]]]:
    """Yield bounded row chunks for large CSV or pipe-delimited HMDA files."""

    if chunk_size < 1:
        raise ValueError("chunk_size must be at least 1")
    chunk: list[dict[str, str]] = []
    for row in iter_hmda_rows(path, delimiter=delimiter, required_columns=required_columns):
        chunk.append(row)
        if len(chunk) == chunk_size:
            yield chunk
            chunk = []
    if chunk:
        yield chunk


def parse_numeric(raw_value: object, *, field_name: str) -> ParsedNumeric:
    """Parse one HMDA numeric-like value while preserving source semantics."""

    raw = "" if raw_value is None else str(raw_value)
    stripped = raw.strip()
    if stripped == "":
        return ParsedNumeric(raw=raw, value=None, status="missing", reason="blank")
    if stripped in {"NA", "Exempt"}:
        return ParsedNumeric(raw=raw, value=None, status="special", special_code=stripped)
    if field_name == "debt_to_income_ratio" and stripped in DTI_BUCKETS:
        return ParsedNumeric(raw=raw, value=None, status="special", special_code=stripped)
    try:
        decimal_value = Decimal(stripped)
    except (InvalidOperation, ValueError):
        return ParsedNumeric(raw=raw, value=None, status="invalid", reason="not_numeric")
    if not decimal_value.is_finite():
        return ParsedNumeric(raw=raw, value=None, status="invalid", reason="not_finite")

    # These are conservative validity checks, not inferred HMDA upper limits.
    # Official documentation warns that loan amount and income have no upper
    # limit; therefore no arbitrary upper bound is imposed here.
    if field_name in {"loan_amount", "property_value", "combined_loan_to_value_ratio", "income", "debt_to_income_ratio"} and decimal_value < 0:
        return ParsedNumeric(raw=raw, value=float(decimal_value), status="out_of_range", reason="negative_value")
    if field_name == "interest_rate" and not Decimal("0") <= decimal_value <= Decimal("99.999"):
        return ParsedNumeric(raw=raw, value=float(decimal_value), status="out_of_range", reason="outside_percentage_range")
    return ParsedNumeric(raw=raw, value=float(decimal_value), status="numeric")


def _update_quality(quality: FieldQuality, parsed: ParsedNumeric) -> None:
    quality.rows += 1
    if parsed.status == "missing":
        quality.missing += 1
    elif parsed.status == "special":
        quality.special += 1
        quality.special_values[parsed.special_code or "unknown"] += 1
    elif parsed.status == "invalid":
        quality.invalid += 1
    elif parsed.status == "out_of_range":
        quality.out_of_range += 1


def quality_audit(
    path: str | Path,
    *,
    chunk_size: int = 10_000,
    delimiter: str | None = None,
    max_rows: int | None = None,
) -> DataQualitySummary:
    """Stream an HMDA file and return counts without altering any source data."""

    source = Path(path)
    resolved_delimiter = detect_delimiter(source, delimiter)
    columns = _read_header(source, resolved_delimiter)
    validate_required_columns(columns)
    summary = DataQualitySummary(
        input_path=str(source),
        delimiter=resolved_delimiter,
        columns=columns,
        required_columns=sorted(DEFAULT_REQUIRED_COLUMNS),
        field_quality={field_name: FieldQuality() for field_name in NUMERIC_FIELDS},
        notes=[
            "Source values are never overwritten or normalized in place.",
            "Income is preserved in the HMDA-reported unit: thousands of dollars; no conversion is applied.",
            "action_taken is preserved as an eight-code candidate outcome and is excluded from operational features.",
            "Reported combined_loan_to_value_ratio is preserved; no loan_amount/property_value ratio is substituted.",
            "Rows with invalid width raise RowWidthError rather than being silently dropped.",
        ],
    )
    rows_seen = 0
    try:
        for chunk in load_hmda_chunks(source, chunk_size=chunk_size, delimiter=resolved_delimiter):
            summary.chunks += 1
            for row in chunk:
                if max_rows is not None and rows_seen >= max_rows:
                    summary.rows_inspected = rows_seen
                    return summary
                rows_seen += 1
                for field_name in NUMERIC_FIELDS:
                    _update_quality(summary.field_quality[field_name], parse_numeric(row.get(field_name), field_name=field_name))
            if max_rows is not None and rows_seen >= max_rows:
                summary.rows_inspected = rows_seen
                return summary
    except EmptyInputError:
        summary.empty_input = True
        raise
    summary.rows_inspected = rows_seen
    if rows_seen == 0:
        summary.empty_input = True
        raise EmptyInputError(f"HMDA input has no data rows: {source}")
    return summary


def _feature_value(field_name: str, raw_value: str) -> Any:
    if field_name in NUMERIC_FIELDS:
        parsed = parse_numeric(raw_value, field_name=field_name)
        return parsed.value if parsed.status == "numeric" else None
    if field_name == "activity_year":
        try:
            return int(raw_value)
        except (TypeError, ValueError):
            return None
    return raw_value


def prepare_operational_features(row: Mapping[str, str]) -> dict[str, Any]:
    """Create a new candidate feature record from one source row.

    The original mapping is not mutated. Raw values and parse status are kept
    only for allowlisted fields, so protected/proxy/outcome fields cannot leak
    into this operational representation.
    """

    features: dict[str, Any] = {}
    raw_values: dict[str, str] = {}
    field_status: dict[str, str] = {}
    for field_name in OPERATIONAL_FEATURE_ALLOWLIST:
        raw = "" if row.get(field_name) is None else str(row.get(field_name))
        raw_values[field_name] = raw
        if field_name in NUMERIC_FIELDS:
            parsed = parse_numeric(raw, field_name=field_name)
            features[field_name] = parsed.value if parsed.status == "numeric" else None
            field_status[field_name] = parsed.status
        elif field_name == "activity_year":
            features[field_name] = _feature_value(field_name, raw)
            field_status[field_name] = "numeric" if features[field_name] is not None else "invalid"
        else:
            features[field_name] = raw
            field_status[field_name] = "missing" if raw.strip() == "" else "categorical"

    canonical = "\x1f".join(raw_values[name] for name in OPERATIONAL_FEATURE_ALLOWLIST).encode("utf-8")
    return {
        "source_row_hash": hashlib.sha256(canonical).hexdigest(),
        "features": features,
        "source_values": raw_values,
        "field_status": field_status,
    }


def _assert_output_path_is_separate(input_path: str | Path, output_path: str | Path) -> None:
    if Path(input_path).resolve() == Path(output_path).resolve():
        raise ValueError("derived output path must be different from the source input path")


def save_quality_report(summary: DataQualitySummary, output_path: str | Path) -> Path:
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary.to_dict(), indent=2, sort_keys=True) + "\n", encoding="utf-8")
    return output


def save_feature_jsonl(
    input_path: str | Path,
    output_path: str | Path,
    *,
    chunk_size: int = 10_000,
    delimiter: str | None = None,
    max_rows: int | None = None,
) -> int:
    """Write candidate features as separate JSONL; return rows written."""

    _assert_output_path_is_separate(input_path, output_path)
    output = Path(output_path)
    output.parent.mkdir(parents=True, exist_ok=True)
    rows_written = 0
    with output.open("w", encoding="utf-8", newline="\n") as handle:
        for chunk in load_hmda_chunks(input_path, chunk_size=chunk_size, delimiter=delimiter):
            for row in chunk:
                if max_rows is not None and rows_written >= max_rows:
                    return rows_written
                handle.write(json.dumps(prepare_operational_features(row), sort_keys=True) + "\n")
                rows_written += 1
    return rows_written
