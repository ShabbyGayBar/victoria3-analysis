# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Equilibrium searches over fixed supply-chain recipes."""

from __future__ import annotations

import warnings
from collections.abc import Mapping
from dataclasses import dataclass, field, replace

import numpy as np
import pandas as pd

from vic3_analysis.analysis.economy import Economy, EconomyState
from vic3_analysis.optimize.base import Bounds, _readonly_array
from vic3_analysis.optimize.equilibrium import (
    EquilibriumOptimizer,
    EquilibriumProblem,
    _is_feasible,
)
from vic3_analysis.optimize.scenario import Scenario


def _to_building_levels(matrix: np.ndarray, chain_levels: np.ndarray) -> np.ndarray:
    """Map a finite nonnegative chain vector, rejecting numerical overflow."""
    levels = np.asarray(chain_levels, dtype=np.float64)
    if levels.shape != (matrix.shape[1],):
        raise ValueError("chain_levels must be aligned to chain_index.")
    if not np.isfinite(levels).all() or (levels < 0).any():
        raise ValueError("chain_levels must contain finite non-negative values.")
    with np.errstate(over="ignore", invalid="ignore"):
        buildings = matrix @ levels
    if not np.isfinite(buildings).all():
        raise ValueError("Transformed building levels must be finite.")
    return buildings


@dataclass(frozen=True, kw_only=True)
class SupplyChainEquilibriumProblem(EquilibriumProblem):
    """Chain-coordinate constraints with building-coordinate economic accounting.

    ``bounds``, constraint columns, and ``warm_start`` decision coefficients
    follow ``chain_index``. Production matrices and wealth retain the
    original economy indexes. Physical evaluation delegates to ``building_problem``.
    """

    chain_index: tuple[str, ...]
    chain_matrix: np.ndarray = field(repr=False, compare=False)
    building_problem: EquilibriumProblem = field(repr=False, compare=False)
    _owner: object = field(default_factory=object, repr=False, compare=False)

    def __post_init__(self) -> None:
        """Snapshot the chain mapping against the retained physical problem."""
        super().__post_init__()
        chains = tuple(self.chain_index)
        if not chains or any(not isinstance(key, str) or not key for key in chains):
            raise ValueError("chain_index must contain nonempty string labels.")
        if len(set(chains)) != len(chains):
            raise ValueError("chain_index must contain unique labels.")
        matrix = _readonly_array(self.chain_matrix)
        if matrix.shape != (len(self.economy.building_index), len(chains)):
            raise ValueError(
                "chain_matrix must match building configurations and chains."
            )
        if not np.isfinite(matrix).all() or (matrix < 0).any():
            raise ValueError(
                "chain_matrix must contain finite non-negative coefficients."
            )
        if not (matrix > 0).any(axis=0).all():
            raise ValueError("Every chain must have at least one nonzero coefficient.")
        object.__setattr__(self, "chain_index", chains)
        object.__setattr__(self, "chain_matrix", matrix)
        if self.building_problem.economy is not self.economy:
            raise ValueError("building_problem belongs to a different Economy.")
        if len(self.bounds) != len(chains):
            raise ValueError("bounds must match the chain index.")

    def to_building_levels(self, chain_levels: np.ndarray) -> np.ndarray:
        """Map chain coordinates using this problem's immutable coefficients."""
        return _to_building_levels(self.chain_matrix, chain_levels)

    def evaluate(self, levels: np.ndarray) -> EconomyState:
        """Solve equilibrium after transforming a nonnegative chain vector."""
        return self.building_problem.evaluate(self.to_building_levels(levels))

    def _to_building_levels(self, levels: np.ndarray) -> np.ndarray:
        """Map chain coordinates for the shared final verification."""
        return self.to_building_levels(levels)


