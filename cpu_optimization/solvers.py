"""Solvers with measured evaluations and analysis outside the measured region.

Only GD/Armijo is implemented here. CG and BFGS use SciPy without replacing
their line searches. Every solver evaluation passes through the same counters.
"""
from __future__ import annotations

from dataclasses import asdict, dataclass
from time import perf_counter
from typing import Any
import warnings

import numpy as np
from scipy.optimize import minimize

from .objectives import Objective


@dataclass(frozen=True)
class SolverConfig:
    gtol: float = 1e-6
    maxiter: int = 5000
    c1: float = 1e-4
    c2: float = 0.4
    alpha0: float = 1.0
    backtrack_factor: float = 0.5
    max_backtracks: int = 50
    min_alpha: float = 1e-12
    global_tolerance: float = 1e-6

    def __post_init__(self) -> None:
        for name in ("gtol", "alpha0", "min_alpha", "global_tolerance"):
            value = getattr(self, name)
            if not np.isfinite(value) or value <= 0:
                raise ValueError(f"{name} must be finite and positive")
        for name in ("maxiter", "max_backtracks"):
            value = getattr(self, name)
            if isinstance(value, bool) or not isinstance(value, int) or value < 0:
                raise ValueError(f"{name} must be a nonnegative integer")
        if not 0 < self.c1 < self.c2 < 1:
            raise ValueError("Require 0 < c1 < c2 < 1")
        if not 0 < self.backtrack_factor < 1:
            raise ValueError("backtrack_factor must lie strictly between 0 and 1")


@dataclass
class RunResult:
    summary: dict[str, Any]
    trace: list[dict[str, Any]]


class EvaluationCounter:
    """Count actual raw evaluations, including rejected line-search trials."""

    def __init__(self, objective: Objective):
        self.objective = objective
        self.nfev = 0
        self.njev = 0
        self.nonfinite_evaluations = 0

    def fun(self, x: np.ndarray) -> float:
        self.nfev += 1
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            value = float(self.objective.fun(x))
        self.nonfinite_evaluations += int(not np.isfinite(value))
        return value

    def grad(self, x: np.ndarray) -> np.ndarray:
        self.njev += 1
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            value = np.asarray(self.objective.grad(x), dtype=np.float64)
        if value.shape != x.shape:
            raise ValueError(f"Gradient shape {value.shape} does not match x {x.shape}")
        self.nonfinite_evaluations += int(not np.isfinite(value).all())
        return value


def _gd(counter: EvaluationCounter, x0: np.ndarray, cfg: SolverConfig, record) -> dict:
    """Armijo GD. max_backtracks counts reductions after the first trial."""
    x = x0.copy()
    f = counter.fun(x)
    g = counter.grad(x)
    nit = 0
    status, message = 1, "Maximum accepted updates reached."
    while True:
        if not np.isfinite(f) or not np.isfinite(g).all():
            status, message = 3, "Nonfinite objective or gradient at current point."
            break
        gnorm = float(np.linalg.norm(g, ord=2))
        if not np.isfinite(gnorm):
            status, message = 3, "Nonfinite gradient norm."
            break
        if gnorm <= cfg.gtol:
            status, message = 0, "Gradient two-norm target reached."
            break
        if nit >= cfg.maxiter:
            break
        alpha = cfg.alpha0
        accepted = False
        for reductions in range(cfg.max_backtracks + 1):
            if alpha < cfg.min_alpha:
                status, message = 2, "Armijo search reached minimum step size."
                break
            with np.errstate(over="ignore", invalid="ignore"):
                trial = x - alpha * g
            if not np.isfinite(trial).all():
                status, message = 3, "Nonfinite line-search trial point."
                break
            if np.array_equal(trial, x):
                status, message = 4, "Numerical stagnation: trial equals current point."
                break
            f_trial = counter.fun(trial)
            if not np.isfinite(f_trial):
                status, message = 3, "Nonfinite objective at line-search trial."
                break
            if f_trial <= f - cfg.c1 * alpha * (gnorm * gnorm):
                accepted = True
                break
            alpha *= cfg.backtrack_factor
        else:
            status, message = 2, "Armijo search exhausted maximum backtracks."
        if not accepted:
            break
        x, f = trial, f_trial
        g = counter.grad(x)
        nit += 1
        record("accepted", nit, x, step_size=alpha,
               line_search_trials=reductions + 1, backtracks=reductions)
    return {"x": x, "nit": nit, "status": status, "success": status == 0,
            "message": message, "reported_nfev": counter.nfev,
            "reported_njev": counter.njev}


