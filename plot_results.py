"""Generate diagnostic figures from a saved experiment, without rerunning it."""
from __future__ import annotations

import argparse
from pathlib import Path

from cpu_optimization.plotting import plot_results


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("results/demo_2d"),
                        help="Directory containing summary.csv and traces/ (default: results/demo_2d)")
    args = parser.parse_args()
    try:
        outputs = plot_results(args.results)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        parser.exit(2, f"Cannot plot experiment: {exc}\n")
    for output in outputs:
        print(output)


if __name__ == "__main__":
    main()
