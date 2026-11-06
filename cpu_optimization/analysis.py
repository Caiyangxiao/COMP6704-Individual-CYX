"""Offline study aggregation; never call or modify any solver."""
from __future__ import annotations

from collections import Counter, defaultdict
from hashlib import sha256
from itertools import combinations
from pathlib import Path
import csv
import json
import math

import numpy as np
import scipy
from scipy.optimize import rosen_hess

from .experiment import write_json


METRICS = ("f_value", "objective_gap", "gradient_norm", "nit", "nfev", "njev", "elapsed_seconds")
BOOLS = ("solver_success", "stationary", "global_hit", "finite_result",
         "counter_consistent", "trace_consistent")
METHODS = ("GD", "CG", "BFGS")


def read_summary(path: Path) -> list[dict]:
    with Path(path).open(encoding="utf-8", newline="") as handle:
        rows = list(csv.DictReader(handle))
    for row in rows:
        for key in METRICS:
            row[key] = float(row[key])
        for key in ("dimension", "start_id", "solver_status", "reported_nfev", "reported_njev", "trace_events"):
            row[key] = int(row[key])
        for key in BOOLS:
            if row[key] not in {"True", "False"}:
                raise ValueError(f"Invalid boolean in {path}: {key}={row[key]}")
            row[key] = row[key] == "True"
        row["x0"] = json.loads(row["x0"])
        row["x_final"] = json.loads(row["x_final"])
    return rows


def _write_csv(path: Path, rows: list[dict]) -> None:
    if not rows:
        return
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=list(rows[0]))
        writer.writeheader()
        writer.writerows(rows)


def aggregate(rows: list[dict]) -> list[dict]:
    """Include all runs in medians/ranges; report endpoint quality separately."""
    groups = defaultdict(list)
    for row in rows:
        groups[(row["problem"], row["dimension"], row["method"])].append(row)
    result = []
    for (problem, dimension, method), members in sorted(groups.items(),
            key=lambda item: (item[0][0], item[0][1], METHODS.index(item[0][2]))):
        item = {"problem": problem, "dimension": dimension, "method": method,
                "n": len(members), "solver_success_count": sum(r["solver_success"] for r in members),
                "stationary_count": sum(r["stationary"] for r in members),
                "global_hit_count": sum(r["global_hit"] for r in members),
                "stationary_non_global_count": sum(r["stationary"] and not r["global_hit"] for r in members),
                "nonstationary_count": sum(not r["stationary"] for r in members)}
        for metric in METRICS:
            values = np.asarray([r[metric] for r in members], dtype=float)
            finite = values[np.isfinite(values)]
            item[f"{metric}_finite_count"] = len(finite)
            for suffix, func in (("median", np.median), ("min", np.min), ("max", np.max)):
                item[f"{metric}_{suffix}"] = float(func(finite)) if finite.size else None
        result.append(item)
    return result


def _termination_category(row: dict) -> str:
    if row["solver_status"] == 1:
        return "iteration_limit"
    if row["solver_status"] == 2:
        return "scipy_precision_loss_or_line_search" if row["method"] != "GD" else "armijo_search_failure"
    if row["solver_status"] == 3 or not row["finite_result"]:
        return "nonfinite"
    if row["solver_status"] == 4:
        return "numerical_stagnation"
    if row["stationary"]:
        return "stationary_global_target" if row["global_hit"] else "stationary_non_global"
    return "other_termination"


def _read_trace(path: Path) -> list[dict]:
    with path.open(encoding="utf-8", newline="") as handle:
        return list(csv.DictReader(handle))


def _diagnostics(result_dir: Path, rows: list[dict], gtol: float) -> list[dict]:
    """Post-solve curvature and tail diagnostics; not solver cost observations."""
    result = []
    for row in rows:
        trace = _read_trace(result_dir / "traces" / f"{row['run_id']}.csv")
        accepted = [e for e in trace if e["event_type"] == "accepted"]
        last = accepted[-1] if accepted else trace[0]
        previous = accepted[-2] if len(accepted) > 1 else trace[0]
        x = np.asarray(row["x_final"], dtype=float)
        hessian = rosen_hess(x) if row["problem"] == "rosenbrock" else np.diag(2 + 40 * np.pi**2 * np.cos(2 * np.pi * x))
        eig = np.linalg.eigvalsh(hessian)
        tail_change = abs(float(last["f_value"]) - float(previous["f_value"]))
        item = {"run_id": row["run_id"], "problem": row["problem"], "dimension": row["dimension"],
                "start_id": row["start_id"], "method": row["method"],
                "termination_category": _termination_category(row), "solver_status": row["solver_status"],
                "solver_message": row["solver_message"], "stationary": row["stationary"],
                "global_hit": row["global_hit"], "f_value": row["f_value"],
                "gradient_norm": row["gradient_norm"], "gradient_over_threshold": row["gradient_norm"] / gtol,
                "hessian_min_eigenvalue": float(eig.min()), "hessian_max_eigenvalue": float(eig.max()),
                "terminal_extra_nfev": int(trace[-1]["nfev"]) - int(last["nfev"]),
                "terminal_extra_njev": int(trace[-1]["njev"]) - int(last["njev"]),
                "last_accepted_objective_change_abs": tail_change,
                "last_change_over_eps_scale": tail_change / (np.finfo(float).eps * max(1, abs(float(last["f_value"])))),
                "gd_median_step_size": None, "gd_median_backtracks": None,
                "gd_total_trial_evaluations": None, "accepted_objective_increases": 0}
        history = [trace[0], *accepted]
        item["accepted_objective_increases"] = sum(
            float(b["f_value"]) > float(a["f_value"]) + 1e-12 * max(1, abs(float(a["f_value"])))
            for a, b in zip(history, history[1:]))
        if row["method"] == "GD" and accepted:
            item["gd_median_step_size"] = float(np.median([float(e["step_size"]) for e in accepted]))
            item["gd_median_backtracks"] = float(np.median([float(e["backtracks"]) for e in accepted]))
            item["gd_total_trial_evaluations"] = sum(int(e["line_search_trials"]) for e in accepted)
        result.append(item)
    return result


