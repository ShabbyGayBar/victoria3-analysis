"""
Nominal linear-programming solver for Victoria 3 economies.

:class:`NominalOptimizer` is solely a solver: it wraps
:func:`scipy.optimize.linprog` and solves
:class:`~vic3_analysis.optimize.scenario.Scenario` formulations over an
:class:`~vic3_analysis.analysis.economy.Economy`, returning an
:class:`~vic3_analysis.analysis.economy.EconomyState`.

All problem definition (objectives, constraints, throughput bonuses) lives in
:class:`~vic3_analysis.optimize.scenario.Scenario`; this module only delegates
to scipy with the scenario's ready-made ``linprog_args``.
"""

import scipy.optimize as opt
from scipy.optimize import OptimizeResult

from vic3_analysis.analysis.economy import Economy, EconomyState
from vic3_analysis.optimize.scenario import Scenario


class NominalOptimizer:
    """Solver for :class:`Scenario` formulations over an :class:`Economy`.

    Example::

        state = NominalOptimizer(economy).solve(scenario)

    Attributes:
        model: The wrapped :class:`Economy`.
        result: The :class:`scipy.optimize.OptimizeResult` from the most recent
            :meth:`solve` call (``None`` until solved).  Exposed so downstream
            tooling can read constraint marginals (shadow prices); callers
            should not mutate it.
        scenario: The :class:`Scenario` from the most recent :meth:`solve` call
            (``None`` until solved).
    """

    model: Economy
    result: OptimizeResult | None
    scenario: Scenario | None

    def __init__(self, model: Economy) -> None:
        """Initialise the solver.

        Args:
            model: The :class:`Economy` to solve scenarios on.
        """
        self.model = model
        self.result = None
        self.scenario = None

    def solve(self, scenario: Scenario) -> EconomyState:
        """Solve a scenario and return the resulting :class:`EconomyState`.

        Delegates to :func:`scipy.optimize.linprog` with the scenario's
        :meth:`~vic3_analysis.optimize.scenario.Scenario.linprog_args` keyword
        arguments.

        Args:
            scenario: The :class:`Scenario` formulation to solve.

        Returns:
            An :class:`EconomyState` (via :meth:`Economy.solve`) built from the
            optimal building-level vector.  The underlying
            :class:`scipy.optimize.OptimizeResult` is also stored on
            :attr:`result` (and the scenario on :attr:`scenario`) for
            marginal inspection. Economy of scale is disabled because its
            level-dependent throughput is nonlinear and is not represented in
            the linear programme.

        Raises:
            ValueError: If :func:`scipy.optimize.linprog` reports that the
                optimisation failed (infeasible or unbounded).
        """
        res = opt.linprog(**scenario.linprog_args(self.model))
        if not res.success:
            raise ValueError(f"Optimization failed: {res.message}")
        self.result = res
        self.scenario = scenario
        return self.model.solve(
            res.x,
            throughput_multipliers=scenario.throughput_multipliers(self.model),
            economy_of_scale_level_cap=0.0,
        )
