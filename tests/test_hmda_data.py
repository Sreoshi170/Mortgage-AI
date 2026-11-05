from __future__ import annotations

import csv
import json

import pytest

from mortgage_precheck.data.ingest import (
    DEFAULT_REQUIRED_COLUMNS,
    OPERATIONAL_FEATURE_ALLOWLIST,
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


HEADER = [
    "activity_year",
    "lei",
    "state_code",
    "county_code",
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
]


def write_fixture(path, rows, header=HEADER):
    with path.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=header, extrasaction="ignore")
        writer.writeheader()
        writer.writerows(rows)


def row(**overrides):
    value = {
        "activity_year": "2025",
        "lei": "institution-1",
        "state_code": "WI",
        "county_code": "55069",
        "action_taken": "1",
        "loan_type": "1",
        "loan_purpose": "1",
        "loan_amount": "250000",
        "combined_loan_to_value_ratio": "95.000",
        "interest_rate": "6.125",
        "rate_spread": "0.166",
        "property_value": "265000",
        "occupancy_type": "1",
        "income": "86",
        "debt_to_income_ratio": "41",
    }
    value.update(overrides)
    return value


def test_valid_file_loads_in_chunks_and_quality_audit_counts_rows(tmp_path):
    source = tmp_path / "hmda.csv"
    write_fixture(source, [row(), row(loan_amount="300000")])

    chunks = list(load_hmda_chunks(source, chunk_size=1))
    summary = quality_audit(source, chunk_size=1)

    assert len(chunks) == 2
    assert all(len(chunk) == 1 for chunk in chunks)
    assert summary.rows_inspected == 2
    assert summary.chunks == 2
    assert summary.columns == HEADER
    assert summary.field_quality["loan_amount"].invalid == 0

    bounded = quality_audit(source, chunk_size=1, max_rows=1)
    assert bounded.rows_inspected == 1
    assert bounded.chunks == 1


def test_pipe_delimited_hmda_text_is_supported(tmp_path):
    source = tmp_path / "hmda.txt"
    with source.open("w", newline="", encoding="utf-8") as handle:
        writer = csv.DictWriter(handle, fieldnames=HEADER, delimiter="|")
        writer.writeheader()
        writer.writerow(row())

    chunks = list(load_hmda_chunks(source, chunk_size=1))
    assert len(chunks) == 1
    assert chunks[0][0]["loan_amount"] == "250000"


def test_missing_required_columns_fail_closed(tmp_path):
    source = tmp_path / "missing.csv"
    write_fixture(source, [row()], header=["activity_year", "loan_amount"])

    with pytest.raises(HmdaSchemaError, match="missing required HMDA columns"):
        list(iter_hmda_rows(source))


def test_special_invalid_and_out_of_range_values_are_distinguished():
    assert parse_numeric("", field_name="income").status == "missing"
    assert parse_numeric("NA", field_name="income").special_code == "NA"
    assert parse_numeric("Exempt", field_name="income").special_code == "Exempt"
    assert parse_numeric(">60%", field_name="debt_to_income_ratio").special_code == ">60%"
    assert parse_numeric("not-a-number", field_name="income").status == "invalid"
    assert parse_numeric("-1", field_name="income").status == "out_of_range"


def test_quality_audit_preserves_special_invalid_and_range_counts(tmp_path):
    source = tmp_path / "quality.csv"
    write_fixture(
        source,
        [
            row(income="NA", debt_to_income_ratio="Exempt"),
            row(income="not-a-number", debt_to_income_ratio=">60%"),
            row(income="-1"),
        ],
    )

    summary = quality_audit(source)
    income = summary.field_quality["income"]
    dti = summary.field_quality["debt_to_income_ratio"]
    assert income.special_values["NA"] == 1
    assert income.invalid == 1
    assert income.out_of_range == 1
    assert dti.special_values["Exempt"] == 1
    assert dti.special_values[">60%"] == 1


def test_empty_input_and_bad_row_width_fail_without_silent_drop(tmp_path):
    empty = tmp_path / "empty.csv"
    empty.write_text(",".join(sorted(DEFAULT_REQUIRED_COLUMNS)) + "\n", encoding="utf-8")
    with pytest.raises(EmptyInputError):
        quality_audit(empty)

    malformed = tmp_path / "malformed.csv"
    malformed.write_text(",".join(HEADER) + "\n2025,only,two\n", encoding="utf-8")
    with pytest.raises(RowWidthError):
        list(iter_hmda_rows(malformed))


def test_feature_transform_is_reproducible_preserves_source_and_excludes_forbidden_fields(tmp_path):
    source_row = row(
        derived_race="Black",
        applicant_age="35-44",
        action_taken="3",
        rate_spread="0.2",
    )
    before = dict(source_row)

    first = prepare_operational_features(source_row)
    second = prepare_operational_features(source_row)

    assert first == second
    assert source_row == before
    assert set(first["features"]) == set(OPERATIONAL_FEATURE_ALLOWLIST)
    assert "action_taken" not in first["features"]
    assert "derived_race" not in first["features"]
    assert "state_code" not in first["features"]
    assert first["features"]["loan_amount"] == 250000.0
    assert first["field_status"]["income"] == "numeric"


def test_derived_outputs_are_separate_and_serializable(tmp_path):
    source = tmp_path / "hmda.csv"
    report = tmp_path / "report.json"
    features = tmp_path / "features.jsonl"
    write_fixture(source, [row()])

    summary = quality_audit(source)
    save_quality_report(summary, report)
    assert json.loads(report.read_text(encoding="utf-8"))["rows_inspected"] == 1
    assert save_feature_jsonl(source, features) == 1
    feature_record = json.loads(features.read_text(encoding="utf-8").strip())
    assert "action_taken" not in feature_record["features"]
    with pytest.raises(ValueError, match="different from the source"):
        save_feature_jsonl(source, source)
