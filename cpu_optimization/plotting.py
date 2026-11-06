"""Plot accepted iterates and evaluation costs from saved CPU experiments.

Reading and plotting are deliberately separate from solving: no evaluations here
are added to solver counters. Log-scale clipping changes display values only.
"""
from __future__ import annotations

import csv
import hashlib
import json
from pathlib import Path

import numpy as np
import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt


DISPLAY_FLOOR = 1e-16
COLORS = {"GD": "#2878B5", "CG": "#E07B24", "BFGS": "#29975E"}


def _read_rows(path: Path) -> list[dict[str, str]]:
    if not path.is_file():
        raise FileNotFoundError(f"Required experiment file does not exist: {path}")
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Experiment file contains no data rows: {path}")
    return rows


def _numbers(rows: list[dict[str, str]], key: str) -> np.ndarray:
    try:
        return np.asarray([float(row[key]) for row in rows], dtype=np.float64)
    except (KeyError, ValueError) as exc:
        raise ValueError(f"Trace column {key!r} is missing or not numeric") from exc


def _flag(value: str | bool | None) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _status(row: dict[str, str]) -> str:
    if _flag(row.get("stationary")):
        return "target hit" if _flag(row.get("global_hit")) else "stationary"
    return "not stationary"


def _plot_positive(axis, x: np.ndarray, values: np.ndarray, **kwargs) -> None:
    finite = np.isfinite(x) & np.isfinite(values)
    # Keep x positions and all terminal events. Mask nonfinite y values rather
    # than connecting a curve across an invalid segment.
    plotted = np.where(finite, np.maximum(values, DISPLAY_FLOOR), np.nan)
    axis.plot(x, plotted, **kwargs)
    axis.set_yscale("log")
    axis.grid(True, alpha=0.25)



def _configure_xscale(axis, series: list[np.ndarray], xlabel: str) -> dict:
    """Use symlog only when disparate evaluation budgets obscure short runs."""
    finite_series = [values[np.isfinite(values)] for values in series]
    maximum = max((float(values.max()) for values in finite_series if values.size), default=0.0)
    final_positive = [float(values[-1]) for values in finite_series
                      if values.size and values[-1] > 0]
    ratio = max(final_positive) / min(final_positive) if final_positive else 1.0
    use_symlog = maximum >= 1000 and ratio > 20
    if use_symlog:
        axis.set_xscale("symlog", linthresh=1)
        axis.set_xlim(left=0)
        axis.set_xlabel(xlabel + " (symlog)")
    else:
        axis.set_xscale("linear")
        axis.set_xlabel(xlabel)
    return {
        "xscale": axis.get_xscale(),
        "yscale": axis.get_yscale(),
        "linthresh": 1 if use_symlog else None,
        "maximum_x": maximum,
        "final_positive_ratio": ratio,
        "final_positive_values": final_positive,
    }


def _sha256(path: Path) -> str:
    return hashlib.sha256(path.read_bytes()).hexdigest()


def _contour_values(problem: str, x: np.ndarray, y: np.ndarray) -> np.ndarray:
    """Vectorized reference surfaces, used only for the diagnostic figure."""
    with np.errstate(over="ignore", invalid="ignore"):
        if problem == "rosenbrock":
            return 100.0 * (y - x * x) ** 2 + (1.0 - x) ** 2
        if problem == "rastrigin":
            return x * x + y * y + 20.0 * (
                np.sin(np.pi * x) ** 2 + np.sin(np.pi * y) ** 2
            )
    raise ValueError(f"No two-dimensional reference contour for {problem!r}")


