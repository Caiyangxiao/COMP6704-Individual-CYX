"""Ensure study statistics retain failed runs and reproduce saved artifacts."""
from pathlib import Path
import csv
import json
import tempfile
import unittest

from cpu_optimization.analysis import METRICS, aggregate, analyze_study
from cpu_optimization.experiment import run_experiment


class AnalysisTests(unittest.TestCase):
    def test_failed_runs_remain_in_medians_ranges_and_denominators(self):
        rows = []
        for value in [1, 2, 3, 4, 100]:
            rows.append({"problem": "rosenbrock", "dimension": 2, "method": "GD",
                         "solver_success": value != 100, "stationary": value != 100,
                         "global_hit": False, **{metric: value for metric in METRICS}})
        group = aggregate(rows)[0]
        self.assertEqual(group["n"], 5)
        self.assertEqual(group["stationary_count"], 4)
        self.assertEqual(group["nfev_median"], 3)
        self.assertEqual(group["nfev_max"], 100)
        self.assertEqual(group["nonstationary_count"], 1)

    def test_completed_study_produces_group_and_provenance_files(self):
        config = {"name": "analysis_test", "seed": 7,
                  "functions": ["rosenbrock", "rastrigin"], "dimensions": [2],
                  "starts_per_case": 1, "methods": ["GD", "CG", "BFGS"],
                  "solver": {"maxiter": 1}}
        with tempfile.TemporaryDirectory() as tmp:
            result_dir = run_experiment(config, Path(tmp) / "study", progress=False)
            output = result_dir / "analysis"
            result = analyze_study(result_dir, output)
            self.assertEqual(result["runs"], 6)
            self.assertEqual(result["groups"], 6)
            self.assertEqual(result["paired_initial_cases"], 2)
            self.assertEqual(result["nonstationary_count"], 6)
            self.assertEqual(result["termination_counts"]["iteration_limit"], 6)
            with (output / "run_diagnostics.csv").open(encoding="utf-8", newline="") as handle:
                diagnostics = list(csv.DictReader(handle))
            self.assertEqual(len(diagnostics), 6)
            provenance = json.loads((output / "analysis_provenance.json").read_text(encoding="utf-8"))
            self.assertIn("summary.csv", provenance["input_sha256"])
            self.assertTrue((output / "grouped_results.csv").is_file())

    def test_incomplete_study_is_rejected(self):
        with tempfile.TemporaryDirectory() as tmp:
            root = Path(tmp)
            (root / "metadata.json").write_text('{"execution_status":"running"}', encoding="utf-8")
            with self.assertRaises(ValueError):
                analyze_study(root, root / "analysis")


if __name__ == "__main__":
    unittest.main()
