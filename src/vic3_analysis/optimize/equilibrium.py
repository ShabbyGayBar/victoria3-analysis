# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Deterministic building-level search with endogenous household equilibrium."""

import logging
from collections.abc import Mapping
from dataclasses import dataclass, field, replace
from time import perf_counter

import numpy as np
import pandas as pd
import scipy.optimize as opt

from vic3_analysis.analysis.economy import EconomyState, EquilibriumError
from vic3_analysis.analysis.economy._utils import _readonly_wealth
from vic3_analysis.analysis.economy.equilibrium import (
    _validate_equilibrium_tolerances,
)
from vic3_analysis.optimize.base import BaseOptimizer, LinearProblem, _CompiledProblem
from vic3_analysis.optimize.scenario import Scenario

_LOGGER = logging.getLogger(__name__)
_OBJECTIVE_UNITS = {
    "gdp": "GBP/week",
    "gdp_per_capita": "GBP/person/week",
    "average_wealth": "wealth_tier",
}


def _metric(state: EconomyState, objective: str) -> float:
    """Read the selected metric in weekly units from a verified snapshot."""
    if objective == "gdp":
        value = state.gdp_weekly
    elif objective == "gdp_per_capita":
        value = state.gdp_per_capita()
    else:
        value = state.average_wealth
    if not np.isfinite(value):
        raise ValueError("Equilibrium objective must be finite.")
    return value


@dataclass(frozen=True)
class EquilibriumProblem(_CompiledProblem):
    """An immutable equilibrium-search recipe bound to one economy.

    Arrays retain full economy index order. ``initial_wealth`` is copied and
    reused for every evaluation, making results independent of earlier trials.
    ``warm_start`` is a nominal GDP LP over the same linear feasible region.
    Evaluation rebuilds supply-dependent baskets for each building mix.
    """

    warm_start: LinearProblem = field(repr=False, compare=False)
    initial_wealth: np.ndarray = field(repr=False, compare=False)
    max_iterations: int = 1000
    rtol: float = 1e-9
    atol: float = 1e-8

    def __post_init__(self) -> None:
        """Freeze wealth and validate equilibrium controls and alignment."""
        super().__post_init__()
        _validate_equilibrium_tolerances(self.rtol, self.atol)
        if (
            isinstance(self.max_iterations, (bool, np.bool_))
            or not isinstance(self.max_iterations, (int, np.integer))
            or self.max_iterations <= 0
        ):
            raise ValueError("max_iterations must be a positive integer.")
        wealth = _readonly_wealth(self.initial_wealth, "initial_wealth")
        if wealth.shape != (
            len(self.economy.building_index),
            len(self.economy.pop_index),
        ):
            raise ValueError(
                "initial_wealth must match building configurations and professions."
            )
        object.__setattr__(self, "initial_wealth", wealth)

    def evaluate(self, levels: np.ndarray) -> EconomyState:
        """Solve household equilibrium at full-index nonnegative building levels.

        Scenario feasibility is checked by the optimizer, separately from this
        physical evaluation. Invalid model inputs raise ``ValueError``; failed
        equilibrium iteration raises ``EquilibriumError`` with its snapshot.
        """
        levels = np.asarray(levels, dtype=np.float64)
        if levels.shape != (len(self.bounds),):
            raise ValueError("levels must be aligned to building configurations.")
        if not np.isfinite(levels).all() or (levels < 0).any():
            raise ValueError("levels must contain finite non-negative values.")
        return self.economy.solve(
            levels,
            method="equilibrium",
            goods_import=self.goods_import,
            goods_export=self.goods_export,
            throughput_multipliers=self.throughput_multipliers,
            workforce_ratio=self.scenario.workforce_ratio,
            initial_wealth=self.initial_wealth,
            max_iterations=self.max_iterations,
            rtol=self.rtol,
            atol=self.atol,
        )

    def objective(self, levels: np.ndarray) -> float:
        """Return the negative, unscaled metric after solving equilibrium."""
        return -_metric(self.evaluate(levels), self.scenario.objective)

    def _to_building_levels(self, levels: np.ndarray) -> np.ndarray:
        """Map search coordinates to physical levels for final verification."""
        return levels


