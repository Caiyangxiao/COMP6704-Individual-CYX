"""A per-start outcome matrix; uses the fixed thresholds in saved results."""
from pathlib import Path
from hashlib import sha256
import json

import numpy as np
import matplotlib
matplotlib.use("Agg")
import matplotlib.pyplot as plt
from matplotlib.colors import ListedColormap, BoundaryNorm
from matplotlib.patches import Patch

from .analysis import read_summary
from .experiment import write_json


def plot_outcomes(result_dir: Path, analysis_dir: Path) -> list[Path]:
    result_dir, analysis_dir = Path(result_dir), Path(analysis_dir)
    rows = read_summary(result_dir / "summary.csv")
    methods = ["GD", "CG", "BFGS"]
    cases = [(problem, dimension) for problem in ("rosenbrock", "rastrigin")
             for dimension in (2, 10, 20)]
    starts = sorted({r["start_id"] for r in rows})
    lookup = {(r["problem"], r["dimension"], r["method"], r["start_id"]): r for r in rows}
    codes = ["G", "L", "I", "P", "F"]
    descriptions = ["G: stationary + global target", "L: stationary, non-global",
                    "I: iteration limit", "P: precision loss / line search", "F: other nonstationary"]
    palette = ["#76B788", "#8FB8DE", "#F1C775", "#E49A9C", "#BDBDBD"]
    matrix = np.empty((len(cases), len(methods) * len(starts)), dtype=int)
    for i, (problem, dimension) in enumerate(cases):
        for j, (method, start_id) in enumerate((m, s) for m in methods for s in starts):
            row = lookup[(problem, dimension, method, start_id)]
            code = "G" if row["stationary"] and row["global_hit"] else (
                "L" if row["stationary"] else "I" if row["solver_status"] == 1 else
                "P" if row["solver_status"] == 2 else "F")
            matrix[i, j] = codes.index(code)
    fig, ax = plt.subplots(figsize=(14, 5.3))
    ax.imshow(matrix, cmap=ListedColormap(palette), norm=BoundaryNorm(np.arange(-.5, 5.5), 5), aspect="auto")
    for i in range(matrix.shape[0]):
        for j in range(matrix.shape[1]):
            ax.text(j, i, codes[matrix[i, j]], ha="center", va="center", fontsize=11)
    ax.set_xticks(range(matrix.shape[1]), [f"{m}\n#{s}" for m in methods for s in starts])
    ax.set_yticks(range(len(cases)), [f"{p.title()} d={d}" for p, d in cases])
    ax.set_xticks(np.arange(-.5, matrix.shape[1], 1), minor=True)
    ax.set_yticks(np.arange(-.5, matrix.shape[0], 1), minor=True)
    ax.grid(which="minor", color="white", linewidth=1.5)
    ax.tick_params(which="minor", bottom=False, left=False)
    for boundary in [len(starts) - .5, 2 * len(starts) - .5]:
        ax.axvline(boundary, color="#333333", linewidth=1.5)
    ax.axhline(2.5, color="#333333", linewidth=1.5)
    fig.suptitle("All 90 outcomes: function, dimension, method, and paired start", fontsize=14)
    fig.legend([Patch(facecolor=c) for c in palette], descriptions, loc="lower center",
               ncol=3, frameon=False, fontsize=8.6, bbox_to_anchor=(.5, .01))
    fig.tight_layout(rect=(0, .15, 1, .93))
    output = analysis_dir / "figures"
    output.mkdir(parents=True, exist_ok=True)
    paths = []
    for suffix in ("png", "pdf"):
        path = output / f"outcome_matrix.{suffix}"
        fig.savefig(path, dpi=180, bbox_inches="tight")
        paths.append(path)
    plt.close(fig)
    write_json(output / "outcome_plot_metadata.json", {
        "matplotlib": matplotlib.__version__, "source_sha256": sha256(Path(__file__).read_bytes()).hexdigest(),
        "summary_sha256": sha256((result_dir / "summary.csv").read_bytes()).hexdigest(),
        "codes": dict(zip(codes, descriptions)), "rows": cases,
        "matrix": [[codes[v] for v in row] for row in matrix],
        "counts": {code: int((matrix == i).sum()) for i, code in enumerate(codes)},
    })
    return paths
