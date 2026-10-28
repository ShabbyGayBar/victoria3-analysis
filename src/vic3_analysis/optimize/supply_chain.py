# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Equilibrium searches in a fixed basis of complete supply-chain recipes."""

from collections.abc import Mapping
from dataclasses import dataclass, field, replace

import numpy as np

from vic3_analysis.analysis.economy import Economy, EconomyState
from vic3_analysis.optimize.base import Bounds, _readonly_array
from vic3_analysis.optimize.equilibrium import (
    EquilibriumOptimizer,
    EquilibriumProblem,
    _is_feasible,
)
from vic3_analysis.optimize.scenario import Scenario


@dataclass(frozen=True, eq=False)
class SupplyChainBasis:
    """Labeled, immutable coefficients for ``building_levels = matrix @ levels``.

    Rows follow an Economy's building-configuration index; columns follow
    ``chain_index``. Units are defined by the caller's recipes, without implicit
    normalization. Shared configurations receive the sum of chain contributions.
    """

    building_index: tuple[str, ...]
    chain_index: tuple[str, ...]
    matrix: np.ndarray = field(repr=False)

    def __post_init__(self) -> None:
        """Own the coefficients and require distinct labels and usable recipes."""
        for name in ("building_index", "chain_index"):
            labels = tuple(getattr(self, name))
            if not labels or any(not isinstance(key, str) or not key for key in labels):
                raise ValueError(f"{name} must contain nonempty string labels.")
            if len(set(labels)) != len(labels):
                raise ValueError(f"{name} must contain unique labels.")
            object.__setattr__(self, name, labels)
        matrix = _readonly_array(self.matrix)
        if matrix.shape != (len(self.building_index), len(self.chain_index)):
            raise ValueError(
                "matrix must match building_index rows and chain_index columns."
            )
        if not np.isfinite(matrix).all() or (matrix < 0).any():
            raise ValueError("matrix must contain finite non-negative coefficients.")
        if not (matrix > 0).any(axis=0).all():
            raise ValueError("Every chain must have at least one nonzero coefficient.")
        object.__setattr__(self, "matrix", matrix)

    def to_building_levels(self, chain_levels: np.ndarray) -> np.ndarray:
        """Map a finite nonnegative chain vector to building configurations."""
        levels = np.asarray(chain_levels, dtype=np.float64)
        if levels.shape != (len(self.chain_index),):
            raise ValueError("chain_levels must be aligned to chain_index.")
        if not np.isfinite(levels).all() or (levels < 0).any():
            raise ValueError("chain_levels must contain finite non-negative values.")
        with np.errstate(over="ignore", invalid="ignore"):
            buildings = self.matrix @ levels
        if not np.isfinite(buildings).all():
            raise ValueError("Transformed building levels must be finite.")
        return buildings


@dataclass(frozen=True, kw_only=True)
class SupplyChainEquilibriumProblem(EquilibriumProblem):
    """Chain-coordinate constraints with building-coordinate economic accounting.

    ``bounds``, constraint columns, and ``warm_start`` decision coefficients
    follow ``basis.chain_index``. Production matrices and wealth retain the
    original economy indexes. Physical evaluation delegates to ``building_problem``.
    """

    basis: SupplyChainBasis = field(repr=False, compare=False)
    building_problem: EquilibriumProblem = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        """Validate the basis against the retained physical problem."""
        super().__post_init__()
        if self.basis.building_index != tuple(self.economy.building_index):
            raise ValueError("basis building_index must match the Economy exactly.")
        if self.building_problem.economy is not self.economy:
            raise ValueError("building_problem belongs to a different Economy.")
        if len(self.bounds) != len(self.basis.chain_index):
            raise ValueError("bounds must match the chain index.")

    def evaluate(self, levels: np.ndarray) -> EconomyState:
        """Solve equilibrium after transforming a nonnegative chain vector."""
        return self.building_problem.evaluate(self.basis.to_building_levels(levels))

    def _to_building_levels(self, levels: np.ndarray) -> np.ndarray:
        """Map chain coordinates for the shared final verification."""
        return self.basis.to_building_levels(levels)


class SupplyChainEquilibriumOptimizer(EquilibriumOptimizer):
    """Optimize nonnegative chain levels using the existing equilibrium search.

    ``x0`` and ``result.x`` contain chain levels. Returned states and
    ``result.building_levels`` contain ``basis.matrix @ result.x``. Fixed
    recipes restrict the search space; they do not guarantee financial viability.
    """

    def __init__(self, economy: Economy, basis: SupplyChainBasis) -> None:
        """Bind an economy and a compatible, immutable supply-chain basis."""
        super().__init__(economy)
        if basis.building_index != tuple(economy.building_index):
            raise ValueError("basis building_index must match the Economy exactly.")
        self.basis = basis

    def compile(
        self,
        scenario: Scenario,
        *,
        initial_wealth: np.ndarray | None = None,
        max_iterations: int = 1000,
        rtol: float = 1e-9,
        atol: float = 1e-8,
    ) -> SupplyChainEquilibriumProblem:
        """Compile building constraints and the nominal warm start into chains."""
        building = super().compile(
            scenario,
            initial_wealth=initial_wealth,
            max_iterations=max_iterations,
            rtol=rtol,
            atol=atol,
        )
        matrix = self.basis.matrix
        A_ub = None if building.A_ub is None else building.A_ub @ matrix
        A_eq = None if building.A_eq is None else building.A_eq @ matrix
        b_ub = building.b_ub
        slices = dict(building.inequality_slices)
        bounds: Bounds = tuple((0.0, None) for _ in self.basis.chain_index)
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
            max_iterations=building.max_iterations,
            rtol=building.rtol,
            atol=building.atol,
            basis=self.basis,
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
        if problem.basis is not self.basis:
            raise ValueError(
                "Compiled problem belongs to a different supply-chain basis."
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
                    else self.basis.to_building_levels(self.result.x)
                )
        if not _is_feasible(problem.building_problem, state.building_levels):
            if self.result is not None:
                self.result.success = False
                self.result.message = (
                    "Supply-chain final building feasibility check failed."
                )
            raise ValueError("Supply-chain final building feasibility check failed.")
        return state
