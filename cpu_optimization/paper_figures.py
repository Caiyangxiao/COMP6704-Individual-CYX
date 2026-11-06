"""Readable publication figures from immutable full-study logs.

Each trace ends at its recorded termination. All five paired starts are drawn;
unsuccessful runs are retained. Only gradient display values are floored for the
logarithmic axes, and raw Rastrigin objectives stay on a linear scale.
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
from matplotlib.ticker import LogLocator, MaxNLocator, SymmetricalLogLocator


COLORS = {"GD": "#2878B5", "CG": "#E07B24", "BFGS": "#29975E"}
METHODS = tuple(COLORS)
DISPLAY_FLOOR = 1e-16
DIMENSIONS = (2, 10, 20)
STYLE = {
    "font.size": 18,
    "axes.labelsize": 18,
    "axes.titlesize": 20,
    "xtick.labelsize": 18,
    "ytick.labelsize": 18,
    "legend.fontsize": 18,
}


def _read_csv(path: Path) -> list[dict[str, str]]:
    with path.open(encoding="utf-8-sig", newline="") as handle:
        rows = list(csv.DictReader(handle))
    if not rows:
        raise ValueError(f"Empty study input: {path}")
    return rows


def _truth(value) -> bool:
    return str(value).strip().lower() in {"true", "1", "yes"}


def _numbers(rows: list[dict], key: str) -> np.ndarray:
    return np.asarray([float(row[key]) for row in rows], dtype=np.float64)


def _legend(gtol: float) -> list[Line2D]:
    return [Line2D([], [], color=COLORS[m], linewidth=2, label=m) for m in METHODS] + [
        Line2D([], [], color="#444444", marker="o", markerfacecolor="none",
               linestyle="none", label="Gradient met"),
        Line2D([], [], color="#444444", marker="x", linestyle="none", label="Gradient not met"),
        Line2D([], [], color="#666666", linestyle="--", label=f"Tolerance {gtol:g}"),
    ]


def _gradient_curves(axis, rows: list[dict], traces: dict[str, list[dict]],
                     gtol: float) -> dict:
    for summary in rows:
        trace = traces[summary["run_id"]]
        x = _numbers(trace, "nfev")
        y = _numbers(trace, "gradient_norm")
        finite = np.isfinite(x) & np.isfinite(y)
        display = np.where(finite, np.maximum(y, DISPLAY_FLOOR), np.nan)
        color = COLORS[summary["method"]]
        axis.plot(x, display, color=color, alpha=.60, linewidth=1.25)
        if finite.any():
            last = np.flatnonzero(finite)[-1]
            axis.plot(x[last], display[last], color=color,
                      marker="o" if _truth(summary["stationary"]) else "x",
                      markerfacecolor="none", linestyle="none", markersize=5.7,
                      markeredgewidth=.95)
    axis.set_xscale("symlog", linthresh=1)
    axis.set_yscale("log")
    axis.set_xlim(left=0)
    locator = SymmetricalLogLocator(base=10, linthresh=1)
    locator.set_params(numticks=4)
    axis.xaxis.set_major_locator(locator)
    axis.yaxis.set_major_locator(LogLocator(numticks=4))
    axis.axhline(gtol, color="#666666", linestyle="--", linewidth=1)
    axis.set_xlabel("nfev (symlog)")
    axis.grid(True, alpha=.22)
    return {"xscale": axis.get_xscale(), "yscale": axis.get_yscale(),
            "linthresh": 1, "run_ids": [row["run_id"] for row in rows],
            "start_ids": sorted({int(row["start_id"]) for row in rows}),
            "gradient_tolerance": gtol}


def _save(fig, output: Path, stem: str) -> list[Path]:
    files = []
    for extension in ("png", "pdf"):
        path = output / f"{stem}.{extension}"
        fig.savefig(path, dpi=230, bbox_inches="tight")
        files.append(path)
    plt.close(fig)
    return files


def _rosenbrock(rows: list[dict], traces: dict, output: Path,
                 gtol: float) -> tuple[list[Path], dict]:
    fig, axes = plt.subplots(1, 3, figsize=(11.0, 4.0))
    meta = {"problem": "rosenbrock", "panels": {}}
    for axis, dimension in zip(axes, DIMENSIONS):
        selected = [r for r in rows if int(r["dimension"]) == dimension]
        meta["panels"][f"gradient_d{dimension}"] = _gradient_curves(axis, selected, traces, gtol)
        axis.set_title(f"d = {dimension}")
    axes[0].set_ylabel(r"$\|\nabla f(x)\|_2$")
    fig.text(.075, .985, "Rosenbrock", fontsize=20, va="top")
    handles = _legend(gtol)
    fig.legend(handles=handles[:3], loc="upper center", bbox_to_anchor=(.66, 1.0),
               ncol=3, frameon=False, columnspacing=1.4, handlelength=1.7)
    fig.legend(handles=handles[3:], loc="upper center", bbox_to_anchor=(.5, .89),
               ncol=3, frameon=False, columnspacing=1.1, handlelength=1.4)
    # Captions carry the no-carry-forward/display-floor explanation. Omitting
    # a duplicate small footer keeps the actual 5.5-inch figure readable.
    fig.subplots_adjust(left=.09, right=.985, bottom=.235, top=.69, wspace=.36)
    return _save(fig, output, "paper_rosenbrock_convergence"), meta


def _rastrigin(rows: list[dict], traces: dict, output: Path,
                gtol: float) -> tuple[list[Path], dict]:
    fig, axes = plt.subplots(2, 3, figsize=(11.0, 6.8))
    meta = {"problem": "rastrigin", "raw_objective_scale": "linear",
            "cross_dimension_warning": "f is additive across coordinates; compare methods within each dimension",
            "panels": {}}
    for column, dimension in enumerate(DIMENSIONS):
        selected = [r for r in rows if int(r["dimension"]) == dimension]
        axis = axes[0, column]
        nonfinite = []
        for start in range(1, 6):
            paired = [r for r in selected if int(r["start_id"]) == start]
            values = np.asarray([float(r["f_value"]) for r in paired])
            finite_values = values[np.isfinite(values)]
            if finite_values.size:
                axis.vlines(start, finite_values.min(), finite_values.max(),
                            color="#B6BDC5", linewidth=.9, zorder=1)
        for method_index, method in enumerate(METHODS):
            method_rows = sorted((r for r in selected if r["method"] == method),
                                 key=lambda r: int(r["start_id"]))
            for summary in method_rows:
                value = float(summary["f_value"])
                if not np.isfinite(value):
                    nonfinite.append(summary["run_id"])
                    continue
                x = int(summary["start_id"]) + (method_index - 1) * .14
                axis.plot(x, value, color=COLORS[method], linestyle="none",
                          marker="o" if _truth(summary["stationary"]) else "x",
                          markerfacecolor="none", markersize=7.0, markeredgewidth=1.3)
        axis.set(xlim=(.55, 5.45), ylim=(0, None), title=f"d = {dimension}",
                 xlabel="Initial point #")
        axis.set_xticks(range(1, 6))
        axis.yaxis.set_major_locator(MaxNLocator(nbins=3, min_n_ticks=3))
        axis.grid(True, alpha=.22)
        if nonfinite:
            axis.text(.03, .97, f"{len(nonfinite)} nonfinite ends", transform=axis.transAxes,
                      va="top", fontsize=13, color="#9B2635")
        meta["panels"][f"final_objective_d{dimension}"] = {
            "xscale": axis.get_xscale(), "yscale": axis.get_yscale(),
            "run_ids": [r["run_id"] for r in selected],
            "nonfinite_unplottable_run_ids": nonfinite,
            "data": [{"run_id": r["run_id"], "start_id": int(r["start_id"]),
                      "method": r["method"],
                      "f_value": float(r["f_value"]) if np.isfinite(float(r["f_value"])) else None,
                      "stationary": _truth(r["stationary"])} for r in selected],
        }
        meta["panels"][f"gradient_d{dimension}"] = _gradient_curves(axes[1, column], selected, traces, gtol)
    axes[0, 0].set_ylabel("Raw additive f")
    axes[1, 0].set_ylabel(r"$\|\nabla f(x)\|_2$")
    fig.text(.075, .985, "Rastrigin", fontsize=20, va="top")
    handles = _legend(gtol)
    fig.legend(handles=handles[:3], loc="upper center", bbox_to_anchor=(.66, 1.0),
               ncol=3, frameon=False, columnspacing=1.4, handlelength=1.7)
    fig.legend(handles=handles[3:], loc="upper center", bbox_to_anchor=(.5, .935),
               ncol=3, frameon=False, columnspacing=1.1, handlelength=1.4)
    fig.text(.5, .82, "Raw f adds coordinate contributions: compare methods within each d.",
             ha="center", fontsize=16, color="#4A5662")
    fig.subplots_adjust(left=.09, right=.985, bottom=.145, top=.755, hspace=.46, wspace=.36)
    return _save(fig, output, "paper_rastrigin_quality_convergence"), meta


def make_paper_figures(results: Path, output: Path) -> list[Path]:
    """Create two compact PNG/PDF figures, retaining all 90 full-study runs.

    ``output/paper_plot_metadata.json`` records input/source hashes, package
    versions, the display floor and actual axis scales. Solver outputs and
    previously generated figures are not modified.
    """
    results, output = Path(results).resolve(), Path(output).resolve()
    metadata_path, config_path = results / "metadata.json", results / "config_resolved.json"
    run_metadata = json.loads(metadata_path.read_text(encoding="utf-8"))
    if run_metadata.get("execution_status") != "completed":
        raise ValueError("Paper figures require a completed study")
    config = json.loads(config_path.read_text(encoding="utf-8"))
    if tuple(sorted(config["dimensions"])) != DIMENSIONS or config["starts_per_case"] != 5:
        raise ValueError("Paper layout expects d=2,10,20 and five paired starts")
    summary_path = results / "summary.csv"
    summaries = _read_csv(summary_path)
    expected = {(problem, dimension, start, method) for problem in ("rosenbrock", "rastrigin")
                for dimension in DIMENSIONS for start in range(1, 6) for method in METHODS}
    actual = [(r["problem"], int(r["dimension"]), int(r["start_id"]), r["method"]) for r in summaries]
    if len(summaries) != 90 or len(set(actual)) != 90 or set(actual) != expected:
        raise ValueError("Full paper figures require all 90 unique paired runs")
    traces = {r["run_id"]: _read_csv(results / "traces" / f"{r['run_id']}.csv") for r in summaries}
    output.mkdir(parents=True, exist_ok=True)
    source_hashes = {"summary.csv": hashlib.sha256(summary_path.read_bytes()).hexdigest(),
                     "config_resolved.json": hashlib.sha256(config_path.read_bytes()).hexdigest(),
                     "metadata.json": hashlib.sha256(metadata_path.read_bytes()).hexdigest(),
                     "code/cpu_optimization/paper_figures.py": hashlib.sha256(Path(__file__).read_bytes()).hexdigest()}
    launcher = Path(__file__).parent.parent / "make_paper_figures.py"
    if launcher.is_file():
        source_hashes["code/make_paper_figures.py"] = hashlib.sha256(launcher.read_bytes()).hexdigest()
    for r in summaries:
        relative = f"traces/{r['run_id']}.csv"
        source_hashes[relative] = hashlib.sha256((results / relative).read_bytes()).hexdigest()
    gtol = float(config["solver"]["gtol"])
    files = []
    figure_metadata = {}
    with matplotlib.rc_context(STYLE):
        for problem, maker in [("rosenbrock", _rosenbrock), ("rastrigin", _rastrigin)]:
            selected = [r for r in summaries if r["problem"] == problem]
            saved, details = maker(selected, traces, output, gtol)
            files.extend(saved)
            figure_metadata[problem] = details
    metadata = {
        "generated_at_utc": datetime.now(timezone.utc).isoformat(),
        "direction": "Unconstrained Optimization",
        "versions": {"python": sys.version, "numpy": np.__version__, "matplotlib": matplotlib.__version__,
                     "solver_scipy": run_metadata.get("scipy")},
        "source_sha256": source_hashes, "runs_included": 90,
        "display_floor": DISPLAY_FLOOR, "base_font_size": 18,
        "intended_print_width_points": 396,
        "intended_max_height_points": {"rosenbrock": 150, "rastrigin": 250},
        "xscale": "symlog for nfev, linthresh=1, retaining initial zero",
        "carry_forward": False, "unsuccessful_runs_retained": True,
        "figures": figure_metadata,
    }
    (output / "paper_plot_metadata.json").write_text(
        json.dumps(metadata, ensure_ascii=False, indent=2, allow_nan=False) + "\n", encoding="utf-8")
    return files