class _BudgetReached(Exception):
    """Stop even during COBYLA initialization without losing the incumbent."""


@dataclass
class _Search:
    """Bounded working memory and diagnostics for one optimizer invocation."""

    problem: EquilibriumProblem
    budget: int
    nfev: int = 0
    equilibrium_evaluations: int = 0
    failures: dict[str, int] = field(default_factory=dict)
    last_error: EquilibriumError | None = None
    best: EconomyState | None = None
    best_levels: np.ndarray | None = None
    best_value: float = np.inf
    scale: float | None = None
    last_levels: np.ndarray | None = None
    last_value: float = np.pi
    log_every: int = 100
    phase: str = "initialization"
    started_at: float = field(default_factory=perf_counter)
    feasible_trials: int = 0
    infeasible_trials: int = 0
    current_metric: float | None = None
    current_feasible: bool | None = None
    last_equilibrium: str = "not_started"
    last_inner_iterations: int | None = None

    def report(
        self,
        event: str,
        *,
        level: int = logging.INFO,
        status: str = "running",
        message: str = "-",
    ) -> None:
        """Log scalar progress without snapshots, histories, or transformed scores."""
        if not _LOGGER.isEnabledFor(level):
            return
        current = (
            "n/a" if self.current_metric is None else f"{self.current_metric:.12g}"
        )
        best = "n/a" if self.best is None else f"{-self.best_value:.12g}"
        _LOGGER.log(
            level,
            "Equilibrium optimizer %s: phase=%s trials=%d/%d elapsed_s=%.3f "
            "objective=%s units=%s current=%s best=%s current_feasible=%s "
            "feasible_trials=%d infeasible_trials=%d physical_rejections=%d "
            "equilibrium_evaluations=%d failures=%s last_equilibrium=%s "
            "last_inner_iterations=%s status=%s message=%s",
            event,
            self.phase,
            self.nfev,
            self.budget,
            perf_counter() - self.started_at,
            self.problem.scenario.objective,
            _OBJECTIVE_UNITS[self.problem.scenario.objective],
            current,
            best,
            self.current_feasible,
            self.feasible_trials,
            self.infeasible_trials,
            self.nfev - self.equilibrium_evaluations,
            self.equilibrium_evaluations,
            dict(sorted(self.failures.items())),
            self.last_equilibrium,
            self.last_inner_iterations,
            status,
            message,
        )

    def trial(self, levels: np.ndarray) -> float:
        """Score a trial; rejected points have a finite, strictly worse penalty."""
        if self.last_levels is not None and np.array_equal(levels, self.last_levels):
            return self.last_value
        if self.nfev >= self.budget:
            raise _BudgetReached
        self.nfev += 1
        self.last_levels = levels.copy()
        self.last_value = float(np.pi)
        self.current_metric = None
        self.current_feasible = None
        self.last_inner_iterations = None
        self.last_equilibrium = "evaluating"
        try:
            return self._evaluate_trial(levels)
        except Exception as error:
            self.last_equilibrium = type(error).__name__
            raise
        finally:
            self.report("trial", level=logging.DEBUG, status=self.last_equilibrium)
            if self.nfev % self.log_every == 0:
                self.report("progress")

    def _evaluate_trial(self, levels: np.ndarray) -> float:
        """Evaluate and classify one uncached trial without changing its score."""
        if not np.isfinite(levels).all() or (levels < 0).any():
            self.current_feasible = False
            self.last_equilibrium = "invalid_levels"
            return self.last_value
        self.equilibrium_evaluations += 1
        try:
            state = self.problem.evaluate(levels)
        except EquilibriumError as error:
            status = error.diagnostics.status
            self.failures[status] = self.failures.get(status, 0) + 1
            self.last_error = error
            self.last_equilibrium = status
            self.last_inner_iterations = error.diagnostics.iterations
            return self.last_value
        value = -_metric(state, self.problem.scenario.objective)
        self.current_metric = -value
        self.current_feasible = _is_feasible(self.problem, levels)
        self.last_equilibrium = "converged"
        diagnostics = state.equilibrium_diagnostics
        if diagnostics is not None:
            self.last_inner_iterations = diagnostics.iterations
        if self.current_feasible:
            self.feasible_trials += 1
        else:
            self.infeasible_trials += 1
        if self.scale is None:
            self.scale = max(1.0, abs(value))
        # A monotone bounded transform keeps every valid metric below the
        # failure penalty, even with negative GDP or widely different units.
        self.last_value = float(np.arctan(value / self.scale))
        if value < self.best_value and self.current_feasible:
            self.best = state
            self.best_levels = levels.copy()
            self.best_value = value
            self.report("new_incumbent", level=logging.DEBUG)
        return self.last_value


