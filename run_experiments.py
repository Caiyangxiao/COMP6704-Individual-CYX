"""Run the configured CPU experiment, optionally producing offline figures."""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--config", type=Path, default=Path("configs/demo_2d.json"))
    parser.add_argument("--output", type=Path, default=Path("results/demo_2d"))
    parser.add_argument("--threads", type=int, default=1,
                        help="Process-local BLAS/OpenMP thread limits, set before NumPy import")
    parser.add_argument("--plot", action="store_true", help="Create figures after solving")
    args = parser.parse_args()
    if args.threads < 1:
        parser.error("--threads must be positive")
    # These affect this process only, not Windows/global settings.
    for name in ("OMP_NUM_THREADS", "OPENBLAS_NUM_THREADS", "MKL_NUM_THREADS",
                 "VECLIB_MAXIMUM_THREADS", "NUMEXPR_NUM_THREADS", "BLIS_NUM_THREADS"):
        os.environ[name] = str(args.threads)
    from cpu_optimization.experiment import run_experiment
    try:
        config = json.loads(args.config.read_text(encoding="utf-8"))
        output = run_experiment(config, args.output)
        if args.plot:
            from cpu_optimization.plotting import plot_results
            for path in plot_results(output):
                print(path)
    except (FileNotFoundError, FileExistsError, ValueError, TypeError, RuntimeError) as exc:
        parser.exit(2, f"Experiment failed: {exc}\n")
    print(f"Results saved to: {output}")


if __name__ == "__main__":
    main()
