"""Audit saved numerical experiments without running any solver.

Usage: python validate_study.py --results results/full_study
Reports default to audits/current_validation.json, outside reference results.
Saved-data integrity, source/EOL proof, and current environment matching are
reported separately. No historical result or metadata file is rewritten.
"""
from __future__ import annotations

import argparse
from collections import Counter
import csv
from datetime import datetime, timedelta, timezone
import hashlib
import itertools
import json
import math
import os
from pathlib import Path
import sys
from time import perf_counter
from typing import Any

from provenance_integrity import (
    compare_environment, environment_snapshot, inspect_source_file, scipy_source_path,
)


class Audit:
    def __init__(self) -> None:
        self.errors: list[str] = []
        self.warnings: list[str] = []
        self.checks: dict[str, bool] = {}
        self.assertions: Counter[str] = Counter()

    def check(self, condition: bool, category: str, message: str) -> None:
        self.assertions[category] += 1
        self.checks[category] = self.checks.get(category, True) and bool(condition)
        if not condition:
            self.errors.append(f"{category}: {message}")


def read_json(path: Path, audit: Audit) -> Any:
    try:
        return json.loads(path.read_text(encoding="utf-8-sig"))
    except (OSError, ValueError) as error:
        audit.check(False, "readable_artifacts", f"{path}: {error}")
        return None


def read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as stream:
        return list(csv.DictReader(stream))


def run_key(record: dict[str, Any]) -> tuple[str, int, int, str]:
    return (
        record["problem"], int(record["dimension"]),
        int(record["start_id"]), record["method"],
    )


def point_key(record: dict[str, Any]) -> tuple[str, int, int]:
    return record["problem"], int(record["dimension"]), int(record["start_id"])


def coordinates(event: dict[str, str], dimension: int) -> list[float]:
    return [float(event[f"x_{i}"]) for i in range(dimension)]


def independent_values(problem: str, x: list[float]) -> tuple[float, float, list[float]]:
    """Use plain scalar arithmetic, independently of the experiment functions."""
    if problem == "rosenbrock":
        value = sum(
            100 * (x[i + 1] - x[i] * x[i]) ** 2 + (1 - x[i]) ** 2
            for i in range(len(x) - 1)
        )
        gradient = [0.0] * len(x)
        for i in range(len(x) - 1):
            residual = x[i + 1] - x[i] * x[i]
            gradient[i] += -400 * x[i] * residual + 2 * (x[i] - 1)
            gradient[i + 1] += 200 * residual
    elif problem == "rastrigin":
        value = sum(xi * xi + 20 * math.sin(math.pi * xi) ** 2 for xi in x)
        gradient = [2 * xi + 20 * math.pi * math.sin(2 * math.pi * xi) for xi in x]
    else:
        raise ValueError(f"No independent formula for {problem!r}")
    return value, math.sqrt(sum(gi * gi for gi in gradient)), gradient