def _trajectory_panel(axis, problem: str, traces: list[tuple[dict, list[dict]]]) -> None:
    optimum = np.array([1.0, 1.0]) if problem == "rosenbrock" else np.zeros(2)
    paths = []
    for summary, trace in traces:
        points = np.column_stack((_numbers(trace, "x_0"), _numbers(trace, "x_1")))
        finite = np.all(np.isfinite(points), axis=1)
        paths.append((summary, points, finite))
    finite_paths = [points[finite] for _, points, finite in paths if finite.any()]
    cloud = np.vstack([optimum[None, :], *finite_paths])
    lower, upper = cloud.min(axis=0), cloud.max(axis=0)
    padding = np.maximum((upper - lower) * 0.09, 0.20)
    lower, upper = lower - padding, upper + padding
    xx, yy = np.meshgrid(
        np.linspace(lower[0], upper[0], 180),
        np.linspace(lower[1], upper[1], 180),
    )
    surface = _contour_values(problem, xx, yy)
    finite_surface = np.isfinite(surface)
    if finite_surface.any():
        z = np.ma.masked_invalid(np.log1p(np.maximum(surface, 0.0)))
        zmin, zmax = float(z.min()), float(z.max())
        if zmax > zmin:
            axis.contour(xx, yy, z, levels=np.linspace(zmin, zmax, 17),
                         colors="#B4BEC8", linewidths=0.6, alpha=0.8)
    for summary, points, finite in paths:
        method = summary["method"].upper()
        color = COLORS.get(method)
        masked = np.where(finite[:, None], points, np.nan)
        axis.plot(masked[:, 0], masked[:, 1], color=color, linewidth=1.15,
                  alpha=0.9, label=f"{method} ({_status(summary)})")
        if finite.any():
            end = points[np.flatnonzero(finite)[-1]]
            axis.scatter(*end, color=color, marker="X", s=48,
                         edgecolors="white", linewidths=0.5, zorder=6)
    first_points = paths[0][1]
    if np.isfinite(first_points[0]).all():
        axis.scatter(*first_points[0], color="black", marker="o", s=36,
                     label="Shared initial point", zorder=7)
    axis.scatter(*optimum, color="#A62235", marker="*", s=155,
                 label="Known global minimizer", zorder=8)
    axis.set(xlim=(lower[0], upper[0]), ylim=(lower[1], upper[1]),
             xlabel=r"$x_1$", ylabel=r"$x_2$", title="Trajectories; contours of log(1 + f)")
    axis.legend(fontsize=8, loc="best")
    axis.grid(True, alpha=0.15)


