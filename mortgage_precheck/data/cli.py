"""Command line audit for the offline HMDA ingestion layer."""

from __future__ import annotations

import argparse
from pathlib import Path

from .ingest import quality_audit, save_feature_jsonl, save_quality_report


def main() -> None:
    parser = argparse.ArgumentParser(description="Audit an HMDA CSV/pipe-delimited file without changing it")
    parser.add_argument("--input", required=True, help="HMDA CSV or pipe-delimited input path")
    parser.add_argument("--report", required=True, help="Separate JSON quality-report output path")
    parser.add_argument("--features-output", help="Optional separate JSONL candidate-feature output path")
    parser.add_argument("--chunk-size", type=int, default=10_000)
    parser.add_argument("--max-rows", type=int, default=None, help="Optional bounded preview; omit for full scan")
    parser.add_argument("--delimiter", choices=[",", "|", "\t"], default=None)
    args = parser.parse_args()

    summary = quality_audit(
        args.input,
        chunk_size=args.chunk_size,
        delimiter=args.delimiter,
        max_rows=args.max_rows,
    )
    report_path = save_quality_report(summary, args.report)
    print(f"audited_input={Path(args.input)}")
    print(f"rows_inspected={summary.rows_inspected}")
    print(f"columns={len(summary.columns)}")
    print(f"quality_report={report_path}")
    if args.features_output:
        rows_written = save_feature_jsonl(
            args.input,
            args.features_output,
            chunk_size=args.chunk_size,
            delimiter=args.delimiter,
            max_rows=args.max_rows,
        )
        print(f"features_written={rows_written}")
        print(f"features_output={Path(args.features_output)}")


if __name__ == "__main__":
    main()
