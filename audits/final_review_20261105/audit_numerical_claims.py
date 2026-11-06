"""Independently audit the final paper from raw per-run JSON and trace CSV.

No grouped table, summary CSV, diagnostic CSV, or solver is imported or used.
Independent analytic derivatives and Hessians are defined below. Only this
audit directory receives output; the original source/results remain untouched.
"""
from __future__ import annotations

import ast
import csv
import hashlib
import json
from collections import Counter, defaultdict
from decimal import Decimal
from pathlib import Path
import statistics

import numpy as np


ROOT = Path(__file__).resolve().parents[2]
DATA = ROOT / "results" / "full_study"
HERE = Path(__file__).resolve().parent
INPUTS = {}
CHECKS = defaultdict(lambda: {"total": 0, "failed": 0})
ISSUES = []


def source(path):
    data = path.read_bytes()
    INPUTS[path.relative_to(ROOT).as_posix()] = {
        "size_bytes": len(data), "sha256": hashlib.sha256(data).hexdigest()
    }
    return data


def load_json(path):
    return json.loads(source(path).decode("utf-8"))


def check(category, condition, **detail):
    CHECKS[category]["total"] += 1
    if not bool(condition):
        CHECKS[category]["failed"] += 1
        ISSUES.append({"category": category, **detail})


def objective(problem, point):
    x = np.asarray(point, dtype=np.float64)
    if problem == "rosenbrock":
        residual = x[1:] - x[:-1] ** 2
        return float(np.sum(100 * residual ** 2 + (1 - x[:-1]) ** 2))
    return float(np.sum(x * x + 20 * np.sin(np.pi * x) ** 2))


def gradient(problem, point):
    x = np.asarray(point, dtype=np.float64)
    if problem == "rosenbrock":
        result = np.zeros_like(x)
        for i in range(len(x) - 1):
            residual = x[i + 1] - x[i] * x[i]
            result[i] += -400 * x[i] * residual + 2 * (x[i] - 1)
            result[i + 1] += 200 * residual
        return result
    return 2 * x + 20 * np.pi * np.sin(2 * np.pi * x)


def rosenbrock_hessian(point):
    x = np.asarray(point, dtype=np.float64)
    result = np.zeros((len(x), len(x)))
    for i in range(len(x) - 1):
        result[i, i] += 1200 * x[i] ** 2 - 400 * x[i + 1] + 2
        result[i + 1, i + 1] += 200
        result[i, i + 1] = result[i + 1, i] = -400 * x[i]
    return result


def report_number(value, digits=3):
    value = float(value)
    return (f"{value:.{digits - 1}e}" if abs(value) < .001 or abs(value) >= 1e4
            else f"{value:.{digits}g}")


def displayed_rounding_matches(displayed, actual):
    displayed = Decimal(displayed)
    half_unit = Decimal(10) ** displayed.as_tuple().exponent / 2
    return abs(Decimal(str(actual)) - displayed) <= half_unit


def stats(values):
    return {"median": statistics.median(values), "min": min(values), "max": max(values)}


