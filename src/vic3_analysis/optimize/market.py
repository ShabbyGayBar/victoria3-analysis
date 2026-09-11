"""Nonlinear market-price optimisation for Victoria 3 economies.

The market solver keeps the scenario's linear production constraints, but
prices are derived from the resulting buy and sell orders.  SLSQP is used for
the resulting piecewise-smooth GDP objective.
"""

from collections.abc import Mapping
from typing import Any, cast

import numpy as np
import scipy.optimize as opt
from scipy.optimize import OptimizeResult

from vic3_analysis.analysis.economy import Economy, EconomyState
from vic3_analysis.optimize.scenario import LinprogArgs, Scenario


_FEASIBILITY_TOLERANCE = 1e-7


class MarketOptimizer:
    """Maximise market-price GDP or GDP per capita for a :class:`Scenario`.

    ``MarketOptimizer`` deliberately keeps the economy-of-scale effect out of
    the optimisation.  Scenario throughput bonuses are fixed and are included
    in the goods-flow matrices used by both the objective and final state.
    Imports, exports, and population needs are exogenous order context: they
    shift prices but are not included in ``EconomyState.gdp_weekly``'s net
    building output.
    """

    model: Economy
    result: OptimizeResult | None
    scenario: Scenario | None

    def __init__(self, model: Economy) -> None:
        """Initialise the solver for *model*."""
        self.model = model
        self.result = None
        self.scenario = None

    def solve(
        self,
        scenario: Scenario,
        *,
        x0: np.ndarray | None = None,
        options: Mapping[str, object] | None = None,
    ) -> EconomyState:
        """Solve *scenario* with endogenous national market prices.

        Args:
            scenario: The scenario to optimise. Its objective must be
                ``"gdp"`` or ``"gdp_per_capita"`` and its import limit must
                be ``None``; the latter leaves imports as explicit
                price-context orders.
            x0: Optional feasible initial building-level vector.  When
                omitted, a nominal GDP LP solution is used as a warm start.
            options: Optional options passed to SciPy's SLSQP implementation.

        Returns:
            The final market-price :class:`EconomyState`.

        Raises:
            ValueError: If the scenario is unsupported, the linear feasible
                region is infeasible or unbounded, the initial point is
                invalid, or SLSQP does not report success.
        """
        if scenario.objective not in ("gdp", "gdp_per_capita"):
            raise ValueError(
                "MarketOptimizer requires objective='gdp' or "
                "objective='gdp_per_capita'."
            )
        if scenario.import_limit is not None:
            raise ValueError("MarketOptimizer requires scenario.import_limit=None.")

        n_buildings = len(self.model.building_index())
        if scenario.objective == "gdp":
            lp_args = scenario.linprog_args(self.model)
        else:
            A_ub, b_ub = scenario.inequality_constraints(self.model)
            A_eq, b_eq = scenario.equality_constraints(self.model)
            warm_start_objective = (
                self.model.employment_vector()
                if scenario.produce
                else -scenario.gdp_vector(self.model)
            )
            lp_args = LinprogArgs(
                c=warm_start_objective,
                A_ub=A_ub,
                b_ub=b_ub,
                A_eq=A_eq,
                b_eq=b_eq,
            )
        lp_args, bounds = self._extract_fixed_zero_bounds(lp_args, n_buildings)
        self._check_feasibility_and_boundedness(lp_args, bounds, n_buildings)

        if x0 is None:
            warm_start = opt.linprog(
                **lp_args,
                bounds=bounds,
                method="highs",
            )
            if not warm_start.success:
                raise ValueError(f"Nominal warm-start failed: {warm_start.message}")
            initial = np.asarray(warm_start.x, dtype=np.float64)
        else:
            initial = self._validate_initial_point(
                x0,
                lp_args["A_ub"],
                lp_args["b_ub"],
                lp_args["A_eq"],
                lp_args["b_eq"],
                bounds,
                n_buildings,
            )

        input_matrix = scenario.goods_input_matrix(self.model)
        output_matrix = scenario.goods_output_matrix(self.model)
        net_matrix = output_matrix - input_matrix
        imports = scenario.imports_vector(self.model)
        exports = scenario.exports_vector(self.model)
        pop_needs = scenario.pop_needs_vector(self.model)
        base_prices = self.model.base_prices()
        employment = self.model.employment_vector()

        def objective_terms(levels: np.ndarray) -> tuple[float, np.ndarray]:
            value, gradient = self._value_and_gradient(
                levels,
                input_matrix,
                output_matrix,
                net_matrix,
                imports,
                exports,
                pop_needs,
                base_prices,
            )
            if scenario.objective == "gdp_per_capita":
                return self._per_capita_value_and_gradient(
                    value, gradient, levels, employment
                )
            return value, gradient

        def objective(levels: np.ndarray) -> float:
            value, _gradient = objective_terms(levels)
            return -value

        def jacobian(levels: np.ndarray) -> np.ndarray:
            _value, gradient = objective_terms(levels)
            return -gradient

        constraints: list[opt.LinearConstraint] = []
        if lp_args["A_ub"] is not None and lp_args["b_ub"] is not None:
            linear_constraint = cast(Any, opt.LinearConstraint)
            constraints.append(
                linear_constraint(lp_args["A_ub"], -np.inf, lp_args["b_ub"])
            )
        if lp_args["A_eq"] is not None and lp_args["b_eq"] is not None:
            linear_constraint = cast(Any, opt.LinearConstraint)
            constraints.append(
                linear_constraint(lp_args["A_eq"], lp_args["b_eq"], lp_args["b_eq"])
            )

        result = opt.minimize(
            objective,
            initial,
            jac=jacobian,
            method="SLSQP",
            bounds=bounds,
            constraints=constraints,
            options=dict(options) if options is not None else None,
        )
        if not result.success:
            raise ValueError(f"Market optimization failed: {result.message}")

        self.result = result
        self.scenario = scenario
        return self.model.solve(
            np.asarray(result.x, dtype=np.float64),
            method="market",
            imports=imports,
            exports=exports,
            throughput_multipliers=scenario.throughput_multipliers(self.model),
            pop_needs=pop_needs,
            economy_of_scale_level_cap=0.0,
        )

    @staticmethod
    def _extract_fixed_zero_bounds(
        lp_args: LinprogArgs,
        n_buildings: int,
    ) -> tuple[LinprogArgs, list[tuple[float, float | None]]]:
        """Turn non-negative zero-sum equalities into fixed-zero bounds."""
        bounds: list[tuple[float, float | None]] = [(0.0, None)] * n_buildings
        A_eq = lp_args["A_eq"]
        b_eq = lp_args["b_eq"]
        if A_eq is None or b_eq is None:
            return lp_args, bounds

        keep = np.ones(len(b_eq), dtype=bool)
        for row_index, (row, rhs) in enumerate(zip(A_eq, b_eq)):
            nonzero = np.flatnonzero(row)
            same_sign = (row[nonzero] > 0).all() or (row[nonzero] < 0).all()
            if abs(rhs) <= _FEASIBILITY_TOLERANCE and len(nonzero) > 0 and same_sign:
                for variable in nonzero:
                    bounds[int(variable)] = (0.0, 0.0)
                keep[row_index] = False

        remaining_A_eq = A_eq[keep]
        remaining_b_eq = b_eq[keep]
        reduced = LinprogArgs(
            c=lp_args["c"],
            A_ub=lp_args["A_ub"],
            b_ub=lp_args["b_ub"],
            A_eq=remaining_A_eq if len(remaining_A_eq) > 0 else None,
            b_eq=remaining_b_eq if len(remaining_b_eq) > 0 else None,
        )
        return reduced, bounds

    @staticmethod
    def _check_feasibility_and_boundedness(
        lp_args: LinprogArgs,
        bounds: list[tuple[float, float | None]],
        n_buildings: int,
    ) -> None:
        """Reject infeasible or unbounded linear scenario regions."""
        boundedness = opt.linprog(
            -np.ones(n_buildings, dtype=np.float64),
            A_ub=lp_args["A_ub"],
            b_ub=lp_args["b_ub"],
            A_eq=lp_args["A_eq"],
            b_eq=lp_args["b_eq"],
            bounds=bounds,
            method="highs",
        )
        if boundedness.success:
            return
        if boundedness.status == 2:
            raise ValueError(
                f"Market optimization is infeasible: {boundedness.message}"
            )
        if boundedness.status == 3:
            raise ValueError(
                "Market optimization requires a bounded feasible region: "
                f"{boundedness.message}"
            )
        raise ValueError(f"Market preflight failed: {boundedness.message}")

    @staticmethod
    def _validate_initial_point(
        x0: np.ndarray,
        A_ub: np.ndarray | None,
        b_ub: np.ndarray | None,
        A_eq: np.ndarray | None,
        b_eq: np.ndarray | None,
        bounds: list[tuple[float, float | None]],
        n_buildings: int,
    ) -> np.ndarray:
        """Validate and copy a user-provided feasible initial point."""
        initial = np.asarray(x0, dtype=np.float64)
        if initial.ndim != 1 or initial.shape[0] != n_buildings:
            raise ValueError(
                "x0 must be a 1-D vector aligned to building configurations."
            )
        if not np.isfinite(initial).all():
            raise ValueError("x0 must contain only finite values.")
        if (initial < 0).any():
            raise ValueError("x0 must contain only non-negative values.")
        for value, (_lower, upper) in zip(initial, bounds, strict=True):
            if upper is not None and value > upper + _FEASIBILITY_TOLERANCE:
                raise ValueError("x0 violates scenario variable bounds.")
        if A_ub is not None and b_ub is not None:
            residual = A_ub @ initial - b_ub
            if not np.all(residual <= _FEASIBILITY_TOLERANCE * (1 + np.abs(b_ub))):
                raise ValueError("x0 violates scenario inequality constraints.")
        if A_eq is not None and b_eq is not None:
            residual = A_eq @ initial - b_eq
            if not np.all(
                np.abs(residual) <= _FEASIBILITY_TOLERANCE * (1 + np.abs(b_eq))
            ):
                raise ValueError("x0 violates scenario equality constraints.")
        return initial.copy()

    def _value_and_gradient(
        self,
        levels: np.ndarray,
        input_matrix: np.ndarray,
        output_matrix: np.ndarray,
        net_matrix: np.ndarray,
        imports: np.ndarray,
        exports: np.ndarray,
        pop_needs: np.ndarray,
        base_prices: np.ndarray,
    ) -> tuple[float, np.ndarray]:
        """Return market GDP and its building-level gradient."""
        building_inputs = levels @ input_matrix
        building_outputs = levels @ output_matrix
        buy_orders = building_inputs + exports + pop_needs
        sell_orders = building_outputs + imports
        prices = self.model.market_prices(buy_orders, sell_orders)
        dp_buy, dp_sell = MarketOptimizer._price_derivatives(
            base_prices, buy_orders, sell_orders
        )
        net_goods = building_outputs - building_inputs
        value = float(np.dot(net_goods, prices))
        gradient = net_matrix @ prices
        gradient += input_matrix @ (net_goods * dp_buy)
        gradient += output_matrix @ (net_goods * dp_sell)
        return value, gradient

    @staticmethod
    def _per_capita_value_and_gradient(
        gdp: float,
        gdp_gradient: np.ndarray,
        levels: np.ndarray,
        employment: np.ndarray,
    ) -> tuple[float, np.ndarray]:
        """Return GDP per capita and its building-level gradient."""
        population = float(np.dot(levels, employment))
        if population <= 0:
            return 0.0, np.zeros_like(gdp_gradient)
        value = gdp / population
        gradient = (
            gdp_gradient * population - gdp * employment
        ) / population**2
        return value, gradient

    @staticmethod
    def _price_derivatives(
        base_prices: np.ndarray, buy_orders: np.ndarray, sell_orders: np.ndarray
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return deterministic piecewise derivatives of market prices.

        At clipping boundaries and at the discontinuous ``(0, 0)`` branch,
        the capped-side/zero derivative is selected for numerical stability.
        """
        dp_buy = np.zeros_like(base_prices)
        dp_sell = np.zeros_like(base_prices)
        positive = (buy_orders > 0) & (sell_orders > 0)
        buy_dominant = positive & (buy_orders > sell_orders)
        buy_interior = buy_dominant & (buy_orders < 2 * sell_orders)
        dp_buy[buy_interior] = (
            0.75 * base_prices[buy_interior] / sell_orders[buy_interior]
        )
        dp_sell[buy_interior] = (
            -0.75
            * base_prices[buy_interior]
            * buy_orders[buy_interior]
            / sell_orders[buy_interior] ** 2
        )
        sell_dominant = positive & (sell_orders > buy_orders)
        sell_interior = sell_dominant & (sell_orders < 2 * buy_orders)
        dp_buy[sell_interior] = (
            0.75
            * base_prices[sell_interior]
            * sell_orders[sell_interior]
            / buy_orders[sell_interior] ** 2
        )
        dp_sell[sell_interior] = (
            -0.75 * base_prices[sell_interior] / buy_orders[sell_interior]
        )
        equal = positive & (buy_orders == sell_orders)
        dp_buy[equal] = 0.75 * base_prices[equal] / buy_orders[equal]
        dp_sell[equal] = -0.75 * base_prices[equal] / buy_orders[equal]
        return dp_buy, dp_sell