class SupplyChainEquilibriumOptimizer(EquilibriumOptimizer):
    """Optimize nonnegative chain levels using the existing equilibrium search.

    ``x0`` and ``result.x`` contain chain levels. Returned states and
    ``result.building_levels`` contain the recipe matrix times ``result.x``. Fixed
    recipes restrict the search space; they do not guarantee financial viability.
    """

    def __init__(self, economy: Economy, df_building_levels: pd.DataFrame) -> None:
        """Snapshot a production-unit-by-chain DataFrame for an economy.

        DataFrame rows are aligned by configuration key to the economy;
        all-NaN columns are skipped with a warning. Shared configurations receive
        the sum of chain contributions, without normalization of coefficients.
        """
        super().__init__(economy)
        frame = self.validate_building_levels(
            df_building_levels, building_index=tuple(economy.building_index)
        )
        self._chain_index = tuple(frame.columns)
        self._chain_matrix = _readonly_array(frame.to_numpy(dtype=np.float64))
        self._owner = object()

    def summary(self) -> pd.DataFrame:
        """Add the recipe count to the report of the verified building state.

        ``chain_count`` counts recipe columns; ``configuration_count`` counts
        building configurations. Economy metrics use mapped building levels.
        """
        return super().summary().assign(chain_count=len(self.chain_index))

    @staticmethod
    def validate_building_levels(
        frame: pd.DataFrame,
        *,
        building_index: tuple[str, ...],
    ) -> pd.DataFrame:
        """Validate, align, and copy recipes, warning when failed columns are skipped.

        Rows must match ``building_index`` exactly; column order is preserved.
        All-NaN columns are omitted. Each remaining recipe must have finite,
        nonnegative coefficients and at least one positive coefficient. Returned
        float coefficients retain the caller's units without normalization.
        """
        buildings = tuple(building_index)
        rows = tuple(frame.index)
        columns = tuple(frame.columns)
        for name, labels in (
            ("building_index", buildings),
            ("DataFrame index", rows),
            ("DataFrame columns", columns),
        ):
            if any(not isinstance(key, str) or not key for key in labels):
                raise ValueError(f"{name} must contain nonempty string labels.")
            if len(set(labels)) != len(labels):
                raise ValueError(f"{name} must contain unique labels.")
        if not buildings or set(rows) != set(buildings):
            raise ValueError("DataFrame index must match building_index exactly.")
        failed = frame.isna().all(axis=0)
        skipped = [key for key, missing in zip(columns, failed, strict=True) if missing]
        if skipped:
            warnings.warn(
                "Skipping failed supply-chain recipes containing only NaN: "
                + ", ".join(skipped),
                UserWarning,
                stacklevel=2,
            )
        chains = tuple(key for key in columns if key not in skipped)
        if not chains:
            raise ValueError("No usable supply-chain recipes remain.")
        try:
            matrix = frame.loc[list(buildings), list(chains)].to_numpy(
                dtype=np.float64, copy=True
            )
        except (TypeError, ValueError) as exc:
            raise ValueError("matrix must contain numeric coefficients.") from exc
        if not np.isfinite(matrix).all() or (matrix < 0).any():
            raise ValueError("matrix must contain finite non-negative coefficients.")
        if not (matrix > 0).any(axis=0).all():
            raise ValueError("Every chain must have at least one nonzero coefficient.")
        return pd.DataFrame(
            matrix, index=pd.Index(buildings, name="config"), columns=chains
        )

    @property
    def chain_index(self) -> tuple[str, ...]:
        """Return surviving recipe labels in chain-vector order."""
        return self._chain_index

    @property
    def df_building_levels(self) -> pd.DataFrame:
        """Return an independent copy of the aligned production-unit-by-chain matrix."""
        return pd.DataFrame(
            self._chain_matrix.copy(),
            index=pd.Index(self.model.building_index, name="config"),
            columns=self.chain_index,
        )

    def to_building_levels(self, chain_levels: np.ndarray) -> np.ndarray:
        """Map a finite nonnegative chain vector to building configurations."""
        return _to_building_levels(self._chain_matrix, chain_levels)

    def compile(
        self,
        scenario: Scenario,
        *,
        initial_wealth: np.ndarray | None = None,
        subsidize_operating_losses: bool = True,
        max_iterations: int = 1000,
        rtol: float = 1e-9,
        atol: float = 1e-8,
    ) -> SupplyChainEquilibriumProblem:
        """Compile building constraints and the nominal warm start into chains."""
        building = super().compile(
            scenario,
            initial_wealth=initial_wealth,
            subsidize_operating_losses=subsidize_operating_losses,
            max_iterations=max_iterations,
            rtol=rtol,
            atol=atol,
        )
        matrix = self._chain_matrix
        A_ub = None if building.A_ub is None else building.A_ub @ matrix
        A_eq = None if building.A_eq is None else building.A_eq @ matrix
        b_ub = building.b_ub
        slices = dict(building.inequality_slices)
        bounds: Bounds = tuple((0.0, None) for _ in self.chain_index)
        blocked = np.zeros(len(bounds), dtype=bool)
        rows: list[np.ndarray] = []
        rhs: list[float] = []
        for row, (lower, upper) in zip(matrix, building.bounds, strict=True):
            if upper == 0:
                blocked |= row > 0
            elif upper is not None:
                rows.append(row)
                rhs.append(upper)
            if lower > 0:
                rows.append(-row)
                rhs.append(-lower)
        if rows:
            start = 0 if b_ub is None else len(b_ub)
            extra = np.stack(rows)
            A_ub = extra if A_ub is None else np.vstack((A_ub, extra))
            b_ub = np.asarray(rhs) if b_ub is None else np.concatenate((b_ub, rhs))
            slices["building_bounds"] = slice(start, start + len(rhs))
        bounds = tuple((0.0, 0.0 if used else None) for used in blocked)
        warm = self._extract_fixed_zero_bounds(
            replace(
                building.warm_start,
                A_ub=A_ub,
                b_ub=b_ub,
                A_eq=A_eq,
                bounds=bounds,
                inequality_slices=slices,
                objective_vector=matrix.T @ building.warm_start.objective_vector,
            )
        )
        problem = SupplyChainEquilibriumProblem(
            economy=building.economy,
            scenario=building.scenario,
            throughput_multipliers=building.throughput_multipliers,
            input_matrix=building.input_matrix,
            output_matrix=building.output_matrix,
            net_matrix=building.net_matrix,
            gdp_vector=building.gdp_vector,
            goods_import=building.goods_import,
            goods_export=building.goods_export,
            A_ub=warm.A_ub,
            b_ub=warm.b_ub,
            A_eq=warm.A_eq,
            b_eq=warm.b_eq,
            bounds=warm.bounds,
            inequality_slices=warm.inequality_slices,
            equality_slices=warm.equality_slices,
            warm_start=warm,
            initial_wealth=building.initial_wealth,
            subsidize_operating_losses=building.subsidize_operating_losses,
            max_iterations=building.max_iterations,
            rtol=building.rtol,
            atol=building.atol,
            chain_index=self.chain_index,
            chain_matrix=matrix,
            _owner=self._owner,
            building_problem=building,
        )
        self._bind_problem(problem)
        return problem

    def solve_problem(
        self,
        problem: EquilibriumProblem,
        *,
        x0: np.ndarray | None = None,
        options: Mapping[str, object] | None = None,
        log_every: int = 100,
    ) -> EconomyState:
        """Search chain coordinates and verify the original building constraints."""
        if not isinstance(problem, SupplyChainEquilibriumProblem):
            raise TypeError("Expected a SupplyChainEquilibriumProblem.")
        if (
            problem._owner is not self._owner
            or problem.chain_index != self.chain_index
            or not np.array_equal(problem.chain_matrix, self._chain_matrix)
        ):
            raise ValueError(
                "Compiled problem belongs to a different supply-chain optimizer or recipes."
            )
        try:
            state = super().solve_problem(
                problem, x0=x0, options=options, log_every=log_every
            )
        finally:
            if self.result is not None:
                self.result.building_levels = (
                    None
                    if self.result.x is None
                    else problem.to_building_levels(self.result.x)
                )
        if not _is_feasible(problem.building_problem, state.building_levels):
            self._state = None
            if self.result is not None:
                self.result.success = False
                self.result.message = (
                    "Supply-chain final building feasibility check failed."
                )
            raise ValueError("Supply-chain final building feasibility check failed.")
        return state