def _is_feasible(problem: EquilibriumProblem, levels: np.ndarray) -> bool:
    """Check original-unit constraints using the shared feasibility tolerance."""
    try:
        BaseOptimizer._validate_initial_point(
            levels,
            problem.A_ub,
            problem.b_ub,
            problem.A_eq,
            problem.b_eq,
            problem.bounds,
            len(problem.bounds),
        )
    except ValueError:
        return False
    return True


class EquilibriumOptimizer(BaseOptimizer[EquilibriumProblem]):
    """Search continuous building levels using verified household equilibria.

    This is a deterministic local heuristic, without a global-optimum or
    smooth-objective stationarity guarantee. Population varies with employment.
    Numerical equilibrium permits the existing financial warning flags.
    """

    def summary(self) -> pd.DataFrame:
        """Extend the solution report with search and equilibrium diagnostics.

        Evaluation counts exclude final verification, matching ``result``.
        Financial warning counts do not imply equilibrium non-convergence.
        """
        report = super().summary()
        diagnostics = self._require_state().equilibrium_diagnostics
        result = self.result
        if diagnostics is None or result is None:
            raise ValueError("Optimizer has no returned equilibrium to summarize.")
        return report.assign(
            equilibrium_evaluations=int(result.equilibrium_evaluations),
            failed_equilibrium_evaluations=sum(result.equilibrium_failures.values()),
            equilibrium_status=diagnostics.status,
            equilibrium_iterations=diagnostics.iterations,
            loss_buildings_count=len(diagnostics.loss_buildings),
            unaffordable_floor_cells_count=len(diagnostics.unaffordable_floor_cells),
        )

    def compile(
        self,
        scenario: Scenario,
        *,
        initial_wealth: np.ndarray | None = None,
        max_iterations: int = 1000,
        rtol: float = 1e-9,
        atol: float = 1e-8,
    ) -> EquilibriumProblem:
        """Compile shared constraints and freeze the equilibrium evaluation seed.

        Supports ``gdp``, ``gdp_per_capita``, and ``average_wealth``. Household
        consumption is endogenous; imports and exports are fixed external orders.
        Goods-output minima constrain net domestic production.
        """
        if scenario.objective not in ("gdp", "gdp_per_capita", "average_wealth"):
            raise ValueError(
                "EquilibriumOptimizer requires objective='gdp', "
                "'gdp_per_capita', or 'average_wealth'."
            )
        data = self._compile_common(scenario)
        warm_start = self._extract_fixed_zero_bounds(
            self._linear_problem(data, -data.gdp_vector)
        )
        # Exact zero caps also imply fixed variables. Keep the named inequality
        # rows for inspection; only the search coordinates are reduced.
        if warm_start.A_ub is not None and warm_start.b_ub is not None:
            bounds = list(warm_start.bounds)
            for row, rhs in zip(warm_start.A_ub, warm_start.b_ub, strict=True):
                if rhs == 0 and (row >= 0).all():
                    for index in np.flatnonzero(row > 0):
                        bounds[int(index)] = (0.0, 0.0)
            warm_start = replace(warm_start, bounds=tuple(bounds))
        if initial_wealth is None:
            initial_wealth = np.broadcast_to(
                self.model.pop_wealth_init,
                (len(self.model.building_index), len(self.model.pop_index)),
            )
        problem = EquilibriumProblem(
            economy=data.economy,
            scenario=scenario,
            throughput_multipliers=data.throughput_multipliers,
            input_matrix=data.input_matrix,
            output_matrix=data.output_matrix,
            net_matrix=data.net_matrix,
            gdp_vector=data.gdp_vector,
            goods_import=data.goods_import,
            goods_export=data.goods_export,
            A_ub=warm_start.A_ub,
            b_ub=warm_start.b_ub,
            A_eq=warm_start.A_eq,
            b_eq=warm_start.b_eq,
            bounds=warm_start.bounds,
            inequality_slices=warm_start.inequality_slices,
            equality_slices=warm_start.equality_slices,
            warm_start=warm_start,
            initial_wealth=initial_wealth,
            max_iterations=max_iterations,
            rtol=rtol,
            atol=atol,
        )
        self._bind_problem(problem)
        return problem

    def solve(
        self,
        scenario: Scenario,
        *,
        x0: np.ndarray | None = None,
        options: Mapping[str, object] | None = None,
        log_every: int = 100,
        initial_wealth: np.ndarray | None = None,
        max_iterations: int = 1000,
        rtol: float = 1e-9,
        atol: float = 1e-8,
    ) -> EconomyState:
        """Compile and search a scenario, returning the best verified equilibrium.

        ``options`` accepts COBYLA's ``rhobeg``, ``tol``, ``catol``, ``disp``,
        and ``f_target`` plus a hard ``maxiter`` trial limit (default 20,000).
        ``max_iterations`` separately limits each household equilibrium solve.
        ``log_every`` sets the trial interval for INFO progress summaries when
        this module's logger is enabled; it must be a positive integer.
        See ``solve_problem`` for search termination and failure diagnostics.
        """
        problem = self.compile(
            scenario,
            initial_wealth=initial_wealth,
            max_iterations=max_iterations,
            rtol=rtol,
            atol=atol,
        )
        return self.solve_problem(problem, x0=x0, options=options, log_every=log_every)

    def solve_problem(
        self,
        problem: EquilibriumProblem,
        *,
        x0: np.ndarray | None = None,
        options: Mapping[str, object] | None = None,
        log_every: int = 100,
    ) -> EconomyState:
        """Search a compiled problem over a bounded, feasible linear region.

        Return the best feasible equilibrium even on budget exhaustion; inspect
        ``result.success`` and ``result.message`` for search termination.
        ``result.x`` and unscaled ``result.fun`` describe the returned state.
        ``result.solver_result`` retains raw COBYLA output (or ``None`` if it
        was skipped or interrupted by the hard budget). ``nfev`` counts
        distinct consecutive trials, including
        rejected points; ``equilibrium_evaluations`` counts inner solve attempts.
        The initial trial counts against the budget; final verification does not.
        ``equilibrium_failures`` counts failures by status and
        ``last_equilibrium_error`` retains the last failed inner solve.

        Enable ``vic3_analysis.optimize.equilibrium`` at INFO for lifecycle
        events and summaries every ``log_every`` trials (default 100, positive
        integer). DEBUG additionally reports uncached trials and incumbents.
        Logging uses actual maximizing metrics in explicit units, independently
        of native COBYLA ``disp``. Library code never configures log handlers.

        Raises:
            ValueError: For invalid inputs, infeasible/unbounded regions, or no
                feasible converged equilibrium (with diagnostics on ``result``).
            EquilibriumError: If fresh verification of the selected state fails.
        """
        self._bind_problem(problem)
        solver_options, budget = _options(options)
        if (
            isinstance(log_every, (bool, np.bool_))
            or not isinstance(log_every, (int, np.integer))
            or log_every <= 0
        ):
            raise ValueError("log_every must be a positive integer.")
        search = _Search(problem, budget, log_every=int(log_every), phase="preflight")
        search.report("started")
        try:
            return self._solve_problem(problem, x0, solver_options, search)
        except Exception as error:
            search.report("finished", status="failed", message=str(error))
            raise

    def _solve_problem(
        self,
        problem: EquilibriumProblem,
        x0: np.ndarray | None,
        solver_options: dict[str, object],
        search: _Search,
    ) -> EconomyState:
        """Run the numerical search while retaining reporting state on failures."""
        budget = search.budget
        self._check_feasibility_and_boundedness(problem.warm_start, label="Equilibrium")
        search.report("preflight_complete")
        search.phase = "warm_start"
        if x0 is None:
            warm = opt.linprog(
                **problem.warm_start.linprog_args(),
                bounds=problem.bounds,
                method="highs",
            )
            if not warm.success:
                raise ValueError(f"Nominal warm-start failed: {warm.message}")
            x0 = np.asarray(warm.x, dtype=np.float64)
            seed = "nominal_GDP_LP"
        else:
            seed = "provided"
        initial = self._validate_initial_point(
            x0,
            problem.A_ub,
            problem.b_ub,
            problem.A_eq,
            problem.b_eq,
            problem.bounds,
            len(problem.bounds),
        )
        search.report("warm_start_complete", message=f"seed={seed}")
        free = np.array([upper != 0 for _lower, upper in problem.bounds])
        initial[~free] = 0.0
        scales = np.maximum(1.0, np.abs(initial[free]))
        search.phase = "initialization"
        search.report(
            "initialization_started", message=f"free_configurations={int(free.sum())}"
        )
        search.trial(initial)
        raw: opt.OptimizeResult | None = None
        exhausted = False
        if free.any():

            def objective(reduced: np.ndarray) -> float:
                levels = np.zeros(len(initial), dtype=np.float64)
                levels[free] = reduced * scales
                return search.trial(levels)

            def iteration_complete(intermediate_result: opt.OptimizeResult) -> None:
                # COBYLA calls this after initialization, at trust-region steps.
                # It observes progress only; it never evaluates or stops a trial.
                search.phase = "search"

            bounds = [
                (lower / scale, None if upper is None else upper / scale)
                for (lower, upper), scale in zip(
                    (
                        bound
                        for bound, used in zip(problem.bounds, free, strict=True)
                        if used
                    ),
                    scales,
                    strict=True,
                )
            ]
            try:
                if search.nfev >= budget:
                    raise _BudgetReached
                # PRIMA needs n+2 initialization calls; the wrapper enforces the
                # caller's smaller budget without a forced extra evaluation.
                solver_options["maxiter"] = max(budget, int(free.sum()) + 2)
                solved = opt.minimize(
                    objective,
                    initial[free] / scales,
                    method="COBYLA",
                    bounds=bounds,
                    constraints=_constraints(problem, free, scales),
                    callback=iteration_complete,
                    options=solver_options,
                )
                raw = solved
                exhausted = not solved.success and search.nfev >= budget
            except _BudgetReached:
                exhausted = True
        result = opt.OptimizeResult(
            success=not exhausted and (raw is None or raw.success),
            status=3 if exhausted else (0 if raw is None else raw.status),
            message=(
                f"Equilibrium optimization exhausted trial budget maxiter={budget}."
                if exhausted
                else ("All building levels are fixed." if raw is None else raw.message)
            ),
            nfev=search.nfev,
            equilibrium_evaluations=search.equilibrium_evaluations,
            equilibrium_failures=dict(search.failures),
            last_equilibrium_error=search.last_error,
            solver_result=raw,
            x=None if search.best_levels is None else search.best_levels.copy(),
            fun=search.best_value,
        )
        self.result = result
        status = (
            "budget_exhausted"
            if exhausted
            else ("completed" if result.success else "stopped")
        )
        search.report("search_stopped", status=status, message=str(result.message))
        if search.best_levels is None:
            result.success = False
            result.message = (
                f"No feasible converged equilibrium found. {result.message}"
            )
            raise ValueError(result.message) from search.last_error
        # Rebuild baskets and rerun from the original seed, independent of all
        # prior objective calls. A final failure must never return stale success.
        search.phase = "verification"
        search.report("verification_started")
        try:
            verified = problem.evaluate(search.best_levels)
            if (
                not _is_feasible(problem, search.best_levels)
                or not np.array_equal(
                    verified.building_levels,
                    problem._to_building_levels(search.best_levels),
                )
                or not np.isclose(
                    -_metric(verified, problem.scenario.objective),
                    search.best_value,
                    rtol=problem.rtol,
                    atol=problem.atol,
                )
            ):
                raise ValueError("Equilibrium optimizer final verification disagrees.")
        except (EquilibriumError, ValueError):
            result.success = False
            result.message = "Equilibrium optimizer final verification failed."
            raise
        result.fun = -_metric(verified, problem.scenario.objective)
        search.phase = "finished"
        search.report(
            "finished",
            status=status,
            message=f"household_equilibrium=converged; {result.message}",
        )
        self._state = verified
        return verified