def validate_trace(
    run: dict[str, Any], path: Path, config: dict[str, Any], audit: Audit
) -> tuple[int, int, dict[str, Any] | None]:
    trace = read_csv(path)
    rid, dimension = run["run_id"], int(run["dimension"])
    category = "trace_protocol"
    audit.check(bool(trace), category, f"{rid}: empty trace")
    if not trace:
        return 0, 0, None
    accepted = [event for event in trace if event["event_type"] == "accepted"]
    audit.check(
        len(trace) == run["trace_events"] == run["nit"] + 2,
        category, f"{rid}: expected initial + accepted updates + terminal",
    )
    audit.check(
        trace[0]["event_type"] == "initial" and trace[-1]["event_type"] == "terminal",
        category, f"{rid}: event boundaries",
    )
    audit.check(
        len(accepted) == run["nit"]
        and [int(event["iteration"]) for event in accepted]
        == list(range(1, run["nit"] + 1)),
        category, f"{rid}: accepted iterations versus nit",
    )
    audit.check(
        int(trace[0]["iteration"]) == int(trace[0]["nfev"]) == int(trace[0]["njev"]) == 0,
        category, f"{rid}: initial counters",
    )
    audit.check(
        coordinates(trace[0], dimension) == run["x0"]
        and coordinates(trace[-1], dimension) == run["x_final"],
        category, f"{rid}: endpoint coordinates",
    )
    for field in ("nfev", "njev"):
        audit.check(int(trace[-1][field]) == run[field], category, f"{rid}: terminal {field}")
    audit.check(
        int(trace[-1]["iteration"]) == run["nit"],
        category, f"{rid}: terminal must not add an update",
    )
    for field in ("f_value", "gradient_norm", "objective_gap"):
        audit.check(float(trace[-1][field]) == run[field], category, f"{rid}: terminal {field}")
    previous = None
    for index, event in enumerate(trace):
        identity = (
            event["run_id"] == rid and run_key(event) == run_key(run)
        )
        audit.check(identity, category, f"{rid}: identity at event {index}")
        audit.check(
            event["event_type"] in {"initial", "accepted", "terminal"},
            category, f"{rid}: unknown event type at event {index}",
        )
        audit.check(
            all(math.isfinite(float(event[field])) for field in (
                "f_value", "gradient_norm", "objective_gap", "elapsed_seconds"
            )) and all(math.isfinite(xi) for xi in coordinates(event, dimension)),
            category, f"{rid}: nonfinite trace value at event {index}",
        )
        audit.check(
            int(event["nfev"]) >= 0 and int(event["njev"]) >= 0
            and float(event["elapsed_seconds"]) >= 0,
            category, f"{rid}: negative counter/time at event {index}",
        )
        if previous is not None:
            audit.check(
                all(float(event[field]) >= float(previous[field])
                    for field in ("nfev", "njev", "elapsed_seconds")),
                category, f"{rid}: nonmonotone counters/time at event {index}",
            )
        previous = event
    audit.check(
        math.isfinite(run["elapsed_seconds"])
        and run["elapsed_seconds"] >= float(trace[-1]["elapsed_seconds"]),
        category, f"{rid}: total measured time precedes terminal record",
    )

    if run["method"] == "GD":
        previous = trace[0]
        for index, event in enumerate(accepted):
            trials, reductions = int(event["line_search_trials"]), int(event["backtracks"])
            alpha = float(event["step_size"])
            audit.check(
                trials == reductions + 1 and reductions >= 0
                and 0 < alpha <= config["alpha0"]
                and math.isclose(
                    alpha, config["alpha0"] * config["backtrack_factor"] ** reductions,
                    rel_tol=1e-13, abs_tol=0.0,
                ),
                "gd_armijo_and_budget", f"{rid}: trial/step fields at update {index + 1}",
            )
            before_x = coordinates(previous, dimension)
            after_x = coordinates(event, dimension)
            _, _, before_gradient = independent_values(run["problem"], before_x)
            audit.check(
                all(math.isclose(new, old - alpha * gi, rel_tol=1e-12, abs_tol=1e-12)
                    for old, new, gi in zip(before_x, after_x, before_gradient)),
                "gd_armijo_and_budget", f"{rid}: negative-gradient update at step {index + 1}",
            )
            audit.check(
                int(event["nfev"]) - int(previous["nfev"])
                == trials + (1 if index == 0 else 0)
                and int(event["njev"]) == index + 2,
                "gd_armijo_and_budget", f"{rid}: evaluation budget at update {index + 1}",
            )
            before, after = float(previous["f_value"]), float(event["f_value"])
            norm = float(previous["gradient_norm"])
            tolerance = 1e-10 * max(1.0, abs(before))
            audit.check(
                after <= before - config["c1"] * alpha * norm * norm + tolerance,
                "gd_armijo_and_budget", f"{rid}: sufficient decrease at update {index + 1}",
            )
            previous = event

    extra = None
    if accepted:
        last = accepted[-1]
        extra_f = run["nfev"] - int(last["nfev"])
        extra_g = run["njev"] - int(last["njev"])
        if extra_f or extra_g:
            extra = {
                "run_id": rid, "additional_nfev": extra_f,
                "additional_njev": extra_g, "solver_status": run["solver_status"],
            }
    return len(trace), len(accepted), extra


