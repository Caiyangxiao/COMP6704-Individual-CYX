"""Behavioral checks for the shared solver protocol and numerical budgets.

Run with ``python -m unittest tests.test_solvers -v`` from the project root.
These tests use functions with independently known gradients and optima; they
check accepted steps and reported costs rather than implementation internals.
"""

import unittest

import numpy as np

from cpu_optimization.objectives import Objective, get_objective
from cpu_optimization.solvers import SolverConfig, solve


METHODS = ("gd", "cg", "bfgs")


def quadratic(diagonal=(1.0, 20.0)):
    diagonal = np.asarray(diagonal, dtype=float)
    return Objective(
        name="test_quadratic",
        fun=lambda x: float(0.5 * np.dot(diagonal * x, x)),
        grad=lambda x: diagonal * x,
        optimum_value=0.0,
    )


class SolverTests(unittest.TestCase):
    def assert_consistent_trace(self, result, objective):
        summary, trace = result.summary, result.trace
        self.assertGreaterEqual(len(trace), 2)
        self.assertEqual(trace[0]["event_type"], "initial")
        self.assertEqual(trace[-1]["event_type"], "terminal")
        self.assertEqual(trace[0]["iteration"], 0)
        self.assertEqual(trace[0]["nfev"], 0)
        self.assertEqual(trace[0]["njev"], 0)
        accepted = [row for row in trace if row["event_type"] == "accepted"]
        self.assertEqual(len(accepted), summary["nit"])
        self.assertEqual(
            [row["iteration"] for row in accepted],
            list(range(1, summary["nit"] + 1)),
        )
        self.assertEqual(trace[-1]["iteration"], summary["nit"])
        self.assertEqual(trace[-1]["nfev"], summary["nfev"])
        self.assertEqual(trace[-1]["njev"], summary["njev"])
        np.testing.assert_array_equal(trace[0]["x"], summary["x0"])
        np.testing.assert_array_equal(trace[-1]["x"], summary["x_final"])
        for previous, current in zip(trace, trace[1:]):
            self.assertGreaterEqual(current["nfev"], previous["nfev"])
            self.assertGreaterEqual(current["njev"], previous["njev"])
            self.assertGreaterEqual(
                current["elapsed_seconds"], previous["elapsed_seconds"]
            )
        for row in trace:
            x = np.asarray(row["x"], dtype=float)
            expected_f = float(objective.fun(x))
            expected_norm = float(np.linalg.norm(objective.grad(x), ord=2))
            self.assertAlmostEqual(row["f_value"], expected_f)
            self.assertAlmostEqual(row["gradient_norm"], expected_norm)
            self.assertAlmostEqual(
                row["objective_gap"], expected_f - objective.optimum_value
            )
        self.assertAlmostEqual(summary["f_value"], trace[-1]["f_value"])
        self.assertAlmostEqual(
            summary["gradient_norm"], trace[-1]["gradient_norm"]
        )

    def test_gd_accepted_steps_satisfy_armijo_and_converge(self):
        objective = quadratic()
        config = SolverConfig(maxiter=500)
        result = solve(objective, np.array([3.0, -2.0]), "gd", config)
        self.assert_consistent_trace(result, objective)
        self.assertTrue(result.summary["stationary"])
        self.assertTrue(result.summary["solver_success"])
        self.assertLessEqual(result.summary["gradient_norm"], config.gtol)

        previous = result.trace[0]
        for current in result.trace:
            if current["event_type"] != "accepted":
                continue
            x_previous = np.asarray(previous["x"])
            x_current = np.asarray(current["x"])
            gradient = objective.grad(x_previous)
            gradient_squared = float(np.dot(gradient, gradient))
            step = x_previous - x_current
            alpha = float(np.dot(step, gradient) / gradient_squared)
            self.assertGreater(alpha, 0.0)
            self.assertLessEqual(alpha, config.alpha0)
            np.testing.assert_allclose(
                x_current,
                x_previous - alpha * gradient,
                rtol=1e-12,
                atol=1e-14,
            )
            self.assertLessEqual(
                current["f_value"],
                previous["f_value"]
                - config.c1 * alpha * gradient_squared
                + 1e-12,
            )
            previous = current

    def test_optimal_initial_point_needs_no_update(self):
        objective = quadratic()
        for method in METHODS:
            with self.subTest(method=method):
                result = solve(objective, np.zeros(2), method, SolverConfig())
                self.assert_consistent_trace(result, objective)
                self.assertEqual(result.summary["nit"], 0)
                self.assertTrue(result.summary["solver_success"])
                self.assertTrue(result.summary["stationary"])
                self.assertTrue(result.summary["global_hit"])
                self.assertEqual(result.summary["nfev"], 1)
                self.assertEqual(result.summary["njev"], 1)

    def test_zero_iteration_budget_only_evaluates_initial_point(self):
        objective = quadratic()
        x0 = np.array([2.0, -1.0])
        for method in METHODS:
            with self.subTest(method=method):
                result = solve(objective, x0, method, SolverConfig(maxiter=0))
                self.assert_consistent_trace(result, objective)
                self.assertEqual(result.summary["nit"], 0)
                self.assertEqual(result.summary["nfev"], 1)
                self.assertEqual(result.summary["njev"], 1)
                self.assertFalse(result.summary["solver_success"])
                self.assertFalse(result.summary["stationary"])
                np.testing.assert_array_equal(result.summary["x_final"], x0)

    def test_one_iteration_budget_permits_exactly_one_accepted_update(self):
        objective = quadratic()
        x0 = np.array([2.0, -1.0])
        for method in METHODS:
            with self.subTest(method=method):
                result = solve(objective, x0, method, SolverConfig(maxiter=1))
                self.assert_consistent_trace(result, objective)
                self.assertEqual(result.summary["nit"], 1)
                self.assertFalse(result.summary["stationary"])
                self.assertLess(result.summary["f_value"], objective.fun(x0))
                self.assertGreaterEqual(result.summary["nfev"], 2)
                self.assertGreaterEqual(result.summary["njev"], 2)

    def test_failed_line_search_counts_trials_without_accepting_them(self):
        objective = quadratic((100.0,))
        x0 = np.array([1.0])
        config = SolverConfig(maxiter=5, max_backtracks=1)
        result = solve(objective, x0, "gd", config)
        self.assert_consistent_trace(result, objective)
        # At alpha=1 and alpha=0.5, f(1-alpha*100) is above f(1).
        # The budget allows the initial trial and one backtrack, both rejected.
        self.assertEqual(result.summary["solver_status"], 2)
        self.assertFalse(result.summary["solver_success"])
        self.assertFalse(result.summary["stationary"])
        self.assertEqual(result.summary["nit"], 0)
        self.assertEqual(result.summary["nfev"], 3)
        self.assertEqual(result.summary["njev"], 1)
        self.assertEqual(len(result.trace), 2)
        np.testing.assert_array_equal(result.summary["x_final"], x0)
        self.assertEqual(result.summary["f_value"], objective.fun(x0))

    def test_scipy_native_and_wrapper_evaluation_counts_agree(self):
        objective = quadratic()
        for method in ("cg", "bfgs"):
            with self.subTest(method=method):
                result = solve(
                    objective,
                    np.array([2.0, -1.0]),
                    method,
                    SolverConfig(maxiter=100),
                )
                self.assert_consistent_trace(result, objective)
                self.assertTrue(result.summary["counter_consistent"])
                self.assertTrue(result.summary["stationary"])
                self.assertGreater(result.summary["nfev"], 1)
                self.assertGreater(result.summary["njev"], 1)

    def test_nonfinite_trial_point_is_not_evaluated_or_accepted(self):
        objective = quadratic((2.0,))
        x0 = np.array([1.0])
        result = solve(
            objective, x0, "gd", SolverConfig(alpha0=1e308, maxiter=5)
        )
        self.assert_consistent_trace(result, objective)
        self.assertEqual(result.summary["solver_status"], 3)
        self.assertFalse(result.summary["solver_success"])
        self.assertEqual(result.summary["nit"], 0)
        self.assertEqual(result.summary["nfev"], 1)
        self.assertEqual(result.summary["njev"], 1)
        np.testing.assert_array_equal(result.summary["x_final"], x0)

    def test_rounded_zero_step_is_stagnation_rather_than_convergence(self):
        # The gradient is one, but subtracting one from 1e20 rounds to 1e20.
        objective = quadratic((1e-20,))
        x0 = np.array([1e20])
        result = solve(objective, x0, "gd", SolverConfig(maxiter=5))
        self.assert_consistent_trace(result, objective)
        self.assertEqual(result.summary["solver_status"], 4)
        self.assertFalse(result.summary["solver_success"])
        self.assertFalse(result.summary["stationary"])
        self.assertEqual(result.summary["nit"], 0)
        self.assertEqual(result.summary["nfev"], 1)
        self.assertEqual(result.summary["njev"], 1)
        np.testing.assert_array_equal(result.summary["x_final"], x0)

    def test_both_benchmark_functions_run_through_all_methods(self):
        starts = {
            "rosenbrock": np.array([-1.2, 1.0]),
            "rastrigin": np.array([0.3, -0.7]),
        }
        for name, x0 in starts.items():
            objective = get_objective(name)
            expected_x0 = x0.copy()
            for method in METHODS:
                with self.subTest(objective=name, method=method):
                    result = solve(objective, x0, method, SolverConfig(maxiter=100))
                    self.assert_consistent_trace(result, objective)
                    self.assertTrue(np.isfinite(result.summary["f_value"]))
                    self.assertTrue(np.isfinite(result.summary["gradient_norm"]))
                    self.assertLessEqual(result.summary["nit"], 100)
                    self.assertGreaterEqual(result.summary["nfev"], 1)
                    self.assertGreaterEqual(result.summary["njev"], 1)
                    np.testing.assert_array_equal(x0, expected_x0)

    def test_global_target_can_be_hit_without_stationarity(self):
        objective = quadratic((1.0,))
        for method in METHODS:
            with self.subTest(method=method):
                result = solve(
                    objective,
                    np.array([1e-4]),
                    method,
                    SolverConfig(maxiter=0),
                )
                self.assertTrue(result.summary["global_hit"])
                self.assertFalse(result.summary["stationary"])

    def test_stationarity_does_not_imply_global_target_hit(self):
        # Zero is a stationary local maximum; the global minima are +/-1.
        objective = Objective(
            name="test_double_well",
            fun=lambda x: float((x[0] ** 2 - 1.0) ** 2),
            grad=lambda x: np.array([4.0 * x[0] * (x[0] ** 2 - 1.0)]),
            optimum_value=0.0,
        )
        for method in METHODS:
            with self.subTest(method=method):
                result = solve(objective, np.array([0.0]), method, SolverConfig())
                self.assertTrue(result.summary["stationary"])
                self.assertFalse(result.summary["global_hit"])
                self.assertEqual(result.summary["nit"], 0)


if __name__ == "__main__":
    unittest.main()
