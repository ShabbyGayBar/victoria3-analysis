# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Nominal linear-programming compilation and solving."""

import numpy as np
import scipy.optimize as opt

from vic3_analysis.analysis.economy import EconomyState
from vic3_analysis.optimize.base import BaseOptimizer, LinearProblem
from vic3_analysis.optimize.scenario import Scenario


class NominalOptimizer(BaseOptimizer[LinearProblem]):
    """Compile and solve nominal-price scenarios as linear programmes."""

    def compile(self, scenario: Scenario) -> LinearProblem:
        """Compile *scenario* into an inspectable linear problem."""
        if scenario.objective == "gdp_per_capita":
            raise ValueError(
                "NominalOptimizer does not support the nonlinear "
                "gdp_per_capita objective; use MarketOptimizer."
            )
        if scenario.objective == "average_wealth":
            raise ValueError(
                "NominalOptimizer does not support average_wealth; "
                "use EquilibriumOptimizer."
            )
        data = self._compile_common(scenario)
        if scenario.objective == "gdp":
            objective = -data.gdp_vector
        elif scenario.objective == "employment":
            objective = -self.model.employment_vector
        elif scenario.objective == "automation":
            objective = self.model.employment_vector
        elif scenario.objective == "construction_cost":
            objective = self.model.construction_cost_vector
        else:
            raise ValueError(f"Unknown objective: {scenario.objective!r}")
        problem = self._linear_problem(data, objective)
        self._bind_problem(problem)
        return problem

    def solve(self, scenario: Scenario) -> EconomyState:
        """Compile and solve *scenario*, returning its optimal economy state."""
        return self.solve_problem(self.compile(scenario))

    def solve_problem(self, problem: LinearProblem) -> EconomyState:
        """Solve a previously compiled linear problem."""
        self._bind_problem(problem)
        result = opt.linprog(
            **problem.linprog_args(),
            bounds=problem.bounds,
            method="highs",
        )
        if not result.success:
            raise ValueError(f"Optimization failed: {result.message}")
        self.result = result
        state = self._state_from_levels(problem, np.asarray(result.x, dtype=np.float64))
        self._state = state
        return state

    def import_marginals(self) -> np.ndarray | None:
        """Return objective sensitivities to increasing imports by good.

        Values align to the goods index and measure the minimized LP objective
        change per additional imported unit under the goods-balance floor.
        """
        problem = self.problem
        result = self.result
        if problem is None or result is None:
            return None
        row_slice = problem.inequality_slices.get("min_goods_balance")
        if row_slice is None:
            return None
        ineqlin = getattr(result, "ineqlin", None)
        if ineqlin is None:
            return None
        marginals = getattr(ineqlin, "marginals", None)
        if marginals is None:
            return None
        values = np.asarray(marginals, dtype=np.float64)
        stop = row_slice.stop
        if stop is None or values.shape[0] < stop:
            return None
        return values[row_slice].copy()
