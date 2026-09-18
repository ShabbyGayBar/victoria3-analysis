"""User-facing single-terminal supply-chain analyzer."""

from __future__ import annotations

from dataclasses import dataclass

import numpy as np
import pandas as pd

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

_METADATA_DEFAULTS: dict[str, str | bool] = {
    "building_group": "",
    "parent_group": "",
    "land_usage": "",
    "is_subsistence": False,
    "discoverable_resource": False,
    "depletable_resource": False,
}


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


@dataclass(frozen=True)
class _EconomySnapshot:
    """Economy metadata shared across analyses in one sweep."""

    production: pd.DataFrame
    goods_index: tuple[str, ...]
    config_index: tuple[str, ...]
    profession_index: tuple[str, ...]
    employment_matrix: np.ndarray
    employment_vector: np.ndarray
    construction_cost_vector: np.ndarray
    arable_land_vector: np.ndarray
    infrastructure_vector: np.ndarray

    @classmethod
    def from_economy(cls, economy: Economy) -> _EconomySnapshot:
        production = economy.df_production.copy(deep=True)
        for column, default in _METADATA_DEFAULTS.items():
            if column not in production.columns:
                production[column] = default
            else:
                production[column] = production[column].fillna(default)
        infrastructure = (
            production["infrastructure_usage_per_level"]
            .fillna(0)
            .to_numpy(dtype=np.float64)
            if "infrastructure_usage_per_level" in production.columns
            else np.zeros(len(production), dtype=np.float64)
        )
        return cls(
            production=production,
            goods_index=tuple(economy.goods_index()),
            config_index=tuple(economy.building_index()),
            profession_index=tuple(economy.pop_index()),
            employment_matrix=_readonly(economy.employment_matrix()),
            employment_vector=_readonly(economy.employment_vector()),
            construction_cost_vector=_readonly(economy.construction_cost_vector()),
            arable_land_vector=_readonly(economy.arable_land_vector()),
            infrastructure_vector=_readonly(infrastructure),
        )


class SupplyChainAnalyzer:
    """Compile and analyze one nominal single-terminal production scenario."""

    def __init__(
        self,
        economy: Economy,
        scenario: Scenario,
        terminal_good: str,
        *,
        tolerance: float = 1e-9,
        _snapshot: _EconomySnapshot | None = None,
    ) -> None:
        """Configure one nominal analysis without solving it.

        Args:
            economy: Economy containing production, goods, and workforce data.
            scenario: Scenario with exactly one positive production target.
            terminal_good: Good key matching the scenario target.
            tolerance: Positive numerical threshold for active levels and edges.
            _snapshot: Internal shared metadata snapshot used by sweeps.

        Raises:
            ValueError: If the target, objective, terminal good, or tolerance is
                invalid for a version-1 nominal analysis.
        """
        if not np.isfinite(tolerance) or tolerance <= 0:
            raise ValueError("tolerance must be a positive finite number.")
        goods_index = economy.goods_index()
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
        self._snapshot = _snapshot or _EconomySnapshot.from_economy(economy)

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
            self._snapshot.production,
            self._scenario,
            tolerance=self._tolerance,
        )
        active = state.building_levels > self._tolerance
        prices = state.market_prices
        realized_graph = build_supply_graph(
            production=self._snapshot.production,
            goods_index=self._snapshot.goods_index,
            config_index=self._snapshot.config_index,
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
            production=self._snapshot.production,
            goods_index=self._snapshot.goods_index,
            config_index=self._snapshot.config_index,
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
            production=self._snapshot.production,
            goods_index=self._snapshot.goods_index,
            config_index=self._snapshot.config_index,
            profession_index=self._snapshot.profession_index,
            employment_matrix=self._snapshot.employment_matrix,
            employment_vector=self._snapshot.employment_vector,
            construction_cost_vector=self._snapshot.construction_cost_vector,
            arable_land_vector=self._snapshot.arable_land_vector,
            infrastructure_vector=self._snapshot.infrastructure_vector,
            realized_graph=realized_graph,
            allowed_graph=allowed_graph,
            tolerance=self._tolerance,
        )