def plot_results(result_dir: Path) -> list[Path]:
    """Create PNG/PDF diagnostic figures for start 1 of each problem/dimension.

    Input: summary.csv, traces/<run_id>.csv and optional config_resolved.json.
    Two-dimensional cases get contours plus three convergence panels. Higher
    dimensions get the same convergence panels without a misleading 2-D slice.
    Failed and terminal events are retained, including evaluations spent on a
    failed final line search. Wide budget disparities use a labelled symlog
    x-axis while retaining zero. plot_metadata.json records source hashes and
    actual axis scales. Files are written only under result_dir/figures.
    """
    result_dir = Path(result_dir).resolve()
    summary_path = result_dir / "summary.csv"
    summaries = _read_rows(summary_path)
    config_file = result_dir / "config_resolved.json"
    config = json.loads(config_file.read_text(encoding="utf-8")) if config_file.is_file() else {}
    gtol = float(config.get("solver", {}).get("gtol", 1e-6))
    groups: dict[tuple[str, int], list[dict[str, str]]] = {}
    for row in summaries:
        try:
            dimension, start_id = int(row["dimension"]), int(row["start_id"])
        except (KeyError, ValueError) as exc:
            raise ValueError("summary.csv needs numeric dimension and start_id columns") from exc
        if start_id == 1:
            groups.setdefault((row["problem"], dimension), []).append(row)
    if not groups:
        raise ValueError("No runs with start_id=1 were found in summary.csv")
    output = result_dir / "figures"
    output.mkdir(parents=True, exist_ok=True)
    written: list[Path] = []
    module_path = Path(__file__).resolve()
    source_sha256 = {
        "summary.csv": _sha256(summary_path),
        "cpu_optimization/plotting.py": _sha256(module_path),
    }
    launcher = module_path.parent.parent / "plot_results.py"
    if launcher.is_file():
        source_sha256["plot_results.py"] = _sha256(launcher)
    if config_file.is_file():
        source_sha256["config_resolved.json"] = _sha256(config_file)
    metadata = {
        "matplotlib_version": matplotlib.__version__,
        "display_floor": DISPLAY_FLOOR,
        "source_sha256": source_sha256,
        "xscale_rule": {
            "symlog_when_maximum_x_at_least": 1000,
            "and_final_positive_ratio_exceeds": 20,
            "linthresh": 1,
            "preserves_initial_zero": True,
        },
        "figures": {},
    }
    for (problem, dimension), group in sorted(groups.items()):
        order = {method: i for i, method in enumerate(COLORS)}
        group.sort(key=lambda row: order.get(row["method"].upper(), 99))
        traces = [(row, _read_rows(result_dir / "traces" / f"{row['run_id']}.csv"))
                  for row in group]
        for row in group:
            relative = f"traces/{row['run_id']}.csv"
            source_sha256[relative] = _sha256(result_dir / relative)
        if dimension == 2:
            fig, grid = plt.subplots(2, 2, figsize=(12.8, 9.3))
            _trajectory_panel(grid[0, 0], problem, traces)
            axes = [grid[0, 1], grid[1, 0], grid[1, 1]]
        else:
            fig, grid = plt.subplots(1, 3, figsize=(15.0, 4.8))
            axes = list(grid)
        for summary, trace in traces:
            method = summary["method"].upper()
            label = f"{method} ({_status(summary)})"
            style = dict(color=COLORS.get(method), label=label, linewidth=1.45)
            iterations = _numbers(trace, "iteration")
            gap = _numbers(trace, "objective_gap")
            _plot_positive(axes[0], iterations, gap, **style)
            _plot_positive(axes[1], _numbers(trace, "nfev"), gap, **style)
            _plot_positive(axes[2], iterations, _numbers(trace, "gradient_norm"), **style)
        axes[0].set(xlabel="Accepted updates", ylabel=r"$f(x)-f^*$",
                    title="Objective gap vs iteration")
        axes[1].set(xlabel="Cumulative function evaluations (nfev)", ylabel=r"$f(x)-f^*$",
                    title="Objective gap vs evaluation cost")
        axes[2].set(xlabel="Accepted updates", ylabel=r"$\|\nabla f(x)\|_2$",
                    title="Gradient norm vs iteration")
        iteration_series = [_numbers(trace, "iteration") for _, trace in traces]
        evaluation_series = [_numbers(trace, "nfev") for _, trace in traces]
        panel_scales = {
            "objective_gap_vs_iteration": _configure_xscale(
                axes[0], iteration_series, "Accepted updates"),
            "objective_gap_vs_nfev": _configure_xscale(
                axes[1], evaluation_series, "Cumulative function evaluations (nfev)"),
            "gradient_norm_vs_iteration": _configure_xscale(
                axes[2], iteration_series, "Accepted updates"),
        }
        if dimension == 2:
            panel_scales["trajectory"] = {
                "xscale": grid[0, 0].get_xscale(),
                "yscale": grid[0, 0].get_yscale(),
                "linthresh": None,
            }
        axes[2].axhline(gtol, color="#666666", linestyle="--", linewidth=1,
                        label=f"Gradient target {gtol:g}")
        for axis in axes:
            axis.legend(fontsize=8, loc="best")
        fig.suptitle(f"{problem.title()} | d={dimension} | shared initial point #1", fontsize=15)
        fig.text(0.5, 0.012,
                 "Log plots display max(value, 1e-16); raw logs remain unchanged. "
                 "Terminal events include any unsuccessful final evaluations.",
                 ha="center", fontsize=8, color="#4A5662")
        fig.tight_layout(rect=(0, 0.04, 1, 0.96))
        stem = f"{problem}_d{dimension}_s01"
        metadata["figures"][stem] = {
            "problem": problem,
            "dimension": dimension,
            "start_id": 1,
            "panels": panel_scales,
        }
        for extension in ("png", "pdf"):
            target = output / f"{stem}.{extension}"
            fig.savefig(target, dpi=170, bbox_inches="tight")
            written.append(target)
        plt.close(fig)
    (output / "plot_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2) + "\n", encoding="utf-8")
    return written