def source_hash_checks(metadata: dict[str, Any], project: Path) -> dict[str, Any]:
    """Check trusted historical raw hashes, allowing only proven EOL changes."""
    project = project.resolve()
    results, errors = {}, []
    recorded = metadata.get("source_sha256", {})
    if not isinstance(recorded, dict) or not recorded:
        errors.append("Metadata has no valid recorded project source hashes.")
        recorded = {}
    # Deliberately do not require subsequently added analysis/validator files.
    for name, expected in recorded.items():
        path = (project / name).resolve()
        if not path.is_relative_to(project):
            results[name] = {
                "path": str(path), "passed": False, "match_kind": "path_outside_project",
                "expected_raw_sha256": expected, "actual_raw_sha256": None,
                "errors": ["Recorded source path resolves outside the project."],
            }
        else:
            results[name] = inspect_source_file(path, expected)
        errors.extend(f"{name}: {message}" for message in results[name]["errors"])
    expected = metadata.get("scipy_optimize_source_sha256")
    path = scipy_source_path()
    if path is None:
        results["scipy.optimize._optimize"] = {
            "path": None, "passed": False, "match_kind": "missing_or_unreadable",
            "expected_raw_sha256": expected, "actual_raw_sha256": None,
            "errors": ["Installed SciPy optimize Python source could not be located."],
        }
    else:
        results["scipy.optimize._optimize"] = inspect_source_file(path, expected)
    errors.extend("scipy.optimize._optimize: " + message
                  for message in results["scipy.optimize._optimize"]["errors"])
    exact = sum(record.get("match_kind") == "byte_exact" for record in results.values())
    equivalent = sum(record.get("match_kind") == "eol_equivalent" for record in results.values())
    return {
        "passed": not errors, "files": results, "errors": errors,
        "recorded_project_files": len(recorded), "byte_exact_files": exact,
        "eol_equivalent_files": equivalent,
        "raw_hash_mismatches": sum(record.get("raw_comparison", {}).get("matches") is not True
                                   for record in results.values()),
        "policy": "Historical raw digests remain authoritative. Raw exact takes priority. Otherwise only LF/CRLF reconstructions of actual bytes whose SHA-256 equals a recorded raw digest are accepted; bare CR fallback and actual code edits are rejected.",
    }


