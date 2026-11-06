"""Compare an independent numerical reproduction with the original 90 solves.

Only the standard library is used. All deterministic run JSON fields and every
trace CSV field are compared exactly, with elapsed_seconds excluded. This
utility never invokes a solver and writes only the requested verification JSON.
"""

from __future__ import annotations

import argparse
import csv
from itertools import zip_longest
import json
from pathlib import Path
import sys
from typing import Any


EXPECTED_RUNS = 90
REQUIRED_RUN_FIELDS = (
    "x0", "x_final", "f_value", "gradient_norm", "objective_gap", "nit",
    "nfev", "njev", "solver_success", "solver_status", "solver_message",
    "stationary", "global_hit",
)
EXCLUDED_FIELDS = {"elapsed_seconds"}
MAX_DIFFERENCE_DETAILS = 1000


class Differences:
    """Count every discrepancy while bounding detailed error-report size."""

    def __init__(self) -> None:
        self.count = 0
        self.details: list[dict[str, Any]] = []
        self.by_category: dict[str, int] = {}

    def add(self, category: str, **detail: Any) -> None:
        self.count += 1
        self.by_category[category] = self.by_category.get(category, 0) + 1
        if len(self.details) < MAX_DIFFERENCE_DETAILS:
            self.details.append({"category": category, **detail})


def _load_json(path: Path) -> Any:
    return json.loads(path.read_text(encoding="utf-8"))


def _compare_json_file(
    reference: Path,
    candidate: Path,
    relative: str,
    differences: Differences,
) -> bool:
    try:
        expected = _load_json(reference / relative)
        actual = _load_json(candidate / relative)
    except (OSError, ValueError) as exc:
        differences.add("input_json", file=relative, error=str(exc))
        return False
    if expected != actual:
        differences.add("input_json", file=relative, expected=expected, actual=actual)
        return False
    return True


def _compare_run(
    reference: Path,
    candidate: Path,
    name: str,
    differences: Differences,
) -> bool:
    before = differences.count
    relative = f"runs/{name}"
    try:
        expected = _load_json(reference / relative)
        actual = _load_json(candidate / relative)
    except (OSError, ValueError) as exc:
        differences.add("run_json", file=relative, error=str(exc))
        return False
    if not isinstance(expected, dict) or not isinstance(actual, dict):
        differences.add("run_json", file=relative, error="Run JSON must be an object.")
        return False
    for key in REQUIRED_RUN_FIELDS:
        if key not in expected or key not in actual:
            differences.add("run_json", file=relative, field=key,
                            error="A required outcome field is missing.")
    for key in sorted((set(expected) | set(actual)) - EXCLUDED_FIELDS):
        if key not in expected or key not in actual:
            differences.add("run_json", file=relative, field=key,
                            error="Field membership differs.")
        elif expected[key] != actual[key]:
            differences.add("run_json", file=relative, field=key,
                            expected=expected[key], actual=actual[key])
    return differences.count == before


def _compare_trace(
    reference: Path,
    candidate: Path,
    name: str,
    differences: Differences,
) -> tuple[bool, int]:
    before = differences.count
    compared_rows = 0
    relative = f"traces/{name}"
    missing = object()
    try:
        with (reference / relative).open(encoding="utf-8", newline="") as first:
            with (candidate / relative).open(encoding="utf-8", newline="") as second:
                expected_reader = csv.DictReader(first)
                actual_reader = csv.DictReader(second)
                expected_fields = set(expected_reader.fieldnames or ()) - EXCLUDED_FIELDS
                actual_fields = set(actual_reader.fieldnames or ()) - EXCLUDED_FIELDS
                if expected_fields != actual_fields:
                    differences.add("trace_csv", file=relative,
                                    error="Non-timing CSV columns differ.",
                                    expected=sorted(expected_fields), actual=sorted(actual_fields))
                for index, (expected, actual) in enumerate(
                    zip_longest(expected_reader, actual_reader, fillvalue=missing), 1
                ):
                    if expected is missing or actual is missing:
                        differences.add("trace_csv", file=relative, row=index,
                                        error="Trace row exists in only one study.")
                        continue
                    compared_rows += 1
                    expected = {key: value for key, value in expected.items()
                                if key not in EXCLUDED_FIELDS}
                    actual = {key: value for key, value in actual.items()
                              if key not in EXCLUDED_FIELDS}
                    if expected != actual:
                        changed = {
                            str(key): {"expected": expected.get(key), "actual": actual.get(key)}
                            for key in set(expected) | set(actual)
                            if key not in expected or key not in actual
                            or expected[key] != actual[key]
                        }
                        differences.add("trace_csv", file=relative, row=index, fields=changed)
    except (OSError, csv.Error) as exc:
        differences.add("trace_csv", file=relative, error=str(exc))
    return differences.count == before, compared_rows


