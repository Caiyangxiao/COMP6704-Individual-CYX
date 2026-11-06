"""Generate compact paper figures from completed full-study results."""
from __future__ import annotations

import argparse
from pathlib import Path

from cpu_optimization.paper_figures import make_paper_figures


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("results/full_study"))
    parser.add_argument("--output", type=Path, default=Path("results/full_study/analysis/paper_figures"))
    args = parser.parse_args()
    for path in make_paper_figures(args.results, args.output):
        print(path)


if __name__ == "__main__":
    main()
