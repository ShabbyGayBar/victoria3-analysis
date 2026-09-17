"""Nonlinear market-price optimization compilation and solving."""

from collections.abc import Mapping
from dataclasses import replace
from types import MappingProxyType
from typing import Any, cast

import numpy as np
import scipy.optimize as opt

from vic3_analysis.analysis.economy import Economy, EconomyState
from vic3_analysis.optimize.base import (
    BaseOptimizer,
    ConstraintSlices,
    LinearProblem,
    MarketProblem,
)
from vic3_analysis.optimize.scenario import Scenario


_FEASIBILITY_TOLERANCE = 1e-7


class MarketOptimizer(BaseOptimizer[MarketProblem]):
    """Compile and solve scenarios with endogenous national market prices."""

    def compile(self, scenario: Scenario) -> MarketProblem:
        """Compile *scenario* into an inspectable nonlinear market problem."""
        if scenario.objective not in ("gdp", "gdp_per_capita"):
            raise ValueError(
                "MarketOptimizer requires objective='gdp' or "
                "objective='gdp_per_capita'."
            )
        if scenario.import_limit is not None:
            raise ValueError("MarketOptimizer requires scenario.import_limit=None.")

        data = self._compile_common(scenario)
        warm_start_objective = (
            self.model.employment_vector()
            if scenario.objective == "gdp_per_capita" and scenario.produce
            else -data.gdp_vector
        )
        warm_start = self._extract_fixed_zero_bounds(
            self._linear_problem(data, warm_start_objective)
        )
        employment = self.model.employment_vector()
        economy = self.model

        def objective_terms(levels: np.ndarray) -> tuple[float, np.ndarray]:
            value, gradient = self._value_and_gradient(
                economy,
                levels,
                data.input_matrix,
                data.output_matrix,
                data.net_matrix,
                data.imports,
                data.exports,
                data.pop_needs,
                economy.base_prices(),
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

        problem = MarketProblem(
            economy=data.economy,
            scenario=scenario,
            throughput_multipliers=data.throughput_multipliers,
            input_matrix=data.input_matrix,
            output_matrix=data.output_matrix,
            net_matrix=data.net_matrix,
            gdp_vector=data.gdp_vector,
            imports=data.imports,
            exports=data.exports,
            pop_needs=data.pop_needs,
            A_ub=warm_start.A_ub,
            b_ub=warm_start.b_ub,
            A_eq=warm_start.A_eq,
            b_eq=warm_start.b_eq,
            bounds=warm_start.bounds,
            inequality_slices=warm_start.inequality_slices,
            equality_slices=warm_start.equality_slices,
            objective=objective,
            jacobian=jacobian,
            warm_start=warm_start,
        )
        self._bind_problem(problem)
        return problem

    def solve(
        self,
        scenario: Scenario,
        *,
        x0: np.ndarray | None = None,
        options: Mapping[str, object] | None = None,
    ) -> EconomyState:
        """Compile and solve *scenario* with endogenous market prices."""
        return self.solve_problem(self.compile(scenario), x0=x0, options=options)

    def solve_problem(
        self,
        problem: MarketProblem,
        *,
        x0: np.ndarray | None = None,
        options: Mapping[str, object] | None = None,
    ) -> EconomyState:
        """Solve a previously compiled market problem."""
        self._bind_problem(problem)
        warm_start_problem = problem.warm_start
        self._check_feasibility_and_boundedness(warm_start_problem)
        n_buildings = len(self.model.building_index())

        if x0 is None:
            warm_start = opt.linprog(
                **warm_start_problem.linprog_args(),
                bounds=warm_start_problem.bounds,
                method="highs",
            )
            if not warm_start.success:
                raise ValueError(f"Nominal warm-start failed: {warm_start.message}")
            initial = np.asarray(warm_start.x, dtype=np.float64)
        else:
            initial = self._validate_initial_point(
                x0,
                problem.A_ub,
                problem.b_ub,
                problem.A_eq,
                problem.b_eq,
                problem.bounds,
                n_buildings,
            )

        constraints: list[opt.LinearConstraint] = []
        if problem.A_ub is not None and problem.b_ub is not None:
            linear_constraint = cast(Any, opt.LinearConstraint)
            constraints.append(linear_constraint(problem.A_ub, -np.inf, problem.b_ub))
        if problem.A_eq is not None and problem.b_eq is not None:
            linear_constraint = cast(Any, opt.LinearConstraint)
            constraints.append(
                linear_constraint(problem.A_eq, problem.b_eq, problem.b_eq)
            )

        result = opt.minimize(
            problem.objective,
            initial,
            jac=problem.jacobian,
            method="SLSQP",
            bounds=problem.bounds,
            constraints=constraints,
            options=dict(options) if options is not None else None,
        )
        if not result.success:
            raise ValueError(f"Market optimization failed: {result.message}")

        self.result = result
        return self._state_from_levels(
            problem,
            np.asarray(result.x, dtype=np.float64),
            method="market",
        )

    @staticmethod
    def _extract_fixed_zero_bounds(problem: LinearProblem) -> LinearProblem:
        """Turn non-negative zero-sum equalities into fixed-zero bounds."""
        if problem.A_eq is None or problem.b_eq is None:
            return problem
        bounds = list(problem.bounds)
        keep = np.ones(len(problem.b_eq), dtype=bool)
        for row_index, (row, rhs) in enumerate(
            zip(problem.A_eq, problem.b_eq, strict=True)
        ):
            nonzero = np.flatnonzero(row)
            same_sign = (row[nonzero] > 0).all() or (row[nonzero] < 0).all()
            if abs(rhs) <= _FEASIBILITY_TOLERANCE and len(nonzero) > 0 and same_sign:
                for variable in nonzero:
                    bounds[int(variable)] = (0.0, 0.0)
                keep[row_index] = False

        remaining_A_eq = problem.A_eq[keep]
        remaining_b_eq = problem.b_eq[keep]
        slices = MarketOptimizer._retained_slices(problem.equality_slices, keep)
        return replace(
            problem,
            A_eq=remaining_A_eq if len(remaining_A_eq) > 0 else None,
            b_eq=remaining_b_eq if len(remaining_b_eq) > 0 else None,
            bounds=tuple(bounds),
            equality_slices=slices,
        )

    @staticmethod
    def _retained_slices(
        slices: ConstraintSlices, keep: np.ndarray
    ) -> ConstraintSlices:
        """Map named equality slices after fixed-zero rows are removed."""
        retained: dict[str, slice] = {}
        for name, row_slice in slices.items():
            start = 0 if row_slice.start is None else row_slice.start
            stop = len(keep) if row_slice.stop is None else row_slice.stop
            block_keep = keep[start:stop]
            count = int(block_keep.sum())
            if count == 0:
                continue
            new_start = int(keep[:start].sum())
            retained[name] = slice(new_start, new_start + count)
        return MappingProxyType(retained)

    @staticmethod
    def _check_feasibility_and_boundedness(problem: LinearProblem) -> None:
        """Reject infeasible or unbounded linear scenario regions."""
        n_buildings = len(problem.bounds)
        boundedness = opt.linprog(
            -np.ones(n_buildings, dtype=np.float64),
            A_ub=problem.A_ub,
            b_ub=problem.b_ub,
            A_eq=problem.A_eq,
            b_eq=problem.b_eq,
            bounds=problem.bounds,
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
        bounds: tuple[tuple[float, float | None], ...],
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

    @staticmethod
    def _value_and_gradient(
        economy: Economy,
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
        prices = economy.market_prices(buy_orders, sell_orders)
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
        gradient = (gdp_gradient * population - gdp * employment) / population**2
        return value, gradient

    @staticmethod
    def _price_derivatives(
        base_prices: np.ndarray,
        buy_orders: np.ndarray,
        sell_orders: np.ndarray,
    ) -> tuple[np.ndarray, np.ndarray]:
        """Return deterministic piecewise derivatives of market prices."""
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
