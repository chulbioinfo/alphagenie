#!/usr/bin/env python3
"""Validate the published v0.24 comparison reports without reading private data.

The default report directory is docs/verification/v024. This command prints a
JSON acceptance result, changes no files, makes no provider calls, and exits
nonzero when any recorded criterion fails. It is not a fresh inference run.
"""
from __future__ import annotations

import argparse
import json
from pathlib import Path

try:
    from .cross_validation_checks import validate_recorded_reports
except ImportError:
    from cross_validation_checks import validate_recorded_reports


def reject_nonfinite(value: str):
    raise ValueError("JSON nonfinite numeric literal is not accepted")


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reports-dir", type=Path, default=Path(__file__).resolve().parents[1] / "docs/verification/v024")
    args = parser.parse_args(argv)
    try:
        reports = [json.loads((args.reports_dir / name).read_text(encoding="utf-8"), parse_constant=reject_nonfinite)
                   for name in ("all_contexts_report.json", "cohort_cross_validation_report.json", "curve_cross_validation_report.json")]
        result = validate_recorded_reports(*reports)
    except (OSError, ValueError):
        result = {"status": "failed", "errors": ["required_report_missing_or_invalid_json"], "provider_calls": 0, "offline": True}
    print(json.dumps(result, indent=2, allow_nan=False))
    return 0 if result["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
