"""End-to-end checks for paired starts, saved costs, and safe result folders."""
from __future__ import annotations

import csv
import json
from pathlib import Path
import tempfile
import unittest

import numpy as np

from cpu_optimization.experiment import make_initial_points, resolve_config, run_experiment


def small_config():
    return {
        "name": "test", "seed": 20261105,
        "functions": ["rosenbrock", "rastrigin"], "dimensions": [2],
        "starts_per_case": 1, "methods": ["GD", "CG", "BFGS"],
        "solver": {"maxiter": 1},
    }


class ExperimentTests(unittest.TestCase):
    def test_demo_points_are_a_stable_subset_of_full_study(self):
        demo = make_initial_points(resolve_config(small_config()))
        full = small_config()
        full.update({"dimensions": [20, 10, 2], "starts_per_case": 5})
        points = make_initial_points(resolve_config(full))
        for case in demo:
            matching = next(p for p in points if p["problem"] == case["problem"]
                            and p["dimension"] == 2 and p["start_id"] == 1)
            np.testing.assert_array_equal(case["x0"], matching["x0"])

    def test_pipeline_preserves_all_runs_and_event_costs(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = run_experiment(small_config(), Path(tmp) / "study", progress=False)
            with (output / "summary.csv").open(encoding="utf-8", newline="") as f:
                summaries = list(csv.DictReader(f))
            self.assertEqual(len(summaries), 6)
            for problem in ("rosenbrock", "rastrigin"):
                paired = [row for row in summaries if row["problem"] == problem]
                self.assertEqual(len({row["x0"] for row in paired}), 1)
            for row in summaries:
                with (output / "traces" / f"{row['run_id']}.csv").open(encoding="utf-8", newline="") as f:
                    trace = list(csv.DictReader(f))
                self.assertEqual(trace[0]["event_type"], "initial")
                self.assertEqual(trace[-1]["event_type"], "terminal")
                self.assertEqual(int(trace[-1]["nfev"]), int(row["nfev"]))
                self.assertEqual(int(trace[-1]["njev"]), int(row["njev"]))
                self.assertEqual(sum(e["event_type"] == "accepted" for e in trace), int(row["nit"]))
            metadata = json.loads((output / "metadata.json").read_text(encoding="utf-8"))
            self.assertEqual(metadata["execution_status"], "completed")
            self.assertEqual(metadata["completed_runs"], 6)
            self.assertTrue(metadata["all_counters_consistent"])
            self.assertTrue(metadata["all_traces_consistent"])
            checks = json.loads((output / "gradient_checks.json").read_text(encoding="utf-8"))
            self.assertTrue(all(item["passed"] for item in checks))
            self.assertTrue((output / "summary.txt").is_file())

    def test_existing_results_are_not_silently_overwritten(self):
        with tempfile.TemporaryDirectory() as tmp:
            output = Path(tmp) / "study"
            output.mkdir()
            marker = output / "important.txt"
            marker.write_text("keep", encoding="utf-8")
            with self.assertRaises(FileExistsError):
                run_experiment(small_config(), output, progress=False)
            self.assertEqual(marker.read_text(encoding="utf-8"), "keep")

    def test_invalid_protocol_is_rejected_before_running(self):
        for key, value in (("methods", ["GD", "GD"]), ("dimensions", [1]),
                           ("starts_per_case", 0), ("seed", -1)):
            with self.subTest(key=key):
                config = small_config()
                config[key] = value
                with self.assertRaises(ValueError):
                    resolve_config(config)


if __name__ == "__main__":
    unittest.main()
