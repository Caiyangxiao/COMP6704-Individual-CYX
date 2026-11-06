"""Figures covering every paired initial point in a completed CPU study.

This module reads immutable solver outputs. It neither calls a solver nor adds
function evaluations to its counters. Curves stop at their recorded terminal
events; median/minimum/maximum summaries retain unsuccessful runs.
"""
from __future__ import annotations

import csv
from datetime import datetime, timezone
import hashlib
import json
from pathlib import Path
import sys

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.lines import Line2D

from .plotting import COLORS, DISPLAY_FLOOR, _contour_values


METHODS = ("GD", "CG", "BFGS")


def _csv(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Missing study input: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Study input has no records: {path}")
    return rows


def _values(trace: list[dict[str, str]], field: str) -> np.ndarray:
    try:
        return np.asarray([float(row[field]) for row in trace], dtype=np.float64)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Invalid numeric trace column: {field}") from exc


def _truth(value: str | bool | None) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _sha(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _display(values: np.ndarray) -> np.ndarray:
    return np.where(np.isfinite(values), np.maximum(values, DISPLAY_FLOOR), np.nan)


def _line(axis, x: np.ndarray, y: np.ndarray, method: str, stationary: bool) -> None:
    # Each run remains its own line, with no interpolation or carry-forward
    # beyond the recorded points. Terminal events can share an iterate while
    # consuming additional evaluations.
    plotted = _display(y)
    axis.plot(x, plotted, color=COLORS[method], alpha=0.46, linewidth=1.0)
    finite = np.isfinite(x) & np.isfinite(y)
    if finite.any():
        last = np.flatnonzero(finite)[-1]
        axis.plot(x[last], plotted[last], color=COLORS[method],
                  marker="o" if stationary else "x", markersize=3.4,
                  markerfacecolor="none", markeredgewidth=0.8,
                  linestyle="none", alpha=0.85)


def _legend_handles(include_status: bool = True) -> list[Line2D]:
    handles = [Line2D([], [], color=COLORS[method], linewidth=1.8, label=method)
               for method in METHODS]
    if include_status:
        handles.extend([
            Line2D([], [], color="#444444", marker="o", markerfacecolor="none",
                   linestyle="none", label="Stationary end"),
            Line2D([], [], color="#444444", marker="x", linestyle="none",
                   label="Nonstationary end"),
        ])
    return handles


def _save(fig, output: Path, stem: str) -> list[Path]:
    paths = []
    for suffix in ("png", "pdf"):
        path = output / f"{stem}.{suffix}"
        fig.savefig(path, dpi=180, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)
    return paths


def _convergence_figure(problem: str, dimensions: list[int], rows: list[dict],
                        traces: dict[str, list[dict]], output: Path,
                        gtol: float, global_tolerance: float) -> tuple[list[Path], dict]:
    fig, axes = plt.subplots(len(dimensions), 3, figsize=(15, 3.7 * len(dimensions)),
                             squeeze=False)
    metadata = {"type": "all_start_convergence", "problem": problem, "panels": {}}
    for row_index, dimension in enumerate(dimensions):
        case_rows = [row for row in rows if int(row["dimension"]) == dimension]
        for summary in case_rows:
            trace = traces[summary["run_id"]]
            iteration, nfev = _values(trace, "iteration"), _values(trace, "nfev")
            gap, gradient = _values(trace, "objective_gap"), _values(trace, "gradient_norm")
            method, stationary = summary["method"], _truth(summary["stationary"])
            _line(axes[row_index, 0], iteration, gap, method, stationary)
            _line(axes[row_index, 1], nfev, gap, method, stationary)
            _line(axes[row_index, 2], iteration, gradient, method, stationary)
        for column, (field, xlabel, ylabel) in enumerate([
            ("gap_vs_iteration", "Accepted updates (symlog)", r"$f(x)-f^*$"),
            ("gap_vs_nfev", "Function evaluations (symlog)", r"$f(x)-f^*$"),
            ("gradient_vs_iteration", "Accepted updates (symlog)", r"$\|\nabla f(x)\|_2$"),
        ]):
            axis = axes[row_index, column]
            axis.set_xscale("symlog", linthresh=1)
            axis.set_yscale("log")
            axis.set_xlim(left=0)
            axis.set(xlabel=xlabel, ylabel=ylabel,
                     title=f"d={dimension}: " + ("Gradient norm" if column == 2 else "Objective gap"))
            threshold = gtol if column == 2 else global_tolerance
            axis.axhline(threshold, color="#666666", linestyle="--", linewidth=0.8, alpha=0.8)
            axis.grid(True, alpha=0.22)
            metadata["panels"][f"d{dimension}_{field}"] = {
                "xscale": axis.get_xscale(), "yscale": axis.get_yscale(), "linthresh": 1,
                "runs": [row["run_id"] for row in case_rows],
                "start_ids": sorted({int(row["start_id"]) for row in case_rows}),
                "threshold": threshold,
            }
    fig.suptitle(f"{problem.title()}: all paired initial points", fontsize=16, y=0.995)
    fig.legend(handles=_legend_handles(), loc="upper center", bbox_to_anchor=(0.5, 0.969),
               ncol=5, frameon=False, fontsize=9)
    fig.text(0.5, 0.012,
             "One thin line per run; curves stop at recorded termination (no carry-forward). "
             "Dashed lines: gap / gradient targets. Display floor: 1e-16.",
             ha="center", fontsize=8.3, color="#4A5662")
    fig.tight_layout(rect=(0, 0.035, 1, 0.94))
    stem = f"{problem}_convergence_all_starts"
    return _save(fig, output, stem), metadata


def _cost_quality_figure(problem: str, dimensions: list[int], rows: list[dict],
                         output: Path) -> tuple[list[Path], dict]:
    fig, axes = plt.subplots(2, 2, figsize=(13.8, 9.0))
    metrics = [
        ("nfev", "Function evaluations", "nfev"),
        ("njev", "Gradient evaluations", "njev"),
        ("objective_gap", "Final objective gap", r"$f(x)-f^*$"),
        ("gradient_norm", "Final gradient norm", r"$\|\nabla f(x)\|_2$"),
    ]
    metadata = {"type": "cost_and_final_quality", "problem": problem,
                "aggregation": "median and min/max across all starts, including unsuccessful runs",
                "panels": {}}
    for axis, (metric, title, ylabel) in zip(axes.flat, metrics):
        panel = {"xscale": "linear", "yscale": "log", "groups": []}
        for method_index, method in enumerate(METHODS):
            positions, medians, minimums, maximums = [], [], [], []
            missing = 0
            for dimension_index, dimension in enumerate(dimensions):
                group = sorted((row for row in rows if int(row["dimension"]) == dimension
                                and row["method"] == method), key=lambda row: int(row["start_id"]))
                values = np.asarray([float(row[metric]) for row in group], dtype=np.float64)
                finite = np.isfinite(values)
                missing += int((~finite).sum())
                position = dimension_index + (method_index - 1) * 0.20
                for index, (summary, value) in enumerate(zip(group, values)):
                    if not np.isfinite(value):
                        continue
                    jitter = (index - (len(group) - 1) / 2) * 0.018
                    stationary = _truth(summary["stationary"])
                    axis.plot(position + jitter, max(value, DISPLAY_FLOOR),
                              marker="o" if stationary else "x", linestyle="none",
                              markerfacecolor="none", markeredgewidth=0.9,
                              color=COLORS[method], markersize=4.7, alpha=0.72)
                raw_finite = values[finite]
                stats = {"dimension": dimension, "method": method, "total_runs": len(group),
                         "finite_runs": int(finite.sum()),
                         "run_ids": [row["run_id"] for row in group]}
                if raw_finite.size:
                    lo, median, hi = [float(x) for x in
                                      (raw_finite.min(), np.median(raw_finite), raw_finite.max())]
                    stats.update(minimum=lo, median=median, maximum=hi)
                    positions.append(position)
                    minimums.append(max(lo, DISPLAY_FLOOR))
                    medians.append(max(median, DISPLAY_FLOOR))
                    maximums.append(max(hi, DISPLAY_FLOOR))
                else:
                    stats.update(minimum=None, median=None, maximum=None)
                panel["groups"].append(stats)
            if positions:
                median_array = np.asarray(medians)
                yerr = np.vstack((median_array - np.asarray(minimums),
                                  np.asarray(maximums) - median_array))
                axis.errorbar(positions, medians, yerr=yerr, color=COLORS[method],
                              linewidth=1.5, elinewidth=1.0, marker="_", markersize=9,
                              capsize=3, label=method)
            if missing:
                axis.text(0.02, 0.96 - method_index * .055,
                          f"{method}: {missing} nonfinite final values (retained in summary)",
                          transform=axis.transAxes, va="top", fontsize=7.5, color=COLORS[method])
        axis.set_yscale("log")
        axis.set(xlabel="Dimension", ylabel=ylabel, title=title)
        axis.set_xticks(np.arange(len(dimensions)), labels=[str(d) for d in dimensions])
        axis.grid(True, alpha=0.22)
        metadata["panels"][metric] = panel
    fig.suptitle(f"{problem.title()}: costs and final quality over all initial points", fontsize=15, y=.995)
    fig.legend(handles=_legend_handles(), loc="upper center", bbox_to_anchor=(.5, .965),
               ncol=5, frameon=False, fontsize=9)
    fig.text(.5, .012,
             "All starts and unsuccessful runs retained. Lines: median; whiskers: min/max; "
             "small markers: individual paired starts. Log display floor: 1e-16.",
             ha="center", fontsize=8.2, color="#4A5662")
    fig.tight_layout(rect=(0, .035, 1, .93))
    return _save(fig, output, f"{problem}_cost_quality_by_dimension"), metadata


def _trajectory_axis(axis, problem: str, start_id: int, group: list[dict],
                     traces: dict[str, list[dict]]) -> None:
    optimum = np.ones(2) if problem == "rosenbrock" else np.zeros(2)
    paths = []
    for row in group:
        trace = traces[row["run_id"]]
        points = np.column_stack((_values(trace, "x_0"), _values(trace, "x_1")))
        finite = np.all(np.isfinite(points), axis=1)
        paths.append((row, points, finite))
    all_points = [optimum[None, :]] + [points[finite] for _, points, finite in paths if finite.any()]
    cloud = np.vstack(all_points)
    lower, upper = cloud.min(axis=0), cloud.max(axis=0)
    padding = np.maximum(.09 * (upper - lower), .2)
    lower, upper = lower - padding, upper + padding
    xx, yy = np.meshgrid(np.linspace(lower[0], upper[0], 170),
                         np.linspace(lower[1], upper[1], 170))
    surface = _contour_values(problem, xx, yy)
    values = np.ma.masked_invalid(np.log1p(np.maximum(surface, 0)))
    if values.count() and float(values.max()) > float(values.min()):
        axis.contour(xx, yy, values, levels=np.linspace(float(values.min()), float(values.max()), 17),
                     colors="#BAC3CC", linewidths=.55, alpha=.8)
    for row, points, finite in paths:
        masked = np.where(finite[:, None], points, np.nan)
        color = COLORS[row["method"]]
        axis.plot(masked[:, 0], masked[:, 1], color=color, linewidth=.95, alpha=.88)
        if finite.any():
            end = points[np.flatnonzero(finite)[-1]]
            axis.plot(end[0], end[1], marker="o" if _truth(row["stationary"]) else "x",
                      color=color, markerfacecolor="none", markersize=5.2,
                      markeredgewidth=1, linestyle="none")
    initial = paths[0][1][0]
    if np.isfinite(initial).all():
        axis.scatter(*initial, c="black", s=24, marker="o", zorder=7)
    axis.scatter(*optimum, c="#A62235", marker="*", s=110, zorder=8)
    axis.set(xlim=(lower[0], upper[0]), ylim=(lower[1], upper[1]),
             title=f"Initial point #{start_id}", xlabel=r"$x_1$", ylabel=r"$x_2$")
    axis.grid(True, alpha=.15)


def _trajectory_figure(problem: str, rows: list[dict], traces: dict[str, list[dict]],
                       output: Path) -> tuple[list[Path], dict]:
    rows_2d = [row for row in rows if int(row["dimension"]) == 2]
    starts = sorted({int(row["start_id"]) for row in rows_2d})
    columns = min(3, len(starts))
    nrows = (len(starts) + columns - 1) // columns
    fig, axes = plt.subplots(nrows, columns, figsize=(5.0 * columns, 4.2 * nrows), squeeze=False)
    metadata = {"type": "all_start_2d_trajectories", "problem": problem, "panels": {}}
    for axis, start_id in zip(axes.flat, starts):
        group = sorted((row for row in rows_2d if int(row["start_id"]) == start_id),
                       key=lambda row: METHODS.index(row["method"]))
        _trajectory_axis(axis, problem, start_id, group, traces)
        metadata["panels"][f"start_{start_id}"] = {
            "xscale": "linear", "yscale": "linear", "start_id": start_id,
            "run_ids": [row["run_id"] for row in group],
            "limits": {"x": list(axis.get_xlim()), "y": list(axis.get_ylim())},
        }
    for axis in list(axes.flat)[len(starts):]:
        axis.set_visible(False)
    handles = _legend_handles()
    handles.extend([
        Line2D([], [], marker="o", color="black", linestyle="none", label="Shared initial point"),
        Line2D([], [], marker="*", color="#A62235", markersize=10,
               linestyle="none", label="Known global minimizer"),
    ])
    fig.suptitle(f"{problem.title()}: all {len(starts)} paired 2-D initial points", fontsize=16, y=.995)
    fig.legend(handles=handles, loc="upper center", bbox_to_anchor=(.5, .96),
               ncol=4, frameon=False, fontsize=8.5)
    fig.text(.5, .012,
             "Contours show log(1 + f). Every recorded path and terminal state is retained. "
             "Plot ranges cover trajectories and the known global minimizer.",
             ha="center", fontsize=8.2, color="#4A5662")
    fig.tight_layout(rect=(0, .04, 1, .89))
    return _save(fig, output, f"{problem}_trajectories_all_starts"), metadata


def generate_study_figures(result_dir: Path, analysis_dir: Path) -> list[Path]:
    """Export six PNG/PDF figures and metadata for a completed full study.

    Every problem/dimension/method group must contain all configured initial
    points. Figures are saved below ``analysis_dir/figures``; the return value
    lists image/PDF files, while ``study_plot_metadata.json`` is written beside
    them. No solver output is modified.
    """
    result_dir, analysis_dir = Path(result_dir).resolve(), Path(analysis_dir).resolve()
    source_metadata = result_dir / "metadata.json"
    if not source_metadata.is_file():
        raise FileNotFoundError(f"Cannot verify study completion: {source_metadata}")
    run_metadata = json.loads(source_metadata.read_text(encoding="utf-8"))
    if run_metadata.get("execution_status") != "completed":
        raise ValueError("Study figures require metadata.execution_status == 'completed'")
    config_file = result_dir / "config_resolved.json"
    config = json.loads(config_file.read_text(encoding="utf-8"))
    summary_file = result_dir / "summary.csv"
    rows = _csv(summary_file)
    dimensions = sorted(int(d) for d in config["dimensions"])
    problems = list(config["functions"])
    expected_methods = tuple(config["methods"])
    if set(expected_methods) != set(METHODS):
        raise ValueError(f"Study plotting expects methods {METHODS}")
    starts = int(config["starts_per_case"])
    expected = len(problems) * len(dimensions) * starts * len(METHODS)
    if len(rows) != expected or int(run_metadata.get("completed_runs", -1)) != expected:
        raise ValueError(f"Expected {expected} completed runs, got {len(rows)} summary records")
    keys = [(row["problem"], int(row["dimension"]), int(row["start_id"]), row["method"])
            for row in rows]
    required = {(problem, dimension, start, method) for problem in problems
                for dimension in dimensions for start in range(1, starts + 1) for method in METHODS}
    if len(set(keys)) != expected or set(keys) != required:
        raise ValueError("Summary has duplicate, missing or unexpected paired run identities")
    traces = {row["run_id"]: _csv(result_dir / "traces" / f"{row['run_id']}.csv") for row in rows}
    output = analysis_dir / "figures"
    output.mkdir(parents=True, exist_ok=True)
    module = Path(__file__).resolve()
    source_hashes = {
        "summary.csv": _sha(summary_file),
        "config_resolved.json": _sha(config_file),
        "metadata.json": _sha(source_metadata),
        "code/cpu_optimization/study_plots.py": _sha(module),
        "code/cpu_optimization/plotting.py": _sha(module.with_name("plotting.py")),
    }
    for row in rows:
        relative = f"traces/{row['run_id']}.csv"
        source_hashes[relative] = _sha(result_dir / relative)
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "direction": "Unconstrained Optimization",
        "source_execution_status": run_metadata["execution_status"],
        "runs_included": len(rows),
        "starts_per_case": starts,
        "versions": {"python": sys.version, "numpy": np.__version__,
                     "matplotlib": matplotlib.__version__, "solver_scipy": run_metadata.get("scipy")},
        "display_floor": DISPLAY_FLOOR,
        "convergence_xscale": "symlog",
        "convergence_linthresh": 1,
        "carry_forward": False,
        "failed_runs_retained": True,
        "source_sha256": source_hashes,
        "figures": {},
    }
    paths = []
    solver_config = config.get("solver", {})
    for problem in problems:
        selected = [row for row in rows if row["problem"] == problem]
        saved, details = _convergence_figure(problem, dimensions, selected, traces, output,
                                             float(solver_config.get("gtol", 1e-6)),
                                             float(solver_config.get("global_tolerance", 1e-6)))
        paths.extend(saved)
        metadata["figures"][f"{problem}_convergence_all_starts"] = details
        saved, details = _cost_quality_figure(problem, dimensions, selected, output)
        paths.extend(saved)
        metadata["figures"][f"{problem}_cost_quality_by_dimension"] = details
        if 2 in dimensions:
            saved, details = _trajectory_figure(problem, selected, traces, output)
            paths.extend(saved)
            metadata["figures"][f"{problem}_trajectories_all_starts"] = details
    (output / "study_plot_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return paths
