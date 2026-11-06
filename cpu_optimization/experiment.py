"""Configuration, paired starts, auditable files, and a small experiment runner."""
from __future__ import annotations

from dataclasses import asdict
from datetime import datetime, timedelta, timezone
from hashlib import sha256
from pathlib import Path
from typing import Any
import csv
import json
import os
import platform
import sys

import numpy as np
import scipy

from .objectives import OBJECTIVE_NAMES, check_gradient, get_objective
from .solvers import SolverConfig, solve


METHODS = ("GD", "CG", "BFGS")
THREAD_VARIABLES = ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                    "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS")
SUMMARY_COLUMNS = [
    "run_id", "problem", "dimension", "start_id", "method", "f_value",
    "objective_gap", "gradient_norm", "nit", "nfev", "njev", "elapsed_seconds",
    "solver_success", "solver_status", "solver_message", "stationary", "global_hit",
    "finite_result", "counter_consistent", "trace_consistent", "reported_nfev",
    "reported_njev", "nonfinite_evaluations", "trace_events", "x0", "x_final",
]


def _json_safe(value):
    """Write standards-compliant JSON, representing nonfinite numbers as null."""
    if isinstance(value, dict):
        return {str(k): _json_safe(v) for k, v in value.items()}
    if isinstance(value, (list, tuple)):
        return [_json_safe(v) for v in value]
    if isinstance(value, np.generic):
        return _json_safe(value.item())
    if isinstance(value, float) and not np.isfinite(value):
        return None
    return value


def write_json(path: Path, value) -> None:
    path.write_text(json.dumps(_json_safe(value), ensure_ascii=False, indent=2,
                               allow_nan=False) + "\n", encoding="utf-8")


def resolve_config(config: dict[str, Any]) -> dict[str, Any]:
    """Validate explicit settings and fill solver defaults; reject silent typos."""
    allowed = {"name", "seed", "functions", "dimensions", "starts_per_case",
               "methods", "initial_ranges", "solver"}
    if set(config) - allowed:
        raise ValueError(f"Unknown configuration keys: {sorted(set(config) - allowed)}")
    required = {"name", "seed", "functions", "dimensions", "starts_per_case", "methods"}
    if required - set(config):
        raise ValueError(f"Missing configuration keys: {sorted(required - set(config))}")
    result = dict(config)
    if not isinstance(result["name"], str) or not result["name"].strip():
        raise ValueError("name must be a nonempty string")
    for key, minimum in (("seed", 0), ("starts_per_case", 1)):
        if isinstance(result[key], bool) or not isinstance(result[key], int) or result[key] < minimum:
            raise ValueError(f"{key} must be an integer >= {minimum}")
    for key in ("functions", "dimensions", "methods"):
        values = result[key]
        if not isinstance(values, list) or not values or len(set(values)) != len(values):
            raise ValueError(f"{key} must be a nonempty list without duplicates")
    if any(name not in OBJECTIVE_NAMES for name in result["functions"]):
        raise ValueError(f"functions must come from {OBJECTIVE_NAMES}")
    if any(m not in METHODS for m in result["methods"]):
        raise ValueError(f"methods must come from {METHODS}")
    if any(isinstance(d, bool) or not isinstance(d, int) or d < 2 for d in result["dimensions"]):
        raise ValueError("dimensions must be integers >= 2")
    ranges = result.get("initial_ranges", {"rosenbrock": [-2, 2], "rastrigin": [-3, 3]})
    for name in result["functions"]:
        bounds = ranges.get(name)
        if not isinstance(bounds, list) or len(bounds) != 2 or not np.isfinite(bounds).all() or bounds[0] >= bounds[1]:
            raise ValueError(f"Invalid initial range for {name}")
    result["initial_ranges"] = ranges
    result["solver"] = asdict(SolverConfig(**result.get("solver", {})))
    return result