def validate_data(results_dir: Path, project: Path) -> dict[str, Any]:
    """Audit saved data independently of current source or environment status."""
    audit = Audit()
    report: dict[str, Any] = {
        "schema_version": 1,
        "validated_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "timezone": "Asia/Shanghai",
        "results_directory": str(results_dir),
        "validator_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "counts": {},
    }
    metadata = read_json(results_dir / "metadata.json", audit)
    config = read_json(results_dir / "config_resolved.json", audit)
    initials = read_json(results_dir / "initial_points.json", audit)
    gradient_checks = read_json(results_dir / "gradient_checks.json", audit)
    if not isinstance(metadata, dict) or not isinstance(config, dict):
        audit.check(False, "readable_artifacts", "metadata/config must be JSON objects")
        report.update(passed=False, checks=audit.checks, errors=audit.errors, warnings=audit.warnings)
        return report

    try:
        rows = read_csv(results_dir / "summary.csv")
        expected = set(itertools.product(
            config["functions"], config["dimensions"],
            range(1, config["starts_per_case"] + 1), config["methods"],
        ))
        json_files = {path.stem: path for path in (results_dir / "runs").glob("*.json")}
        trace_files = {path.stem: path for path in (results_dir / "traces").glob("*.csv")}
        runs = {name: read_json(path, audit) for name, path in json_files.items()}
        runs = {name: run for name, run in runs.items() if isinstance(run, dict)}
        ids = {row["run_id"] for row in rows}
        audit.check(
            len(rows) == len(ids) == len(runs) == len(trace_files) == len(expected),
            "study_coverage", "summary/JSON/trace counts or unique run IDs differ",
        )
        audit.check(
            ids == set(runs) == set(trace_files)
            and set(map(run_key, rows)) == set(map(run_key, runs.values())) == expected,
            "study_coverage", "files do not cover the full configured Cartesian product",
        )
        audit.check(
            metadata.get("execution_status") == "completed"
            and metadata.get("completed_runs") == metadata.get("expected_runs") == len(expected),
            "study_coverage", "completion metadata does not match the configured study",
        )
        point_map = {point_key(record): record["x0"] for record in initials}
        expected_points = {(name, dimension, start) for name, dimension, start, _ in expected}
        audit.check(
            len(initials) == len(point_map) == len(expected_points)
            and set(point_map) == expected_points,
            "paired_initial_points", "initial point coverage/uniqueness",
        )
        report["counts"].update(
            expected_runs=len(expected), summary_rows=len(rows), run_json_files=len(json_files),
            trace_csv_files=len(trace_files), expected_initial_points=len(expected_points),
            initial_points=len(point_map), trace_events=0, accepted_updates=0,
        )
    except (OSError, KeyError, TypeError, ValueError) as error:
        audit.check(False, "readable_artifacts", f"invalid study structure: {error}")
        report.update(passed=False, checks=audit.checks, errors=audit.errors, warnings=audit.warnings)
        return report

    flags: Counter[tuple[bool, bool, bool]] = Counter()
    statuses: Counter[tuple[str, int, str]] = Counter()
    extra_terminal = []
    unsuccessful = []
    for row in rows:
        rid = row["run_id"]
        try:
            run = runs[rid]
            point = point_map[point_key(run)]
            low, high = config["initial_ranges"][run["problem"]]
            audit.check(
                run["x0"] == point and len(point) == run["dimension"]
                and len(run["x_final"]) == run["dimension"]
                and all(low <= xi <= high for xi in point),
                "paired_initial_points", f"{rid}: initial point, range, or dimension",
            )
            audit.check(
                run["config"] == config["solver"],
                "summary_consistency", f"{rid}: solver configuration differs",
            )
            for field in ("nit", "nfev", "njev", "reported_nfev", "reported_njev", "trace_events", "solver_status"):
                audit.check(int(row[field]) == run[field], "summary_consistency", f"{rid}: CSV/JSON {field}")
            for field in ("solver_success", "stationary", "global_hit", "finite_result", "counter_consistent", "trace_consistent"):
                audit.check(
                    row[field] in {"True", "False"}
                    and (row[field] == "True") == run[field],
                    "summary_consistency", f"{rid}: CSV/JSON {field}",
                )
            for field in ("f_value", "gradient_norm", "objective_gap", "elapsed_seconds"):
                audit.check(float(row[field]) == run[field], "summary_consistency", f"{rid}: CSV/JSON {field}")
            audit.check(
                json.loads(row["x0"]) == run["x0"]
                and json.loads(row["x_final"]) == run["x_final"]
                and row["solver_message"] == run["solver_message"],
                "summary_consistency", f"{rid}: CSV/JSON coordinates or message",
            )
            audit.check(
                run["nfev"] == run["reported_nfev"]
                and run["njev"] == run["reported_njev"]
                and 0 <= run["nit"] <= config["solver"]["maxiter"]
                and run["counter_consistent"] and run["trace_consistent"],
                "native_evaluation_counts", f"{rid}: native/wrapper counts or flags",
            )
            event_count, accepted_count, extra = validate_trace(
                run, trace_files[rid], config["solver"], audit
            )
            report["counts"]["trace_events"] += event_count
            report["counts"]["accepted_updates"] += accepted_count
            if extra:
                extra_terminal.append(extra)

            value, norm, _ = independent_values(run["problem"], run["x_final"])
            audit.check(
                math.isclose(value, run["f_value"], rel_tol=1e-11, abs_tol=1e-12)
                and math.isclose(norm, run["gradient_norm"], rel_tol=1e-9, abs_tol=2e-10)
                and math.isclose(run["objective_gap"], run["f_value"], rel_tol=1e-12, abs_tol=1e-14),
                "independent_final_diagnostics", f"{rid}: independent value/gradient/gap",
            )
            finite = (
                math.isfinite(run["f_value"]) and math.isfinite(run["gradient_norm"])
                and all(math.isfinite(xi) for xi in run["x_final"])
            )
            audit.check(
                run["finite_result"] == finite
                and run["stationary"] == (finite and run["gradient_norm"] <= config["solver"]["gtol"])
                and run["global_hit"] == (finite and abs(run["objective_gap"]) <= config["solver"]["global_tolerance"]),
                "result_classifications", f"{rid}: finite/stationary/global target labels",
            )
            flags[(run["solver_success"], run["stationary"], run["global_hit"])] += 1
            statuses[(run["method"], run["solver_status"], run["solver_message"])] += 1
            if not run["solver_success"]:
                unsuccessful.append({field: run[field] for field in (
                    "run_id", "solver_status", "solver_message", "nit", "nfev", "njev",
                    "f_value", "gradient_norm", "stationary", "global_hit",
                )})
        except (OSError, KeyError, TypeError, ValueError, OverflowError) as error:
            audit.check(False, "readable_artifacts", f"{rid}: {error}")

    expected_gradient_cases = Counter({
        (name, dimension): 2 for name in config["functions"] for dimension in config["dimensions"]
    })
    try:
        audit.check(
            Counter((record["objective"], record["dimension"]) for record in gradient_checks)
            == expected_gradient_cases and all(record["passed"] for record in gradient_checks),
            "gradient_checks", "expected two passing checks per function/dimension",
        )
        report["counts"]["gradient_checks"] = len(gradient_checks)
        report["counts"]["gradient_checks_passed"] = sum(bool(record["passed"]) for record in gradient_checks)
    except (KeyError, TypeError) as error:
        audit.check(False, "gradient_checks", str(error))

    demo_path = results_dir.parent / "demo_2d" / "initial_points.json"
    report["demo_initial_points"] = {"available": demo_path.is_file(), "matched": 0}
    if demo_path.is_file():
        demo = read_json(demo_path, audit)
        try:
            demo_2d = [record for record in demo if int(record["dimension"]) == 2]
            matches = sum(point_map.get(point_key(record)) == record["x0"] for record in demo_2d)
            audit.check(matches == len(demo_2d), "demo_subset", "2-D demo initial points differ")
            report["demo_initial_points"].update(path=str(demo_path), compared=len(demo_2d), matched=matches)
        except (KeyError, TypeError, ValueError) as error:
            audit.check(False, "demo_subset", str(error))
    report["result_label_totals"] = {
        "solver_success": sum(count for (success, _, _), count in flags.items() if success),
        "stationary": sum(count for (_, stationary, _), count in flags.items() if stationary),
        "global_hit": sum(count for (_, _, global_hit), count in flags.items() if global_hit),
    }
    report["result_label_combinations"] = [
        {"solver_success": values[0], "stationary": values[1], "global_hit": values[2], "count": count}
        for values, count in sorted(flags.items())
    ]
    report["termination_counts"] = [
        {"method": values[0], "solver_status": values[1], "solver_message": values[2], "count": count}
        for values, count in sorted(statuses.items())
    ]
    report["extra_terminal_evaluations"] = extra_terminal
    report["unsuccessful_solver_runs"] = unsuccessful
    report.update(
        passed=not audit.errors, checks=audit.checks,
        assertions=dict(audit.assertions), errors=audit.errors, warnings=audit.warnings,
    )
    return report