def _options(options: Mapping[str, object] | None) -> tuple[dict[str, object], int]:
    """Validate supported COBYLA options before attempting any equilibrium."""
    values: dict[str, object] = {"rhobeg": 1.0, "tol": 1e-4, "catol": 1e-7, "disp": 0}
    supplied = dict(options) if options is not None else {}
    budget = supplied.pop("maxiter", 20_000)
    if (
        isinstance(budget, (bool, np.bool_))
        or not isinstance(budget, (int, np.integer))
        or budget <= 0
    ):
        raise ValueError("options['maxiter'] must be a positive integer.")
    for key, value in supplied.items():
        if key not in (*values, "f_target"):
            raise ValueError(f"Unsupported COBYLA option: {key!r}.")
        if key == "disp":
            if not isinstance(value, (int, np.integer)) or value not in (0, 1, 2, 3):
                raise ValueError("options['disp'] must be an integer from 0 to 3.")
        elif (
            isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))
            or not np.isfinite(value)
            or (key in ("rhobeg", "tol") and value <= 0)
            or (key == "catol" and value < 0)
        ):
            raise ValueError(f"Invalid COBYLA option {key!r}.")
        values[key] = value
    return values, int(budget)


def _constraints(
    problem: EquilibriumProblem, free: np.ndarray, scales: np.ndarray
) -> list[opt.LinearConstraint]:
    """Reduce coordinates and scale rows by their original feasibility units."""
    constraints: list[opt.LinearConstraint] = []
    for matrix, rhs, equality in (
        (problem.A_ub, problem.b_ub, False),
        (problem.A_eq, problem.b_eq, True),
    ):
        if matrix is None or rhs is None:
            continue
        reduced = matrix[:, free] * scales
        keep = (reduced != 0).any(axis=1)
        if not keep.any():
            continue
        normalization = 1.0 + np.abs(rhs[keep])
        normalized_rhs = rhs[keep] / normalization
        lower = normalized_rhs if equality else np.full(len(normalized_rhs), -np.inf)
        constraint = opt.LinearConstraint(reduced[keep] / normalization[:, None])
        constraint.lb = lower
        constraint.ub = normalized_rhs
        constraints.append(constraint)
    return constraints