def make_initial_points(config: dict[str, Any]) -> list[dict[str, Any]]:
    """Stable per-case streams keep start #1 identical in demo and full runs.

    Each stream uses SeedSequence([base_seed, objective_index, dimension]).
    Changing the number/order of other dimensions or number of starts does not
    change a previously generated point in this case.
    """
    cases = []
    for problem in config["functions"]:
        for dimension in config["dimensions"]:
            sequence = np.random.SeedSequence([config["seed"], OBJECTIVE_NAMES.index(problem), dimension])
            rng = np.random.default_rng(sequence)
            low, high = config["initial_ranges"][problem]
            points = rng.uniform(low, high, size=(config["starts_per_case"], dimension))
            for start_id, x in enumerate(points, 1):
                cases.append({"problem": problem, "dimension": dimension,
                              "start_id": start_id, "x0": x.tolist()})
    return cases


def _environment_metadata(config: dict) -> dict:
    numpy_configuration = np.show_config(mode="dicts")
    project = Path(__file__).resolve().parent.parent
    files = sorted((project / "cpu_optimization").glob("*.py"))
    files += [project / "run_experiments.py", project / "plot_results.py"]
    hashes = {str(p.relative_to(project)).replace("\\", "/"):
              sha256(p.read_bytes()).hexdigest() for p in files if p.is_file()}
    # Hash the actual BFGS/CG source, not merely its version label.
    from scipy.optimize import _optimize
    source = Path(_optimize.__file__)
    return {
        "started_at": datetime.now(timezone(timedelta(hours=8))).isoformat(),
        "timezone": "Asia/Shanghai", "direction": "Unconstrained Optimization",
        "topic": "Classical methods on nonconvex test functions (CPU)",
        "execution_status": "running", "python": sys.version,
        "python_executable": sys.executable, "numpy": np.__version__,
        "scipy": scipy.__version__, "platform": platform.platform(),
        "processor": platform.processor(), "logical_cpu_count": os.cpu_count(),
        "thread_environment": {name: os.environ.get(name) for name in THREAD_VARIABLES},
        "numpy_configuration": numpy_configuration, "source_sha256": hashes,
        "scipy_optimize_source_sha256": sha256(source.read_bytes()).hexdigest(),
        "initialization": "PCG64 / SeedSequence([seed, objective_index, dimension])",
        "expected_runs": len(config["functions"]) * len(config["dimensions"])
                         * config["starts_per_case"] * len(config["methods"]),
        "timing_scope": "solver call including initialization, trials and event capture; excludes offline diagnostics and file IO",
        "bfgs_complexity_reference": "SciPy 1.13.1 uses dense matrix products in inverse-Hessian update; recheck other versions",
    }


def _gradient_preflight(config: dict) -> list[dict]:
    checks = []
    for problem in config["functions"]:
        for dimension in config["dimensions"]:
            for point in (np.linspace(-0.73, 0.41, dimension),
                          np.linspace(0.19, 1.17, dimension)):
                check = check_gradient(get_objective(problem), point)
                check["x"] = point.tolist()
                checks.append(check)
    if not all(item["passed"] for item in checks):
        raise RuntimeError("Analytic-gradient preflight failed; experiments were not started")
    return checks


def _write_trace(path: Path, run_id: str, case: dict, method: str, trace: list[dict]) -> None:
    fields = ["run_id", "problem", "dimension", "start_id", "method", "iteration",
              "event_type", "nfev", "njev", "elapsed_seconds", "f_value",
              "objective_gap", "gradient_norm", "step_size", "line_search_trials", "backtracks"]
    fields += [f"x_{i}" for i in range(case["dimension"])]
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=fields)
        writer.writeheader()
        for event in trace:
            row = {"run_id": run_id, "problem": case["problem"],
                   "dimension": case["dimension"], "start_id": case["start_id"],
                   "method": method, **{k: v for k, v in event.items() if k != "x"}}
            row.update({f"x_{i}": v for i, v in enumerate(event["x"])})
            writer.writerow(row)


def _write_summary(path: Path, summaries: list[dict]) -> None:
    with path.open("w", encoding="utf-8", newline="") as handle:
        writer = csv.DictWriter(handle, fieldnames=SUMMARY_COLUMNS, extrasaction="ignore")
        writer.writeheader()
        for summary in summaries:
            row = dict(summary)
            for key in ("x0", "x_final"):
                row[key] = json.dumps(summary[key])
            writer.writerow(row)


