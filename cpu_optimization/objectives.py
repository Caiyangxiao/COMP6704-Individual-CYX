"""Analytic nonconvex objectives and independent gradient diagnostics.

The objective functions are deliberately separate from solver accounting.  Use
these raw callables for offline plots and post-solve checks; wrap them at the
solver boundary when function and gradient evaluations must be counted.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Callable

import numpy as np
from scipy.optimize import rosen, rosen_der


@dataclass(frozen=True)
class Objective:
    """A named objective with an analytic gradient and known optimal value."""

    name: str
    fun: Callable[[np.ndarray], float]
    grad: Callable[[np.ndarray], np.ndarray]
    optimum_value: float = 0.0


OBJECTIVE_NAMES = ("rosenbrock", "rastrigin")
_GRADIENT_CHECK_TOLERANCE = 1e-5


def _as_vector(x: np.ndarray, *, min_dimension: int) -> np.ndarray:
    """Convert an input to a float64 vector without modifying its contents."""
    vector = np.asarray(x, dtype=np.float64)
    if vector.ndim != 1:
        raise ValueError("The objective input must be a one-dimensional vector.")
    if vector.size < min_dimension:
        raise ValueError(
            f"The objective requires dimension >= {min_dimension}; "
            f"received {vector.size}."
        )
    return vector


def _rosenbrock_fun(x: np.ndarray) -> float:
    return float(rosen(_as_vector(x, min_dimension=2)))


def _rosenbrock_grad(x: np.ndarray) -> np.ndarray:
    return np.asarray(
        rosen_der(_as_vector(x, min_dimension=2)), dtype=np.float64
    )


def _rastrigin_fun(x: np.ndarray) -> float:
    vector = _as_vector(x, min_dimension=1)
    # Equivalent to 10*d + sum(x**2 - 10*cos(2*pi*x)), with less
    # cancellation close to the known zero-valued minimizer.
    sine = np.sin(np.pi * vector)
    return float(np.sum(vector * vector + 20.0 * sine * sine))


def _rastrigin_grad(x: np.ndarray) -> np.ndarray:
    vector = _as_vector(x, min_dimension=1)
    return 2.0 * vector + 20.0 * np.pi * np.sin(2.0 * np.pi * vector)


_OBJECTIVES = {
    "rosenbrock": Objective("rosenbrock", _rosenbrock_fun, _rosenbrock_grad),
    "rastrigin": Objective("rastrigin", _rastrigin_fun, _rastrigin_grad),
}


def get_objective(name: str) -> Objective:
    """Return an objective by name, accepting surrounding space and case."""
    if not isinstance(name, str):
        raise TypeError("The objective name must be a string.")
    key = name.strip().lower()
    try:
        return _OBJECTIVES[key]
    except KeyError:
        raise ValueError(
            f"Unknown objective {name!r}; choose from {', '.join(OBJECTIVE_NAMES)}."
        ) from None


def check_gradient(
    objective: Objective,
    x: np.ndarray,
    relative_step: float = 1e-6,
) -> dict[str, str | int | float | bool]:
    """Compare an analytic gradient with coordinate central differences.

    Coordinate ``i`` uses ``h_i = relative_step * max(1, abs(x_i))``.
    ``passed`` applies elementwise absolute and relative tolerances of 1e-5.
    The reported relative error is the two-norm error divided by the larger
    of 1 and the two gradient norms.  Results contain only JSON-serializable
    scalars and do not change the input vector.

    This is a diagnostic using raw objective calls, separate from any solver
    evaluation counts.  Nonfinite inputs or evaluations raise ``ValueError``.
    """
    vector = _as_vector(x, min_dimension=1).copy()
    if not np.all(np.isfinite(vector)):
        raise ValueError("Gradient checks require a finite input vector.")
    if not np.isfinite(relative_step) or relative_step <= 0.0:
        raise ValueError("relative_step must be finite and strictly positive.")

    analytic = np.asarray(objective.grad(vector), dtype=np.float64)
    if analytic.shape != vector.shape:
        raise ValueError("The analytic gradient must have the input shape.")
    if not np.all(np.isfinite(analytic)):
        raise ValueError("The analytic gradient is not finite at this point.")

    numerical = np.empty_like(vector)
    for index in range(vector.size):
        step = relative_step * max(1.0, abs(float(vector[index])))
        plus = vector.copy()
        minus = vector.copy()
        plus[index] += step
        minus[index] -= step
        if plus[index] == minus[index]:
            raise ValueError("relative_step is too small for finite differences.")
        upper = float(objective.fun(plus))
        lower = float(objective.fun(minus))
        if not np.isfinite(upper) or not np.isfinite(lower):
            raise ValueError("Finite-difference objective values are not finite.")
        numerical[index] = (upper - lower) / (2.0 * step)

    difference = analytic - numerical
    max_abs_error = float(np.max(np.abs(difference)))
    analytic_norm = float(np.linalg.norm(analytic, ord=2))
    numerical_norm = float(np.linalg.norm(numerical, ord=2))
    relative_error = float(
        np.linalg.norm(difference, ord=2)
        / max(1.0, analytic_norm, numerical_norm)
    )
    tolerance = _GRADIENT_CHECK_TOLERANCE
    return {
        "objective": objective.name,
        "dimension": int(vector.size),
        "relative_step": float(relative_step),
        "max_abs_error": max_abs_error,
        "relative_error": relative_error,
        "analytic_gradient_norm": analytic_norm,
        "finite_difference_gradient_norm": numerical_norm,
        "absolute_tolerance": tolerance,
        "relative_tolerance": tolerance,
        "passed": bool(
            np.allclose(analytic, numerical, atol=tolerance, rtol=tolerance)
        ),
    }
