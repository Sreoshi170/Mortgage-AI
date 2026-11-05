"""CLI for the Phase 4 target/feature design audit; never trains a model."""

from __future__ import annotations

import argparse
import json
from collections import Counter, defaultdict
from pathlib import Path
from typing import Any

from mortgage_precheck.data.ingest import iter_hmda_rows

from .prepare import prepare_baseline_row
from .spec import (
    GROUP_COLUMN,
    MODEL_SPEC_VERSION,
    PROPOSED_FEATURES,
    SPLIT_RATIOS,
    SPLIT_SEED,
)
from .splitting import assign_split_from_row
from .target import construct_candidate_target


def build_summary(input_path: str | Path, *, delimiter: str | None = None, chunk_size: int = 50_000, max_rows: int | None = None) -> dict[str, Any]:
    """Stream a source and summarize eligible target rows and candidate fields."""

    del chunk_size  # iter_hmda_rows is streaming; the argument remains a CLI compatibility control.
    action_counts: Counter[str] = Counter()
    excluded_counts: Counter[str] = Counter()
    split_rows: Counter[str] = Counter()
    split_groups: dict[str, set[str]] = defaultdict(set)
    feature_status_counts: dict[str, Counter[str]] = {name: Counter() for name in PROPOSED_FEATURES}
    total = eligible = positive = negative = 0
    columns: list[str] = []
    complete_scan = True
    for row_number, row in enumerate(iter_hmda_rows(input_path, delimiter=delimiter), start=1):
        if not columns:
            columns = list(row.keys())
        if max_rows is not None and row_number > max_rows:
            complete_scan = False
            break
        total += 1
        target = construct_candidate_target(row.get("action_taken"))
        action_counts[target.raw_code or "<missing>"] += 1
        if not target.included:
            excluded_counts[target.raw_code or "<missing>"] += 1
            continue
        eligible += 1
        positive += int(target.target == 1)
        negative += int(target.target == 0)
        prepared = prepare_baseline_row(row)
        for name, status in prepared["field_status"].items():
            feature_status_counts[name][status] += 1
        split = assign_split_from_row(row, group_column=GROUP_COLUMN, seed=SPLIT_SEED, ratios=SPLIT_RATIOS)
        split_rows[split] += 1
        group = str(row.get(GROUP_COLUMN) or "<missing_group>").strip() or "<missing_group>"
        split_groups[split].add(group)
    return {
        "spec_version": MODEL_SPEC_VERSION,
        "input_path": str(Path(input_path)),
        "columns_inspected": columns,
        "rows_inspected": total,
        "complete_scan": complete_scan,
        "training_performed": False,
        "target": {
            "column": "action_taken",
            "positive_code": "1",
            "negative_code": "3",
            "positive_rows": positive,
            "negative_rows": negative,
            "eligible_rows": eligible,
            "positive_prevalence": (positive / eligible) if eligible else None,
            "excluded_rows": total - eligible,
            "action_code_counts": dict(action_counts),
            "excluded_action_code_counts": dict(excluded_counts),
        },
        "proposed_features": list(PROPOSED_FEATURES),
        "eligible_feature_status_counts": {name: dict(counts) for name, counts in feature_status_counts.items()},
        "split": {
            "strategy": "deterministic_institution_group_holdout",
            "group_column": GROUP_COLUMN,
            "seed": SPLIT_SEED,
            "ratios": SPLIT_RATIOS,
            "eligible_rows_by_split": dict(split_rows),
            "distinct_groups_by_split": {name: len(groups) for name, groups in split_groups.items()},
        },
        "limitations": [
            "This report is a design audit; it does not fit or evaluate a model.",
            "Raw LEI values are used only in memory for grouping and are not written to the report.",
            "No application-level identifier is available, so cross-institution related records cannot be fully detected.",
        ],
    }


def main() -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--input", required=True, help="HMDA CSV or pipe-delimited input path")
    parser.add_argument("--output", default="reports/modeling/phase4_target_feature_summary.json")
    parser.add_argument("--delimiter", choices=[",", "|", "\\t"])
    parser.add_argument("--chunk-size", type=int, default=50_000, help="Reserved for consistent streaming CLI usage")
    parser.add_argument("--max-rows", type=int)
    args = parser.parse_args()
    delimiter = "\t" if args.delimiter == "\\t" else args.delimiter
    summary = build_summary(args.input, delimiter=delimiter, chunk_size=args.chunk_size, max_rows=args.max_rows)
    output = Path(args.output)
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(summary, indent=2, sort_keys=True) + "\n", encoding="utf-8")
    print(json.dumps({"output": str(output), "rows_inspected": summary["rows_inspected"], "complete_scan": summary["complete_scan"], "training_performed": False}, indent=2))
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