def _write_overview(path: Path, config: dict, summaries: list[dict]) -> None:
    lines = ["COMP6704 | Unconstrained Optimization | CPU experiment",
             "This is a reproducible benchmark run, not a universal optimizer ranking.",
             f"Runs: {len(summaries)}; dimensions: {config['dimensions']}; starts per case: {config['starts_per_case']}",
             "Stationary and global-target flags are separate offline checks.",
             "", "problem      method  nit     nfev     njev      f_final       grad_norm  stationary global_hit"]
    for s in summaries:
        lines.append(f"{s['problem']:<12} {s['method']:<6} {s['nit']:>5} {s['nfev']:>8} {s['njev']:>8} "
                     f"{s['f_value']:>12.5e} {s['gradient_norm']:>12.5e} "
                     f"{str(s['stationary']):>10} {str(s['global_hit']):>10}")
    lines += ["", "Raw statuses/messages: see summary.csv and runs/*.json.",
              "Accepted/initial/terminal events and cumulative costs: traces/*.csv.",
              "Initial values and all diagnostic f/gradient values are computed offline.",
              "Every solver evaluation, including failed final trials, is counted.",
              "Short CPU timing differences include logging overhead and may be noisy."]
    path.write_text("\n".join(lines) + "\n", encoding="utf-8")


def run_experiment(config: dict[str, Any], output: Path, *, progress: bool = True) -> Path:
    """Run a validated study in a fresh folder; preserve unsuccessful solves."""
    resolved = resolve_config(config)
    output = Path(output).resolve()
    if output.exists() and any(output.iterdir()):
        raise FileExistsError(f"Output is not empty: {output}. Choose a new --output folder.")
    checks = _gradient_preflight(resolved)
    points = make_initial_points(resolved)
    output.mkdir(parents=True, exist_ok=True)
    (output / "traces").mkdir(exist_ok=True)
    (output / "runs").mkdir(exist_ok=True)
    metadata = _environment_metadata(resolved)
    write_json(output / "config_resolved.json", resolved)
    write_json(output / "initial_points.json", points)
    write_json(output / "gradient_checks.json", checks)
    write_json(output / "metadata.json", metadata)
    summaries = []
    try:
        cfg = SolverConfig(**resolved["solver"])
        for case in points:
            objective = get_objective(case["problem"])
            for method in resolved["methods"]:
                run_id = f"{case['problem']}_d{case['dimension']}_s{case['start_id']:02d}_{method.lower()}"
                result = solve(objective, case["x0"], method, cfg)
                summary = {"run_id": run_id, "start_id": case["start_id"], **result.summary}
                _write_trace(output / "traces" / f"{run_id}.csv", run_id, case, method, result.trace)
                write_json(output / "runs" / f"{run_id}.json", summary)
                summaries.append(summary)
                # Keep a useful partial summary if an unexpected later error occurs.
                _write_summary(output / "summary.csv", summaries)
                if progress:
                    print(f"[{len(summaries)}/{metadata['expected_runs']}] {run_id}: "
                          f"f={summary['f_value']:.6g}, |g|={summary['gradient_norm']:.3g}, "
                          f"nit={summary['nit']}, nfev={summary['nfev']}, "
                          f"njev={summary['njev']}, stationary={summary['stationary']}", flush=True)
        metadata.update({"execution_status": "completed", "completed_runs": len(summaries),
                         "all_counters_consistent": all(s["counter_consistent"] for s in summaries),
                         "all_traces_consistent": all(s["trace_consistent"] for s in summaries)})
        _write_overview(output / "summary.txt", resolved, summaries)
    except Exception as exc:
        metadata.update({"execution_status": "failed", "completed_runs": len(summaries),
                         "error": f"{type(exc).__name__}: {exc}"})
        raise
    finally:
        write_json(output / "metadata.json", metadata)
    return output
