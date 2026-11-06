"""Aggregate a completed study and optionally generate all-start figures."""
from pathlib import Path
import argparse


def main():
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument("--results", type=Path, default=Path("results/full_study"))
    parser.add_argument("--output", type=Path, default=None)
    parser.add_argument("--plot", action="store_true")
    args = parser.parse_args()
    from cpu_optimization.analysis import analyze_study
    output = args.output or args.results / "analysis"
    try:
        summary = analyze_study(args.results, output)
        if args.plot:
            from cpu_optimization.study_plots import generate_study_figures
            for path in generate_study_figures(args.results, output):
                print(path)
            from cpu_optimization.outcome_plot import plot_outcomes
            for path in plot_outcomes(args.results, output):
                print(path)
    except (FileNotFoundError, ValueError, KeyError) as exc:
        parser.exit(2, f"Cannot analyze study: {exc}\n")
    print(f"Runs={summary['runs']}; stationary={summary['stationary_count']}; "
          f"global target={summary['global_hit_count']}; nonstationary={summary['nonstationary_count']}")
    print(f"Analysis saved to: {output.resolve()}")


if __name__ == "__main__":
    main()
