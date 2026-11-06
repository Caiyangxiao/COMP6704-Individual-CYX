"""Checks of benchmark definitions, derivatives, and diagnostic behavior."""

from __future__ import annotations

import json
import unittest
from dataclasses import FrozenInstanceError

import numpy as np

from cpu_optimization.objectives import (
    OBJECTIVE_NAMES,
    Objective,
    check_gradient,
    get_objective,
)


class ObjectiveTests(unittest.TestCase):
    def test_known_global_minima_and_gradients(self) -> None:
        for dimension in (2, 10, 20):
            for name, coordinate in (("rosenbrock", 1.0), ("rastrigin", 0.0)):
                with self.subTest(name=name, dimension=dimension):
                    objective = get_objective(name)
                    point = np.full(dimension, coordinate, dtype=np.float64)
                    self.assertEqual(objective.optimum_value, 0.0)
                    self.assertEqual(objective.fun(point), 0.0)
                    np.testing.assert_array_equal(
                        objective.grad(point), np.zeros(dimension)
                    )

    def test_rastrigin_stays_positive_very_close_to_minimum(self) -> None:
        objective = get_objective("rastrigin")
        point = np.array([1e-12, -2e-12])
        # The cosine-plus-constant expression can cancel to zero here.
        self.assertGreater(objective.fun(point), 0.0)
        local_quadratic = (1.0 + 20.0 * np.pi**2) * float(point @ point)
        self.assertAlmostEqual(objective.fun(point) / local_quadratic, 1.0)

    def test_rastrigin_matches_definition_away_from_minimum(self) -> None:
        point = np.array([-2.25, -0.3, 0.4, 1.75])
        reference = 10.0 * point.size + float(
            np.sum(point**2 - 10.0 * np.cos(2.0 * np.pi * point))
        )
        self.assertAlmostEqual(get_objective("rastrigin").fun(point), reference)

    def test_analytic_gradients_match_central_differences(self) -> None:
        generator = np.random.default_rng(20261105)
        for name in OBJECTIVE_NAMES:
            for dimension in (2, 10, 20):
                for sample in range(3):
                    with self.subTest(name=name, dimension=dimension, sample=sample):
                        point = generator.uniform(-1.5, 1.5, size=dimension)
                        before = point.copy()
                        result = check_gradient(get_objective(name), point)
                        self.assertTrue(result["passed"], result)
                        self.assertLess(result["relative_error"], 1e-5)
                        np.testing.assert_array_equal(point, before)
                        json.dumps(result, allow_nan=False)

    def test_both_functions_have_negative_directional_curvature(self) -> None:
        # Negative centered second differences independently establish
        # nonconvexity, without using either analytic gradient implementation.
        examples = (
            ("rosenbrock", np.array([0.0, 1.0])),
            ("rastrigin", np.array([0.5, 0.0])),
        )
        step = 1e-4
        for name, point in examples:
            with self.subTest(name=name):
                objective = get_objective(name)
                offset = np.array([step, 0.0])
                second_difference = (
                    objective.fun(point + offset)
                    - 2.0 * objective.fun(point)
                    + objective.fun(point - offset)
                ) / step**2
                self.assertLess(second_difference, -100.0)

    def test_invalid_shapes_and_dimensions_are_rejected(self) -> None:
        for name in OBJECTIVE_NAMES:
            objective = get_objective(name)
            for point in (np.array(1.0), np.zeros((2, 2)), np.array([])):
                for function in (objective.fun, objective.grad):
                    with self.subTest(name=name, point=point, function=function):
                        with self.assertRaises(ValueError):
                            function(point)
        rosenbrock = get_objective("rosenbrock")
        with self.assertRaises(ValueError):
            rosenbrock.fun([1.0])
        with self.assertRaises(ValueError):
            rosenbrock.grad([1.0])

    def test_gradient_is_float64_and_input_is_unchanged(self) -> None:
        point = np.array([-1, 2, 0], dtype=np.int32)
        original = point.copy()
        for name in OBJECTIVE_NAMES:
            with self.subTest(name=name):
                objective = get_objective(name)
                self.assertIsInstance(objective.fun(point), float)
                self.assertEqual(objective.grad(point).dtype, np.dtype(np.float64))
                np.testing.assert_array_equal(point, original)


class GradientDiagnosticTests(unittest.TestCase):
    def test_incorrect_gradient_fails(self) -> None:
        objective = Objective(
            "incorrect-quadratic",
            lambda x: float(x @ x),
            lambda x: np.zeros_like(x),
        )
        result = check_gradient(objective, np.array([1.0, -2.0]))
        self.assertFalse(result["passed"])
        self.assertGreater(result["max_abs_error"], 1.0)

    def test_invalid_steps_and_nonfinite_points_are_rejected(self) -> None:
        objective = get_objective("rastrigin")
        for step in (0.0, -1e-6, float("inf"), float("nan")):
            with self.subTest(step=step):
                with self.assertRaises(ValueError):
                    check_gradient(objective, np.array([0.2]), relative_step=step)
        with self.assertRaises(ValueError):
            check_gradient(objective, np.array([float("nan")]))

    def test_unknown_objective_and_frozen_metadata(self) -> None:
        with self.assertRaises(ValueError):
            get_objective("unknown")
        objective = get_objective(" Rosenbrock ")
        self.assertEqual(objective.name, "rosenbrock")
        with self.assertRaises(FrozenInstanceError):
            objective.name = "changed"  # type: ignore[misc]


if __name__ == "__main__":
    unittest.main()