def validate(results_dir: Path, project: Path) -> dict[str, Any]:
    started = datetime.now(timezone(timedelta(hours=8)))
    tick = perf_counter()
    data = validate_data(results_dir, project)
    try:
        metadata = json.loads((results_dir / "metadata.json").read_text(encoding="utf-8-sig"))
        if not isinstance(metadata, dict):
            raise ValueError("Historical metadata must be a JSON object.")
    except (OSError, ValueError) as error:
        metadata = {}
        metadata_error = str(error)
    else:
        metadata_error = None
    source = source_hash_checks(metadata, project)
    environment = compare_environment(metadata, environment_snapshot())
    if metadata_error:
        source["errors"].insert(0, "Cannot load trusted historical metadata: " + metadata_error)
        source["passed"] = False
    errors = ["data_internal_integrity: " + error for error in data["errors"]]
    errors.extend("source_integrity: " + error for error in source["errors"])
    errors.extend("environment_match: " + error for error in environment["errors"])
    finished = datetime.now(timezone(timedelta(hours=8)))
    return {
        "schema_version": 2,
        "passed": data["passed"] and source["passed"] and environment["passed"],
        "results_directory": str(results_dir),
        "validation_scope": {
            "solver_invoked": False, "reference_results_written": False,
            "historical_experiment_started_at": metadata.get("started_at"),
            "interpretation": "Saved-data consistency, historical source identity/EOL proof, and required current software versions are independent checks. Passing is not a new numerical rerun or a timing-reproduction claim.",
        },
        "time_scope": {
            "started_at": started.isoformat(), "finished_at": finished.isoformat(),
            "timezone": "Asia/Shanghai", "elapsed_seconds": perf_counter() - tick,
            "measures": "This read-only validation execution; excludes any solver execution.",
        },
        "validator_source_sha256": hashlib.sha256(Path(__file__).read_bytes()).hexdigest(),
        "provenance_helper_sha256": hashlib.sha256(
            (Path(__file__).resolve().parent / "provenance_integrity.py").read_bytes()
        ).hexdigest(),
        "data_internal_integrity": data,
        "source_integrity": source,
        "environment_match": environment,
        "counts": data.get("counts", {}),
        "result_label_totals": data.get("result_label_totals", {}),
        "errors": errors,
        "warnings": data.get("warnings", []),
    }