def verify_reproduction(reference: Path, candidate: Path) -> dict[str, Any]:
    """Return a read-only exact comparison; do not write the report here."""
    reference = reference.resolve()
    candidate = candidate.resolve()
    if reference == candidate:
        raise ValueError("Reference and independent candidate must be different directories.")
    if not reference.is_dir() or not candidate.is_dir():
        raise ValueError("Both study directories must exist.")
    differences = Differences()
    environments = {}
    for label, directory in (("reference", reference), ("candidate", candidate)):
        try:
            metadata = _load_json(directory / "metadata.json")
            if (not isinstance(metadata, dict)
                    or metadata.get("execution_status") != "completed"
                    or metadata.get("completed_runs") != EXPECTED_RUNS):
                differences.add("completeness", study=label,
                                error="Metadata must declare 90 completed runs.")
            if isinstance(metadata, dict):
                environments[label] = {key: metadata.get(key) for key in ("python", "numpy", "scipy")}
        except (OSError, ValueError) as exc:
            differences.add("completeness", study=label, error=str(exc))

    initials_match = _compare_json_file(
        reference, candidate, "initial_points.json", differences
    )
    config_match = _compare_json_file(
        reference, candidate, "config_resolved.json", differences
    )
    reference_runs = {path.name for path in (reference / "runs").glob("*.json")}
    candidate_runs = {path.name for path in (candidate / "runs").glob("*.json")}
    for label, names in (("reference", reference_runs), ("candidate", candidate_runs)):
        if len(names) != EXPECTED_RUNS:
            differences.add("completeness", study=label, actual_run_files=len(names),
                            expected_run_files=EXPECTED_RUNS)
    if reference_runs != candidate_runs:
        differences.add("run_membership", missing=sorted(reference_runs - candidate_runs),
                        unexpected=sorted(candidate_runs - reference_runs))

    matching_runs = 0
    for name in sorted(reference_runs & candidate_runs):
        matching_runs += int(_compare_run(reference, candidate, name, differences))

    reference_traces = {path.name for path in (reference / "traces").glob("*.csv")}
    candidate_traces = {path.name for path in (candidate / "traces").glob("*.csv")}
    expected_trace_names = {Path(name).with_suffix(".csv").name for name in reference_runs}
    for label, names in (("reference", reference_traces), ("candidate", candidate_traces)):
        if names != expected_trace_names:
            differences.add("trace_membership", study=label,
                            missing=sorted(expected_trace_names - names),
                            unexpected=sorted(names - expected_trace_names))
    matching_traces = 0
    compared_trace_rows = 0
    for name in sorted(reference_traces & candidate_traces):
        matches, count = _compare_trace(reference, candidate, name, differences)
        matching_traces += int(matches)
        compared_trace_rows += count

    run_match = (len(reference_runs) == len(candidate_runs) == matching_runs == EXPECTED_RUNS
                 and reference_runs == candidate_runs)
    trace_match = (len(reference_traces) == len(candidate_traces) == matching_traces == EXPECTED_RUNS
                   and reference_traces == candidate_traces == expected_trace_names)
    return {
        "status": "passed" if differences.count == 0 else "failed",
        "comparison_mode": "exact; no numerical tolerances",
        "reference": str(reference), "candidate": str(candidate),
        "expected_runs": EXPECTED_RUNS,
        "reference_run_files": len(reference_runs),
        "candidate_run_files": len(candidate_runs),
        "run_files_compared": len(reference_runs & candidate_runs),
        "run_files_matching_exactly": matching_runs,
        "trace_files_compared": len(reference_traces & candidate_traces),
        "trace_files_matching_exactly": matching_traces,
        "trace_rows_compared": compared_trace_rows,
        "exact_run_outcomes_match": run_match,
        "exact_trace_fields_match": trace_match,
        "initial_points_match": initials_match,
        "resolved_config_match": config_match,
        "required_outcome_fields": list(REQUIRED_RUN_FIELDS),
        "run_field_policy": "All JSON fields except elapsed_seconds are compared.",
        "trace_field_policy": "All CSV row fields except elapsed_seconds are compared, including run_id.",
        "metadata_policy": "Completion is checked; paths, timestamps, and other metadata are excluded from exact equality.",
        "environment_context": environments,
        "solver_invoked": False,
        "difference_count": differences.count,
        "differences_by_category": differences.by_category,
        "difference_details": differences.details,
        "difference_details_truncated": differences.count > len(differences.details),
    }


def main(argv: list[str] | None = None) -> int:
    root = Path(__file__).resolve().parent.parent
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--reference", type=Path, default=root / "results" / "full_study")
    parser.add_argument("--candidate", type=Path, required=True)
    parser.add_argument("--output", type=Path,
                        default=root / "submission" / "reproduction_verification.json")
    args = parser.parse_args(argv)
    reference = args.reference.resolve()
    candidate = args.candidate.resolve()
    output = args.output.resolve()
    if output.is_relative_to(reference) or output.is_relative_to(candidate):
        parser.error("Verification output must be outside both study directories.")
    if reference == candidate:
        parser.error("Reference and candidate must be different directories.")
    try:
        report = verify_reproduction(reference, candidate)
    except (OSError, ValueError) as exc:
        report = {"status": "failed", "error": f"{type(exc).__name__}: {exc}",
                  "reference": str(reference), "candidate": str(candidate),
                  "solver_invoked": False}
    output.parent.mkdir(parents=True, exist_ok=True)
    output.write_text(json.dumps(report, ensure_ascii=False, indent=2,
                                 sort_keys=True, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({key: report[key] for key in (
        "status", "run_files_matching_exactly", "trace_files_matching_exactly",
        "trace_rows_compared", "difference_count", "error"
    ) if key in report}, indent=2))
    return 0 if report["status"] == "passed" else 1


if __name__ == "__main__":
    raise SystemExit(main())