def solve(objective: Objective, x0, method: str,
          config: SolverConfig | None = None) -> RunResult:
    """Return a measured solve plus offline-enriched initial/accepted/terminal events.

    Initial event: x0 and zero counters; its values are filled offline. The
    solver's own initial f/g calls are counted normally. A terminal event may
    repeat the last accepted x with larger counters after a failed line search.
    Logging and callbacks do not evaluate the objective or gradient.
    """
    cfg = config if config is not None else SolverConfig()
    method = method.upper()
    if method not in {"GD", "CG", "BFGS"}:
        raise ValueError(f"Unknown method: {method}")
    x0 = np.array(x0, dtype=np.float64, copy=True)
    if x0.ndim != 1 or not x0.size or not np.isfinite(x0).all():
        raise ValueError("x0 must be a nonempty finite one-dimensional vector")
    counter = EvaluationCounter(objective)
    trace: list[dict[str, Any]] = []
    start = perf_counter()

    def record(event_type, iteration, x, **extra):
        trace.append({"event_type": event_type, "iteration": int(iteration),
                      "x": np.array(x, dtype=np.float64, copy=True),
                      "nfev": counter.nfev, "njev": counter.njev,
                      "elapsed_seconds": perf_counter() - start,
                      "step_size": None, "line_search_trials": None,
                      "backtracks": None, **extra})

    record("initial", 0, x0)
    captured = []
    if method == "GD":
        native = _gd(counter, x0, cfg, record)
    else:
        accepted = 0

        def callback(xk):
            nonlocal accepted
            accepted += 1
            record("accepted", accepted, xk)

        options = {"gtol": cfg.gtol, "norm": 2, "maxiter": cfg.maxiter,
                   "c1": cfg.c1, "c2": cfg.c2, "disp": False}
        if method == "BFGS":
            options["xrtol"] = 0.0  # Initial inverse Hessian is SciPy's identity default.
        with warnings.catch_warnings(record=True) as caught:
            warnings.simplefilter("always")
            res = minimize(counter.fun, x0.copy(), jac=counter.grad,
                           method=method, callback=callback, options=options)
        captured = [{"category": w.category.__name__, "message": str(w.message)}
                    for w in caught]
        native = {"x": np.asarray(res.x), "nit": int(res.nit),
                  "status": int(res.status), "success": bool(res.success),
                  "message": str(res.message), "reported_nfev": int(res.nfev),
                  "reported_njev": int(res.njev)}
    record("terminal", native["nit"], native["x"])
    elapsed = perf_counter() - start
    measured_counts = (counter.nfev, counter.njev)
    counter_consistent = measured_counts == (native["reported_nfev"], native["reported_njev"])
    trace_consistent = sum(e["event_type"] == "accepted" for e in trace) == native["nit"]
    if not counter_consistent or not trace_consistent:
        raise RuntimeError("Solver counters or accepted-iterate callbacks are inconsistent")

    # All diagnostics below use raw functions, outside counters and the timer.
    for event in trace:
        x = event["x"]
        with np.errstate(over="ignore", invalid="ignore", divide="ignore"):
            f_value = float(objective.fun(x))
            g = np.asarray(objective.grad(x), dtype=np.float64)
            gnorm = float(np.linalg.norm(g, ord=2))
        event.update({"x": x.tolist(), "f_value": f_value,
                      "gradient_norm": gnorm,
                      "objective_gap": f_value - objective.optimum_value})
    if measured_counts != (counter.nfev, counter.njev):
        raise RuntimeError("Offline diagnostics changed evaluation counters")
    final = trace[-1]
    finite = bool(np.isfinite(final["f_value"]) and np.isfinite(final["gradient_norm"])
                  and np.isfinite(native["x"]).all())
    stationary = finite and final["gradient_norm"] <= cfg.gtol
    global_hit = finite and abs(final["objective_gap"]) <= cfg.global_tolerance
    summary = {"problem": objective.name, "dimension": int(x0.size), "method": method,
               "x0": x0.tolist(), "x_final": final["x"],
               "f_value": final["f_value"], "gradient_norm": final["gradient_norm"],
               "objective_gap": final["objective_gap"],
               "nit": native["nit"], "nfev": counter.nfev, "njev": counter.njev,
               "reported_nfev": native["reported_nfev"],
               "reported_njev": native["reported_njev"],
               "elapsed_seconds": elapsed, "solver_success": native["success"],
               "solver_status": native["status"], "solver_message": native["message"],
               "stationary": bool(stationary), "global_hit": bool(global_hit),
               "finite_result": finite, "nonfinite_evaluations": counter.nonfinite_evaluations,
               "counter_consistent": counter_consistent, "trace_consistent": trace_consistent,
               "trace_events": len(trace), "warnings": captured, "config": asdict(cfg)}
    return RunResult(summary=summary, trace=trace)