def _paired_comparisons(rows: list[dict]) -> list[dict]:
    groups = defaultdict(dict)
    for row in rows:
        groups[(row["problem"], row["dimension"], row["start_id"])][row["method"]] = row
    result = []
    for (problem, dimension, start_id), methods in sorted(groups.items()):
        for a, b in combinations(METHODS, 2):
            left, right = methods[a], methods[b]
            same_quality = left["stationary"] and right["stationary"] and math.isclose(
                left["f_value"], right["f_value"], rel_tol=1e-6, abs_tol=1e-6)
            result.append({"problem": problem, "dimension": dimension, "start_id": start_id,
                           "method_a": a, "method_b": b,
                           "both_stationary": left["stationary"] and right["stationary"],
                           "both_global_target": left["global_hit"] and right["global_hit"],
                           "comparable_stationary_objective": same_quality,
                           "nfev_a_over_b": left["nfev"] / right["nfev"],
                           "njev_a_over_b": left["njev"] / right["njev"],
                           "f_a_minus_b": left["f_value"] - right["f_value"],
                           "grad_a": left["gradient_norm"], "grad_b": right["gradient_norm"]})
    return result


def _initial_point_table(rows: list[dict]) -> list[dict]:
    grouped = defaultdict(dict)
    for row in rows:
        grouped[(row["problem"], row["dimension"], row["start_id"])][row["method"]] = row
    result = []
    for (problem, dimension, start_id), methods in sorted(grouped.items()):
        item = {"problem": problem, "dimension": dimension, "start_id": start_id,
                "x0": json.dumps(methods["GD"]["x0"])}
        for method in METHODS:
            for metric in ("f_value", "gradient_norm", "nit", "nfev", "njev", "stationary", "global_hit"):
                item[f"{method.lower()}_{metric}"] = methods[method][metric]
        result.append(item)
    return result


def analyze_study(result_dir: Path, output: Path) -> dict:
    result_dir, output = Path(result_dir).resolve(), Path(output).resolve()
    metadata = json.loads((result_dir / "metadata.json").read_text(encoding="utf-8"))
    if metadata.get("execution_status") != "completed":
        raise ValueError("Study has not completed; do not analyze an incomplete summary")
    config = json.loads((result_dir / "config_resolved.json").read_text(encoding="utf-8"))
    rows = read_summary(result_dir / "summary.csv")
    if len(rows) != metadata["expected_runs"] or len({r["run_id"] for r in rows}) != len(rows):
        raise ValueError("Summary run count or IDs are inconsistent")
    output.mkdir(parents=True, exist_ok=True)
    groups = aggregate(rows)
    diagnostics = _diagnostics(result_dir, rows, config["solver"]["gtol"])
    paired = _paired_comparisons(rows)
    initial = _initial_point_table(rows)
    _write_csv(output / "grouped_results.csv", groups)
    _write_csv(output / "initial_point_comparison.csv", initial)
    _write_csv(output / "paired_comparisons.csv", paired)
    _write_csv(output / "run_diagnostics.csv", diagnostics)
    _write_csv(output / "nonstationary_runs.csv", [r for r in diagnostics if not r["stationary"]])
    _write_csv(output / "stationary_non_global_runs.csv", [r for r in diagnostics if r["stationary"] and not r["global_hit"]])
    categories = Counter(r["termination_category"] for r in diagnostics)
    result = {
        "runs": len(rows), "groups": len(groups), "paired_initial_cases": len(initial),
        "stationary_count": sum(r["stationary"] for r in rows),
        "global_hit_count": sum(r["global_hit"] for r in rows),
        "solver_success_count": sum(r["solver_success"] for r in rows),
        "nonstationary_count": sum(not r["stationary"] for r in rows),
        "termination_counts": dict(categories), "gtol": config["solver"]["gtol"],
        "global_tolerance": config["solver"]["global_tolerance"],
        "summed_solver_seconds": sum(r["elapsed_seconds"] for r in rows),
        "all_runs_in_statistics": True, "groups_data": groups,
        "posthoc_diagnostic_note": "Hessian spectra and tail quantities are offline diagnostics; positive curvature at an approximate endpoint is numerical evidence, not an exact proof.",
        "comparison_limit": "Costs of runs terminating at different endpoint qualities or failing the gradient target are not interchangeable times-to-same-accuracy.",
    }
    write_json(output / "analysis_summary.json", result)
    files = [result_dir / "summary.csv", result_dir / "config_resolved.json", result_dir / "metadata.json"]
    files.extend(sorted((result_dir / "traces").glob("*.csv")))
    project = Path(__file__).resolve().parent.parent
    source_files = [Path(__file__), project / "analyze_results.py"]
    write_json(output / "analysis_provenance.json", {
        "input_sha256": {str(p.relative_to(result_dir)).replace("\\", "/"): sha256(p.read_bytes()).hexdigest() for p in files},
        "source_sha256": {str(p.relative_to(project)).replace("\\", "/"): sha256(p.read_bytes()).hexdigest() for p in source_files if p.exists()},
        "numpy": np.__version__, "scipy": scipy.__version__,
        "aggregation": "Median/min/max across all 5 paired starts, including unsuccessful runs. No post-termination interpolation.",
    })
    return result