def main():
    paper = load_json(ROOT / "paper_source" / "content.json")
    source(ROOT / "paper_source" / "create_content.py")
    metadata = load_json(DATA / "metadata.json")
    config = load_json(DATA / "config_resolved.json")
    initial_points = load_json(DATA / "initial_points.json")
    preflight = load_json(DATA / "gradient_checks.json")
    runs = [load_json(path) for path in sorted((DATA / "runs").glob("*.json"))]
    run_by_id = {run["run_id"]: run for run in runs}
    grouped = defaultdict(list)
    traces = {}
    gd_steps, gd_trials = defaultdict(list), defaultdict(list)
    events = Counter()
    accepted_updates = 0
    independent_labels = {}
    max_value_error = max_gradient_error = 0.0
    for run in runs:
        run_id = run["run_id"]
        problem, dimension, method = run["problem"], run["dimension"], run["method"]
        grouped[(problem, dimension, method)].append(run)
        x = np.asarray(run["x_final"], dtype=np.float64)
        f = objective(problem, x)
        norm = float(np.linalg.norm(gradient(problem, x)))
        finite = bool(np.isfinite(x).all() and np.isfinite(f) and np.isfinite(norm))
        stationary = finite and norm <= config["solver"]["gtol"]
        global_hit = finite and abs(f) <= config["solver"]["global_tolerance"]
        independent_labels[run_id] = (stationary, global_hit)
        check("finite_and_outcome_labels", finite == run["finite_result"], run_id=run_id)
        check("finite_and_outcome_labels", stationary == run["stationary"], run_id=run_id)
        check("finite_and_outcome_labels", global_hit == run["global_hit"], run_id=run_id)
        max_value_error = max(max_value_error, abs(f - run["f_value"]))
        max_gradient_error = max(max_gradient_error, abs(norm - run["gradient_norm"]))
        check("independent_endpoint_values", np.isclose(f, run["f_value"], atol=1e-12, rtol=1e-10), run_id=run_id)
        check("independent_endpoint_values", np.isclose(norm, run["gradient_norm"], atol=1e-10, rtol=1e-8), run_id=run_id)
        check("independent_endpoint_values", run["objective_gap"] == run["f_value"], run_id=run_id)
        check("protocol", run["config"] == config["solver"], run_id=run_id)
        path = DATA / "traces" / f"{run_id}.csv"
        text = source(path).decode("utf-8")
        rows = list(csv.DictReader(text.splitlines()))
        traces[run_id] = rows
        previous_counts = (0, 0)
        previous_accepted = rows[0]
        accepted = 0
        for event in rows:
            event_type = event["event_type"]
            events[event_type] += 1
            counts = (int(event["nfev"]), int(event["njev"]))
            event_x = np.array([float(event[f"x_{i}"]) for i in range(dimension)])
            event_f = objective(problem, event_x)
            event_gnorm = float(np.linalg.norm(gradient(problem, event_x)))
            check("trace_independent_values", np.isfinite(event_x).all() and np.isfinite(event_f) and np.isfinite(event_gnorm), run_id=run_id)
            check("trace_independent_values", np.isclose(event_f, float(event["f_value"]), atol=1e-12, rtol=1e-10), run_id=run_id)
            check("trace_independent_values", np.isclose(event_gnorm, float(event["gradient_norm"]), atol=1e-10, rtol=1e-8), run_id=run_id)
            check("trace_counter_monotonicity", all(a >= b for a, b in zip(counts, previous_counts)), run_id=run_id)
            previous_counts = counts
            if event_type != "accepted":
                continue
            accepted += 1
            check("trace_iteration_indices", int(event["iteration"]) == accepted, run_id=run_id)
            if method == "GD":
                alpha = float(event["step_size"])
                trials = int(event["line_search_trials"])
                backtracks = int(event["backtracks"])
                gd_steps[(problem, dimension)].append(alpha)
                gd_trials[(problem, dimension)].append(trials)
                check("gd_trial_protocol", trials == backtracks + 1, run_id=run_id)
                check("gd_trial_protocol", alpha == config["solver"]["alpha0"] * config["solver"]["backtrack_factor"] ** backtracks, run_id=run_id)
                check("gd_trial_protocol", alpha >= config["solver"]["min_alpha"], run_id=run_id)
                old_x = np.array([float(previous_accepted[f"x_{i}"]) for i in range(dimension)])
                new_x = np.array([float(event[f"x_{i}"]) for i in range(dimension)])
                old_gradient = gradient(problem, old_x)
                check("gd_update_equation", np.allclose(new_x, old_x - alpha * old_gradient, atol=1e-12, rtol=1e-12), run_id=run_id)
                old_f, new_f = float(previous_accepted["f_value"]), float(event["f_value"])
                rhs = old_f - config["solver"]["c1"] * alpha * float(old_gradient @ old_gradient)
                check("gd_armijo", new_f <= rhs + 5e-13 * max(1.0, abs(old_f)), run_id=run_id)
            previous_accepted = event
        accepted_updates += accepted
        check("trace_totals", accepted == run["nit"], run_id=run_id)
        check("trace_totals", len(rows) == accepted + 2 == run["trace_events"], run_id=run_id)
        check("trace_initial_terminal", rows[0]["event_type"] == "initial" and rows[-1]["event_type"] == "terminal", run_id=run_id)
        check("trace_initial_terminal", int(rows[0]["nfev"]) == int(rows[0]["njev"]) == 0, run_id=run_id)
        check("trace_initial_terminal", int(rows[0]["iteration"]) == 0 and int(rows[-1]["iteration"]) == run["nit"], run_id=run_id)
        check("trace_initial_terminal", [float(rows[0][f"x_{i}"]) for i in range(dimension)] == run["x0"], run_id=run_id)
        for field in ("nfev", "njev"):
            check("native_and_terminal_counts", int(rows[-1][field]) == run[field] == run["reported_" + field], run_id=run_id, field=field)
        for field in ("f_value", "gradient_norm", "objective_gap"):
            check("terminal_values", float(rows[-1][field]) == run[field], run_id=run_id, field=field)
        check("terminal_coordinates", [float(rows[-1][f"x_{i}"]) for i in range(dimension)] == run["x_final"], run_id=run_id)
        if method == "GD":
            check("gd_evaluation_totals", run["nfev"] == 1 + sum(int(e["line_search_trials"]) for e in rows if e["event_type"] == "accepted"), run_id=run_id)
            check("gd_evaluation_totals", run["njev"] == run["nit"] + 1, run_id=run_id)

    aggregate = {
        "runs": len(runs),
        "stationary": sum(s for s, g in independent_labels.values()),
        "global_hit": sum(g for s, g in independent_labels.values()),
        "stationary_not_global": sum(s and not g for s, g in independent_labels.values()),
        "neither": sum(not s and not g for s, g in independent_labels.values()),
        "accepted_updates": accepted_updates,
        "trace_events": sum(events.values()),
        "initial_terminal_events": events["initial"] + events["terminal"],
        "solver_elapsed_seconds": sum(run["elapsed_seconds"] for run in runs),
        "finite_results": sum(run["finite_result"] for run in runs),
        "native_success_agrees_with_public_stationary": all(run["solver_success"] == independent_labels[run["run_id"]][0] for run in runs),
    }
    expected_counts = {"runs": 90, "stationary": 73, "global_hit": 26,
                       "stationary_not_global": 47, "neither": 17,
                       "accepted_updates": 80425, "trace_events": 80605,
                       "initial_terminal_events": 180, "finite_results": 90}
    for key, value in expected_counts.items():
        check("prose_counts", aggregate[key] == value, claim=key, expected=value, actual=aggregate[key])
    check("prose_time", f"{aggregate['solver_elapsed_seconds']:.3f}" == "26.915")
    subgroup_counts = {}
    for problem in ("rosenbrock", "rastrigin"):
        for method in ("GD", "CG", "BFGS"):
            members = [r for r in runs if r["problem"] == problem and r["method"] == method]
            subgroup_counts[f"{problem}/{method}"] = {
                "runs": len(members), "stationary": sum(independent_labels[r["run_id"]][0] for r in members),
                "global_hit": sum(independent_labels[r["run_id"]][1] for r in members),
                "statuses": dict(Counter(str(r["solver_status"]) for r in members)),
            }
    expected_subgroups = {
        "rosenbrock/GD": (0, 0), "rosenbrock/CG": (15, 14), "rosenbrock/BFGS": (15, 12),
        "rastrigin/GD": (15, 0), "rastrigin/CG": (15, 0), "rastrigin/BFGS": (13, 0),
    }
    for key, expected in expected_subgroups.items():
        check("prose_subgroups", (subgroup_counts[key]["stationary"], subgroup_counts[key]["global_hit"]) == expected, group=key)

    pages = paper["pages"]
    empirical_tables = {}
    independent_groups = {}
    for page, problem in ((pages[5], "rosenbrock"), (pages[6], "rastrigin")):
        table = next(block for block in page if block["kind"] == "table")
        expected_rows = []
        for dimension in (2, 10, 20):
            for method in ("GD", "CG", "BFGS"):
                members = grouped[(problem, dimension, method)]
                check("group_design", len(members) == 5, problem=problem, dimension=dimension, method=method)
                values = {field: stats([r[field] for r in members]) for field in ("nit", "nfev", "njev", "f_value", "gradient_norm", "elapsed_seconds")}
                s = sum(independent_labels[r["run_id"]][0] for r in members)
                g = sum(independent_labels[r["run_id"]][1] for r in members)
                independent_groups[f"{problem}/d{dimension}/{method}"] = {"stationary": s, "global_hit": g, **values}
                row = [str(dimension), method, f"{s}/{g}", str(values["nit"]["median"])]
                for field in ("nfev", "njev"):
                    v = values[field]
                    row.append(f"{v['median']}\n[{v['min']}, {v['max']}]")
                v = values["f_value"]
                row.append(f"{report_number(v['median'])}\n[{report_number(v['min'])}, {report_number(v['max'])}]")
                expected_rows.append(row)
        empirical_tables[problem] = {"expected_rows_from_raw_runs": expected_rows, "paper_rows": table["rows"]}
        check("results_table_shape", len(table["rows"]) == len(expected_rows), problem=problem)
        for row_index, (actual, expected) in enumerate(zip(table["rows"], expected_rows), 1):
            for column, (a, e) in enumerate(zip(actual, expected), 1):
                check("results_table_cells", a == e, problem=problem, row=row_index, column=column, expected=e, actual=a)

    failures = {}
    failure_table = [block for block in pages[6] if block["kind"] == "table"][1]
    for actual in failure_table["rows"]:
        start = int(actual[0]);run_id = f"rastrigin_d20_s{start:02d}_bfgs"
        run = run_by_id[run_id];trace = traces[run_id]
        accepted = [event for event in trace if event["event_type"] == "accepted"]
        last, terminal = accepted[-1], trace[-1]
        extra_f = int(terminal["nfev"]) - int(last["nfev"])
        extra_g = int(terminal["njev"]) - int(last["njev"])
        failures[run_id] = {
            "nit": run["nit"], "nfev": run["nfev"], "njev": run["njev"],
            "gradient_norm": run["gradient_norm"], "f_value": run["f_value"],
            "last_accepted_nfev": int(last["nfev"]), "last_accepted_njev": int(last["njev"]),
            "extra_terminal_nfev": extra_f, "extra_terminal_njev": extra_g,
            "threshold_excess_percent": (run["gradient_norm"] / 1e-6 - 1) * 100,
            "last_accepted_objective_change": float(last["f_value"]) - float(accepted[-2]["f_value"]),
            "native_status": run["solver_status"], "native_message": run["solver_message"],
        }
        check("failure_table_cells", int(actual[1]) == run["nit"], run_id=run_id)
        check("failure_table_cells", actual[2] == f"{run['nfev']} / {run['njev']}", run_id=run_id)
        check("failure_table_cells", displayed_rounding_matches(actual[3], run["gradient_norm"]), run_id=run_id)
        check("failure_table_cells", displayed_rounding_matches(actual[4], run["f_value"]), run_id=run_id)
        check("failure_mechanism", run["solver_status"] == 2 and "precision loss" in run["solver_message"], run_id=run_id)
        check("failure_mechanism", last["iteration"] == terminal["iteration"], run_id=run_id)
    check("failure_work_claims", (failures["rastrigin_d20_s03_bfgs"]["last_accepted_nfev"], failures["rastrigin_d20_s03_bfgs"]["last_accepted_njev"]) == (59, 59))
    check("failure_work_claims", (failures["rastrigin_d20_s03_bfgs"]["extra_terminal_nfev"], failures["rastrigin_d20_s03_bfgs"]["extra_terminal_njev"]) == (58, 46))
    check("failure_work_claims", (failures["rastrigin_d20_s04_bfgs"]["extra_terminal_nfev"], failures["rastrigin_d20_s04_bfgs"]["extra_terminal_njev"]) == (0, 0))
    check("failure_work_claims", displayed_rounding_matches("0.02346", failures["rastrigin_d20_s04_bfgs"]["threshold_excess_percent"]))
    check("failure_work_claims", failures["rastrigin_d20_s04_bfgs"]["last_accepted_objective_change"] == 0.0)

    hessian_table = next(block for block in pages[7] if block["kind"] == "table")
    hessian_diagnostics = {}
    for row in hessian_table["rows"]:
        dimension, start, method = (part.strip() for part in row[0].split("/"))
        run_id = f"rosenbrock_d{dimension}_s{int(start):02d}_{method.lower()}"
        run = run_by_id[run_id]
        eigenvalues = np.linalg.eigvalsh(rosenbrock_hessian(run["x_final"]))
        hessian_diagnostics[run_id] = {"f_value": run["f_value"], "gradient_norm": run["gradient_norm"], "min_eigenvalue": float(eigenvalues[0]), "max_eigenvalue": float(eigenvalues[-1])}
        for text, value in zip(row[1:], (run["f_value"], run["gradient_norm"], eigenvalues[0])):
            check("hessian_table_cells", displayed_rounding_matches(text, value), run_id=run_id, displayed=text, independent=float(value))
        check("hessian_endpoint_interpretation", eigenvalues[0] > 0 and independent_labels[run_id] == (True, False), run_id=run_id)
    claimed_ids = set(hessian_diagnostics)
    actual_ids = {r["run_id"] for r in runs if r["problem"] == "rosenbrock" and independent_labels[r["run_id"]] == (True, False)}
    check("hessian_endpoint_interpretation", claimed_ids == actual_ids)
    check("nonconvexity_example", np.array_equal(rosenbrock_hessian([0., 1.]), np.diag([-398., 200.])))
    check("nonconvexity_example", np.array_equal(gradient("rosenbrock", [0., 1.]), [-2., 200.]))
    check("nonconvexity_example", 2 - 40 * np.pi ** 2 < 0)
    optimum_hessian = rosenbrock_hessian([1., 1.])
    optimum_eigenvalues = np.linalg.eigvalsh(optimum_hessian)
    optimum_condition = float(optimum_eigenvalues[-1] / optimum_eigenvalues[0])
    geometry_diagnostics = {
        "rosenbrock_2d_at_global_minimum": {
            "point": [1., 1.], "hessian": optimum_hessian.tolist(),
            "eigenvalues": optimum_eigenvalues.tolist(),
            "spectral_condition_number": optimum_condition,
        }
    }
    check("optimum_local_geometry", np.array_equal(optimum_hessian, [[802., -400.], [-400., 200.]]))
    check("optimum_local_geometry", displayed_rounding_matches("0.39936", optimum_eigenvalues[0]))
    check("optimum_local_geometry", displayed_rounding_matches("1001.60064", optimum_eigenvalues[1]))
    check("optimum_local_geometry", displayed_rounding_matches("2508", optimum_condition))

    preflight_diagnostics = []
    check("gradient_preflight", len(preflight) == 12)
    actual_preflight_cases = set()
    expected_preflight_cases = {
        (problem, dimension, tuple(point))
        for problem in ("rosenbrock", "rastrigin") for dimension in (2, 10, 20)
        for point in (np.linspace(-.73, .41, dimension), np.linspace(.19, 1.17, dimension))
    }
    for item in preflight:
        problem, dimension = item["objective"], item["dimension"]
        x = np.asarray(item["x"])
        actual_preflight_cases.add((problem, dimension, tuple(x)))
        check("gradient_preflight", item["relative_step"] == 1e-6 and item["absolute_tolerance"] == item["relative_tolerance"] == 1e-5, problem=problem, dimension=dimension)
        analytic = gradient(problem, x)
        numeric = np.empty_like(x)
        for i in range(dimension):
            step = 1e-6 * max(1., abs(float(x[i])))
            plus, minus = x.copy(), x.copy();plus[i] += step;minus[i] -= step
            numeric[i] = (objective(problem, plus) - objective(problem, minus)) / (2 * step)
        passed = bool(np.allclose(analytic, numeric, atol=1e-5, rtol=1e-5))
        nonstationary = bool(np.linalg.norm(analytic) > 1e-6)
        expected_points = (np.linspace(-.73, .41, dimension), np.linspace(.19, 1.17, dimension))
        check("gradient_preflight", passed and item["passed"] and nonstationary, problem=problem, dimension=dimension)
        check("gradient_preflight", any(np.array_equal(x, candidate) for candidate in expected_points), problem=problem, dimension=dimension)
        preflight_diagnostics.append({"problem": problem, "dimension": dimension, "x": x.tolist(), "passed": passed, "nonstationary": nonstationary, "max_abs_error": float(np.max(np.abs(analytic - numeric))), "gradient_norm": float(np.linalg.norm(analytic))})
    check("gradient_preflight", actual_preflight_cases == expected_preflight_cases and len(actual_preflight_cases) == 12)

    pairing = {}
    for case in initial_points:
        key = (case["problem"], case["dimension"], case["start_id"])
        pairing[str(key)] = [r for r in runs if (r["problem"], r["dimension"], r["start_id"]) == key]
        check("paired_initialization", len(pairing[str(key)]) == 3 and all(r["x0"] == case["x0"] for r in pairing[str(key)]), case=str(key))
    for problem_index, problem in enumerate(("rosenbrock", "rastrigin")):
        for dimension in (2, 10, 20):
            rng = np.random.default_rng(np.random.SeedSequence([20261105, problem_index, dimension]))
            low, high = (-2, 2) if problem == "rosenbrock" else (-3, 3)
            generated = rng.uniform(low, high, size=(5, dimension))
            saved = sorted([p for p in initial_points if p["problem"] == problem and p["dimension"] == dimension], key=lambda p:p["start_id"])
            check("paired_initialization", np.array_equal(generated, [p["x0"] for p in saved]), problem=problem, dimension=dimension)
    check("protocol", len(pairing) == 30 and metadata["completed_runs"] == metadata["expected_runs"] == 90)
    expected_solver = {"gtol": 1e-6, "maxiter": 5000, "c1": 1e-4, "c2": .4,
                       "alpha0": 1., "backtrack_factor": .5, "max_backtracks": 50,
                       "min_alpha": 1e-12, "global_tolerance": 1e-6}
    for key, value in expected_solver.items():
        check("protocol_constants", config["solver"][key] == value, key=key)
    check("protocol_constants", config["seed"] == 20261105 and config["starts_per_case"] == 5)
    check("protocol_constants", config["dimensions"] == [2, 10, 20] and config["functions"] == ["rosenbrock", "rastrigin"] and config["methods"] == ["GD", "CG", "BFGS"])
    check("protocol_constants", config["initial_ranges"] == {"rosenbrock": [-2, 2], "rastrigin": [-3, 3]})
    check("protocol", all(v == "1" for v in metadata["thread_environment"].values()))
    check("protocol", metadata["logical_cpu_count"] == 24 and metadata["numpy"] == "1.26.4" and metadata["scipy"] == "1.13.1" and metadata["python"].startswith("3.12.8"))
    check("protocol", "Windows-11" in metadata["platform"] and "Intel64 Family 6 Model 191 Stepping 2" in metadata["processor"])

    ratios, gd_statistics = {}, {}
    for dimension, claimed_ratio, pair_count in ((2, "1.24", 5), (10, "2.97", 3), (20, "3.91", 4)):
        pairs = []
        for start in range(1, 6):
            cg = run_by_id[f"rosenbrock_d{dimension}_s{start:02d}_cg"]
            bfgs = run_by_id[f"rosenbrock_d{dimension}_s{start:02d}_bfgs"]
            if independent_labels[cg["run_id"]][1] and independent_labels[bfgs["run_id"]][1]:
                pairs.append({"start_id": start, "cg_nfev": cg["nfev"], "bfgs_nfev": bfgs["nfev"], "ratio": cg["nfev"] / bfgs["nfev"]})
        median = statistics.median(p["ratio"] for p in pairs)
        ratios[str(dimension)] = {"pairs": pairs, "median": median}
        check("conditional_cost_ratios", len(pairs) == pair_count and displayed_rounding_matches(claimed_ratio, median), dimension=dimension)
        gd_statistics[str(dimension)] = {"steps": stats(gd_steps[("rosenbrock", dimension)]), "trials": stats(gd_trials[("rosenbrock", dimension)])}
        check("gd_step_medians", gd_statistics[str(dimension)]["steps"]["median"] == (1/512 if dimension == 2 else 1/1024), dimension=dimension)
        check("gd_trial_medians", gd_statistics[str(dimension)]["trials"]["median"] == (10 if dimension == 2 else 11), dimension=dimension)

    rastrigin_2d = []
    for start in range(1, 6):
        values = {method: run_by_id[f"rastrigin_d2_s{start:02d}_{method.lower()}"]["f_value"] for method in ("GD", "CG", "BFGS")}
        better = values["GD"] < values["CG"] and values["GD"] < values["BFGS"]
        rastrigin_2d.append({"start_id": start, "f_values": values, "gd_strictly_lower_than_both": better, "range": max(values.values()) - min(values.values()), "near_tie_at_1e-10": max(values.values()) - min(values.values()) <= 1e-10})
    check("rastrigin_paired_quality", sum(item["gd_strictly_lower_than_both"] for item in rastrigin_2d) == 4)

    for name, expected in metadata["source_sha256"].items():
        source(ROOT / name)
        check("original_source_bytes", INPUTS[name]["sha256"] == expected, file=name)
    test_methods = 0
    for path in sorted((ROOT / "tests").glob("*.py")):
        tree = ast.parse(source(path).decode("utf-8"))
        test_methods += sum(isinstance(node, (ast.FunctionDef, ast.AsyncFunctionDef)) and node.name.startswith("test_") for node in ast.walk(tree))
    check("unit_test_count_only", test_methods == 28)
    report = {
        "status": "passed" if not ISSUES else "failed", "solver_invoked": False,
        "scope": "Independent raw-run and trace audit; no grouped/summary/diagnostic numerical inputs.",
        "checks": dict(CHECKS), "issues": ISSUES, "aggregate": aggregate,
        "subgroup_counts": subgroup_counts, "independent_groups": independent_groups,
        "results_table_comparisons": empirical_tables, "failure_diagnostics": failures,
        "hessian_diagnostics": hessian_diagnostics, "gradient_preflight": preflight_diagnostics,
        "geometry_diagnostics": geometry_diagnostics,
        "conditional_paired_cost_ratios": ratios, "gd_steps_and_trials": gd_statistics,
        "rastrigin_2d_paired_objectives": rastrigin_2d,
        "independent_endpoint_max_abs_error": {"f_value": max_value_error, "gradient_norm": max_gradient_error},
        "unit_test_methods_discovered": test_methods,
        "not_reexecuted": "Unit-test pass status and document rendering are outside this no-solver numerical audit; 28 test definitions were counted.",
        "nonempirical_tables": "Literature and asymptotic arithmetic tables require theoretical/source review; empirical protocol verified against saved config/metadata.",
        "inputs": dict(INPUTS), "input_file_count": len(INPUTS),
        "total_input_source_bytes": sum(item["size_bytes"] for item in INPUTS.values()),
    }
    source(Path(__file__).resolve())
    report["audit_script"] = INPUTS[Path(__file__).resolve().relative_to(ROOT).as_posix()]
    path = HERE / "numerical_claims_audit.json"
    path.write_text(json.dumps(report, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    print(json.dumps({"status": report["status"], "failed_checks": len(ISSUES), "checks_performed": sum(c["total"] for c in CHECKS.values()), "input_file_count": report["input_file_count"], "raw_source_bytes": report["total_input_source_bytes"], "report": str(path)}, indent=2))
    if ISSUES:
        print(json.dumps(ISSUES[:20], indent=2))
    return 0 if not ISSUES else 1


if __name__ == "__main__":
    raise SystemExit(main())
