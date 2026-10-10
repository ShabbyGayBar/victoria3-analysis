# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""User-facing single-terminal supply-chain analyzer."""

from __future__ import annotations

import numpy as np

from vic3_analysis.analysis.economy import Economy, EconomyState
from vic3_analysis.analysis.supply_chain.graph import (
    allowed_process_mask,
    build_supply_graph,
)
from vic3_analysis.analysis.supply_chain.result import (
    SolverDiagnostics,
    SupplyChainResult,
)
from vic3_analysis.optimize.nominal import NominalOptimizer
from vic3_analysis.optimize.scenario import Scenario


def _readonly(value: np.ndarray) -> np.ndarray:
    result = np.array(value, dtype=np.float64, copy=True)
    result.setflags(write=False)
    return result


def _freeze_state(state: EconomyState) -> EconomyState:
    """Return an `EconomyState` whose arrays are defensive read-only copies."""
    return EconomyState(
        building_levels=_readonly(state.building_levels),
        building_goods_input=_readonly(state.building_goods_input),
        building_goods_output=_readonly(state.building_goods_output),
        imports=_readonly(state.imports),
        exports=_readonly(state.exports),
        market_prices=_readonly(state.market_prices),
        pops=_readonly(state.pops),
        pop_wealth=_readonly(state.pop_wealth),
        pop_balance=_readonly(state.pop_balance),
        pop_needs=_readonly(state.pop_needs),
    )


def _marginals(block: object) -> np.ndarray | None:
    values = getattr(block, "marginals", None)
    if values is None:
        return None
    return np.asarray(values, dtype=np.float64)


class SupplyChainAnalyzer:
    """Compile and analyze one nominal single-terminal production scenario."""

    def __init__(
        self,
        economy: Economy,
        scenario: Scenario,
        terminal_good: str,
        *,
        tolerance: float = 1e-9,
    ) -> None:
        """Configure one nominal analysis without solving it.

        Args:
            economy: Economy containing production, goods, and workforce data.
            scenario: Scenario with exactly one positive production target.
            terminal_good: Good key matching the scenario target.
            tolerance: Positive numerical threshold for active levels and edges.

        Raises:
            ValueError: If the target, objective, terminal good, or tolerance is
                invalid for a version-1 nominal analysis.
        """
        if not np.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("tolerance must be a positive finite number.")
        goods_index = economy.goods_index
        if terminal_good not in goods_index:
            raise ValueError(f"Good '{terminal_good}' not found in goods index.")
        if len(scenario.produce) != 1:
            raise ValueError("Scenario must contain exactly one production target.")
        target_good, target_amount = scenario.produce[0]
        if target_good != terminal_good:
            raise ValueError("terminal_good must match the Scenario production target.")
        try:
            amount = float(target_amount)
        except (TypeError, ValueError) as exc:
            raise ValueError(
                "Production target must be a positive finite number."
            ) from exc
        if not np.isfinite(amount) or amount <= 0:
            raise ValueError("Production target must be a positive finite number.")
        if scenario.objective == "gdp_per_capita":
            raise ValueError(
                "SupplyChainAnalyzer v1 supports nominal objectives only; "
                "gdp_per_capita requires MarketOptimizer."
            )
        self._economy = economy
        self._scenario = scenario
        self._terminal_good = terminal_good
        self._target_quantity = amount
        self._tolerance = float(tolerance)

    def run(self) -> SupplyChainResult:
        """Solve once and return an immutable supply-chain result."""
        optimizer = NominalOptimizer(self._economy)
        problem = optimizer.compile(self._scenario)
        state = _freeze_state(optimizer.solve_problem(problem))
        solver_result = optimizer.result
        if solver_result is None:
            raise RuntimeError("Nominal optimizer returned no solver result.")

        fun = float(solver_result.fun)
        objective_value = (
            -fun if self._scenario.objective in ("gdp", "employment") else fun
        )
        diagnostics = SolverDiagnostics(
            status=int(solver_result.status),
            message=str(solver_result.message),
            objective_value=objective_value,
            inequality_marginals=_marginals(getattr(solver_result, "ineqlin", None)),
            equality_marginals=_marginals(getattr(solver_result, "eqlin", None)),
        )
        allowed = allowed_process_mask(
            self._economy._supply_chain_production,
            self._scenario,
            tolerance=self._tolerance,
        )
        active = state.building_levels > self._tolerance
        prices = state.market_prices
        realized_graph = build_supply_graph(
            production=self._economy._supply_chain_production,
            goods_index=self._economy.goods_index,
            config_index=self._economy.building_index,
            input_matrix=problem.input_matrix,
            output_matrix=problem.output_matrix,
            levels=state.building_levels,
            prices=prices,
            terminal_good=self._terminal_good,
            selected_processes=active,
            allowed_processes=allowed,
            tolerance=self._tolerance,
        )
        allowed_graph = build_supply_graph(
            production=self._economy._supply_chain_production,
            goods_index=self._economy.goods_index,
            config_index=self._economy.building_index,
            input_matrix=problem.input_matrix,
            output_matrix=problem.output_matrix,
            levels=state.building_levels,
            prices=prices,
            terminal_good=self._terminal_good,
            selected_processes=allowed,
            allowed_processes=allowed,
            tolerance=self._tolerance,
        )
        return SupplyChainResult(
            scenario=self._scenario,
            terminal_good=self._terminal_good,
            target_quantity=self._target_quantity,
            problem=problem,
            state=state,
            diagnostics=diagnostics,
            production=self._economy._supply_chain_production,
            goods_index=self._economy.goods_index,
            config_index=self._economy.building_index,
            profession_index=self._economy.pop_index,
            employment_matrix=self._economy.employment_matrix,
            employment_vector=self._economy.employment_vector,
            construction_cost_vector=self._economy.construction_cost_vector,
            arable_land_vector=self._economy.arable_land_vector,
            infrastructure_vector=self._economy.infrastructure_vector,
            realized_graph=realized_graph,
            allowed_graph=allowed_graph,
            tolerance=self._tolerance,
        )