def check_output_destination(destination: Path, results_dir: Path, project: Path) -> Path:
    """Keep current audit output out of all reference/source trees."""
    destination, results_dir, project = destination.resolve(), results_dir.resolve(), project.resolve()
    if destination.suffix.lower() != ".json":
        raise ValueError("Validation output must be a separate .json audit file.")
    if destination.is_relative_to(results_dir) or any(part.lower() == "results" for part in destination.parts):
        raise ValueError("Refusing to write validation output inside reference/results directories.")
    for directory in ("cpu_optimization", "tests", "configs", "paper_source", ".venv"):
        if destination.is_relative_to(project / directory):
            raise ValueError(f"Refusing to overwrite a protected source/config tree: {directory}")
    if destination.is_dir():
        raise ValueError("Validation output must be a file, not a directory.")
    return destination


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("results/full_study"))
    parser.add_argument("--output", type=Path, default=Path("audits/current_validation.json"),
                        help="Separate current audit JSON; reference/results trees are forbidden")
    args = parser.parse_args(argv)
    project = Path(__file__).resolve().parent
    results_dir = args.results.resolve()
    if not results_dir.is_dir():
        parser.error(f"results directory does not exist: {results_dir}")
    try:
        destination = check_output_destination(args.output, results_dir, project)
    except ValueError as error:
        parser.error(str(error))
    report = validate(results_dir, project)
    destination.parent.mkdir(parents=True, exist_ok=True)
    temporary = destination.with_name(destination.name + ".tmp")
    temporary.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    os.replace(temporary, destination)
    print(json.dumps({
        "passed": report["passed"], "validation_file": str(destination),
        "data_internal_integrity": report["data_internal_integrity"]["passed"],
        "source_integrity": report["source_integrity"]["passed"],
        "environment_match": report["environment_match"]["passed"],
        "counts": report["counts"], "result_label_totals": report.get("result_label_totals", {}),
        "errors": report["errors"],
    }, ensure_ascii=False, indent=2))
    return 0 if report["passed"] else 1


if __name__ == "__main__":
    sys.exit(main())
