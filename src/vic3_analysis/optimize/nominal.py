"""
Nominal linear-programming solver for Victoria 3 economies.

`NominalOptimizer` is solely a solver: it wraps
`scipy.optimize.linprog` and solves
`Scenario` formulations over an
`Economy`, returning an
`EconomyState`.

All problem definition (objectives, constraints, throughput bonuses) lives in
`Scenario`; this module only delegates
to scipy with the scenario's ready-made ``linprog_args``.
"""

import scipy.optimize as opt
from scipy.optimize import OptimizeResult

from vic3_analysis.analysis.economy import Economy, EconomyState
from vic3_analysis.optimize.scenario import Scenario


class NominalOptimizer:
    """Solver for `Scenario` formulations over an `Economy`.

    Example::

        state = NominalOptimizer(economy).solve(scenario)

    Attributes:
        model: The wrapped `Economy`.
        result: The `scipy.optimize.OptimizeResult` from the most recent
            `solve` call (``None`` until solved).  Exposed so downstream
            tooling can read constraint marginals (shadow prices); callers
            should not mutate it.
        scenario: The `Scenario` from the most recent `solve` call
            (``None`` until solved).
    """

    model: Economy
    result: OptimizeResult | None
    scenario: Scenario | None

    def __init__(self, model: Economy) -> None:
        """Initialise the solver.

        Args:
            model: The `Economy` to solve scenarios on.
        """
        self.model = model
        self.result = None
        self.scenario = None

    def solve(self, scenario: Scenario) -> EconomyState:
        """Solve a scenario and return the resulting `EconomyState`.

        Delegates to `scipy.optimize.linprog` with the scenario's
        `linprog_args` keyword
        arguments.

        Args:
            scenario: The `Scenario` formulation to solve.

        Returns:
            An `EconomyState` (via `Economy.solve`) built from the
            optimal building-level vector.  The underlying
            `scipy.optimize.OptimizeResult` is also stored on
            `result` (and the scenario on `scenario`) for
            marginal inspection. Economy of scale is disabled because its
            level-dependent throughput is nonlinear and is not represented in
            the linear programme.

        Raises:
            ValueError: If `scipy.optimize.linprog` reports that the
                optimisation failed (infeasible or unbounded).
        """
        if scenario.objective == "gdp_per_capita":
            raise ValueError(
                "NominalOptimizer does not support the nonlinear "
                "gdp_per_capita objective; use MarketOptimizer."
            )
        res = opt.linprog(**scenario.linprog_args(self.model))
        if not res.success:
            raise ValueError(f"Optimization failed: {res.message}")
        self.result = res
        self.scenario = scenario
        return self.model.solve(
            res.x,
            imports=scenario.imports_vector(self.model),
            exports=scenario.exports_vector(self.model),
            throughput_multipliers=scenario.throughput_multipliers(self.model),
            pop_needs=scenario.pop_needs_vector(self.model),
            economy_of_scale_level_cap=0.0,
        )
