# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared compilation infrastructure for Victoria 3 optimizers."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field, replace
from types import MappingProxyType
from typing import TypedDict

import numpy as np
import pandas as pd
import scipy.optimize as opt
from scipy.optimize import OptimizeResult

from vic3_analysis.analysis.economy import Economy, EconomyState
from vic3_analysis.optimize._orders import goods_order_vector
from vic3_analysis.optimize.scenario import Scenario

Bounds = tuple[tuple[float, float | None], ...]
ConstraintSlices = Mapping[str, slice]

_FEASIBILITY_TOLERANCE = 1e-7


def _readonly_array(value: np.ndarray) -> np.ndarray:
    """Return an owned, read-only float array."""
    result = np.array(value, dtype=np.float64, copy=True)
    result.setflags(write=False)
    return result


class LinprogArgs(TypedDict):
    """Keyword arguments accepted by :func:`scipy.optimize.linprog`."""

    c: np.ndarray
    A_ub: np.ndarray | None
    b_ub: np.ndarray | None
    A_eq: np.ndarray | None
    b_eq: np.ndarray | None


@dataclass(frozen=True)
class _CompiledProblem:
    """Economy-bound data shared by concrete compiled problems."""

    economy: Economy = field(repr=False, compare=False)
    scenario: Scenario
    throughput_multipliers: np.ndarray = field(repr=False, compare=False)
    input_matrix: np.ndarray = field(repr=False, compare=False)
    output_matrix: np.ndarray = field(repr=False, compare=False)
    net_matrix: np.ndarray = field(repr=False, compare=False)
    gdp_vector: np.ndarray = field(repr=False, compare=False)
    goods_import: np.ndarray = field(repr=False, compare=False)
    goods_export: np.ndarray = field(repr=False, compare=False)
    A_ub: np.ndarray | None = field(repr=False, compare=False)
    b_ub: np.ndarray | None = field(repr=False, compare=False)
    A_eq: np.ndarray | None = field(repr=False, compare=False)
    b_eq: np.ndarray | None = field(repr=False, compare=False)
    bounds: Bounds
    inequality_slices: ConstraintSlices = field(compare=False)
    equality_slices: ConstraintSlices = field(compare=False)

    def __post_init__(self) -> None:
        """Defensively freeze arrays and named-slice mappings."""
        array_fields = (
            "throughput_multipliers",
            "input_matrix",
            "output_matrix",
            "net_matrix",
            "gdp_vector",
            "goods_import",
            "goods_export",
            "A_ub",
            "b_ub",
            "A_eq",
            "b_eq",
        )
        for name in array_fields:
            value = getattr(self, name)
            if value is not None:
                object.__setattr__(self, name, _readonly_array(value))
        object.__setattr__(
            self,
            "inequality_slices",
            MappingProxyType(dict(self.inequality_slices)),
        )
        object.__setattr__(
            self,
            "equality_slices",
            MappingProxyType(dict(self.equality_slices)),
        )


@dataclass(frozen=True)
class LinearProblem(_CompiledProblem):
    """A compiled nominal linear optimization problem."""

    objective_vector: np.ndarray = field(repr=False, compare=False)

    def __post_init__(self) -> None:
        """Freeze common data and the linear objective vector."""
        super().__post_init__()
        object.__setattr__(
            self, "objective_vector", _readonly_array(self.objective_vector)
        )

    def linprog_args(self) -> LinprogArgs:
        """Return coefficients as ``linprog`` keyword arguments."""
        return {
            "c": self.objective_vector,
            "A_ub": self.A_ub,
            "b_ub": self.b_ub,
            "A_eq": self.A_eq,
            "b_eq": self.b_eq,
        }


@dataclass(frozen=True)
class MarketProblem(_CompiledProblem):
    """A compiled nonlinear market-price optimization problem."""

    objective: Callable[[np.ndarray], float] = field(repr=False, compare=False)
    jacobian: Callable[[np.ndarray], np.ndarray] = field(repr=False, compare=False)
    warm_start: LinearProblem = field(repr=False, compare=False)


@dataclass(frozen=True)
class _CompilationData:
    """Common compilation result before an objective is attached."""

    economy: Economy
    scenario: Scenario
    throughput_multipliers: np.ndarray
    input_matrix: np.ndarray
    output_matrix: np.ndarray
    net_matrix: np.ndarray
    gdp_vector: np.ndarray
    goods_import: np.ndarray
    goods_export: np.ndarray
    A_ub: np.ndarray | None
    b_ub: np.ndarray | None
    A_eq: np.ndarray | None
    b_eq: np.ndarray | None
    bounds: Bounds
    inequality_slices: ConstraintSlices
    equality_slices: ConstraintSlices


class BaseOptimizer[ProblemT: _CompiledProblem](ABC):
    """Abstract base for economy-bound optimization formulations."""

    model: Economy
    result: OptimizeResult | None
    scenario: Scenario | None
    problem: ProblemT | None
    _state: EconomyState | None

    def __init__(self, model: Economy) -> None:
        """Bind the optimizer to *model*."""
        self.model = model
        self.result = None
        self.scenario = None
        self.problem = None
        self._state = None

    @abstractmethod
    def compile(self, scenario: Scenario) -> ProblemT:
        """Compile *scenario* into the concrete optimizer's problem type."""

    def summary(self) -> pd.DataFrame:
        """Return a fresh one-row report of the latest returned solution.

        GDP is reported weekly and annually; ``gdp_per_capita`` is annual.
        Employment counts workers, population includes dependents, and wealth
        is a population-weighted tier. Infrastructure usage is consumption
        minus generation. Construction cost and arable-land consumption use
        the model's existing accounting. ``throughput_multiplier`` is NaN
        unless all compiled configuration multipliers are equal.

        Reporting never solves or evaluates the problem again. Binding a new
        problem clears the retained solution. Equilibrium searches that return
        a verified state on budget exhaustion remain reportable even when
        ``search_success`` is false.

        Raises:
            ValueError: If the current problem has no returned solution.
        """
        state = self._require_state()
        problem = self._require_problem()
        result = self.result
        if result is None:
            raise ValueError("Optimizer has no returned solution to summarize.")
        scenario = problem.scenario
        multipliers = problem.throughput_multipliers
        values: dict[str, object] = {
            "objective": scenario.objective,
            "employment_cap": scenario.employment_cap,
            "workforce_ratio": scenario.workforce_ratio,
            "banned_building_groups": ";".join(scenario.banned_building_groups),
            "min_net_infrastructure": scenario.min_net_infrastructure,
            "min_goods_balance": scenario.min_goods_balance,
            "configuration_count": len(self.model.building_index),
            "throughput_multiplier": (
                float(multipliers[0])
                if multipliers.size and np.all(multipliers == multipliers[0])
                else float("nan")
            ),
            "economy_of_scale_level_cap": 0.0,
            "gdp_weekly": state.gdp_weekly,
            "annual_gdp": state.gdp(annual=True),
            "employment": state.total_employment,
            "population": state.total_population,
            "gdp_per_capita": state.gdp_per_capita(annual=True),
            "average_wealth": state.average_wealth,
            "construction_cost": self.model.construction_cost(state),
            "arable_land_consumption": self.model.arable_land_consumption(state),
            "net_infrastructure_usage": float(
                state.building_levels @ self.model.infrastructure_vector
            ),
            "search_success": bool(result.success),
            "search_status": int(result.status),
            "search_message": str(result.message),
        }
        if "nfev" in result:
            values["trial_evaluations"] = int(result.nfev)
        return pd.DataFrame([values])

    def _require_state(self) -> EconomyState:
        if self._state is None:
            raise ValueError("Optimizer has no returned solution to summarize.")
        return self._state

    @property
    def goods_input_matrix(self) -> np.ndarray:
        """Return the current problem's adjusted input matrix."""
        return self._require_problem().input_matrix

    @property
    def goods_output_matrix(self) -> np.ndarray:
        """Return the current problem's adjusted output matrix."""
        return self._require_problem().output_matrix

    @property
    def goods_matrix(self) -> np.ndarray:
        """Return the current problem's adjusted net-goods matrix."""
        return self._require_problem().net_matrix

    @property
    def gdp_vector(self) -> np.ndarray:
        """Return the current problem's nominal GDP vector."""
        return self._require_problem().gdp_vector

    @property
    def throughput_multipliers(self) -> np.ndarray:
        """Return the current problem's per-configuration multipliers."""
        return self._require_problem().throughput_multipliers

    def _require_problem(self) -> ProblemT:
        if self.problem is None:
            raise ValueError("Optimizer has not compiled or solved a scenario.")
        return self.problem

    def _bind_problem(self, problem: ProblemT) -> None:
        """Retain *problem* and invalidate any previous result and solution."""
        self._validate_problem_economy(problem)
        self.problem = problem
        self.scenario = problem.scenario
        self.result = None
        self._state = None

    def _validate_problem_economy(self, problem: _CompiledProblem) -> None:
        if problem.economy is not self.model:
            raise ValueError("Compiled problem belongs to a different Economy.")

    def _compile_common(self, scenario: Scenario) -> _CompilationData:
        """Compile shared market context and linear constraints."""
        multipliers = self._throughput_multipliers(scenario)
        input_matrix = self.model.goods_input_matrix(throughput_multipliers=multipliers)
        output_matrix = self.model.goods_output_matrix(
            throughput_multipliers=multipliers
        )
        net_matrix = output_matrix - input_matrix
        goods_import = goods_order_vector(
            self.model.goods_index, scenario.goods_import, "goods_import"
        )
        goods_export = goods_order_vector(
            self.model.goods_index, scenario.goods_export, "goods_export"
        )
        A_ub, b_ub, inequality_slices = self._compile_inequalities(
            scenario, net_matrix, goods_import, goods_export
        )
        A_eq, b_eq, equality_slices = self._compile_equalities(scenario)
        n_buildings = len(self.model.building_index)
        return _CompilationData(
            economy=self.model,
            scenario=scenario,
            throughput_multipliers=multipliers,
            input_matrix=input_matrix,
            output_matrix=output_matrix,
            net_matrix=net_matrix,
            gdp_vector=net_matrix @ self.model.base_prices,
            goods_import=goods_import,
            goods_export=goods_export,
            A_ub=A_ub,
            b_ub=b_ub,
            A_eq=A_eq,
            b_eq=b_eq,
            bounds=tuple((0.0, None) for _ in range(n_buildings)),
            inequality_slices=inequality_slices,
            equality_slices=equality_slices,
        )

    def _linear_problem(
        self,
        data: _CompilationData,
        objective_vector: np.ndarray,
    ) -> LinearProblem:
        """Attach a linear objective to common compiled data."""
        return LinearProblem(
            economy=data.economy,
            scenario=data.scenario,
            throughput_multipliers=data.throughput_multipliers,
            input_matrix=data.input_matrix,
            output_matrix=data.output_matrix,
            net_matrix=data.net_matrix,
            gdp_vector=data.gdp_vector,
            goods_import=data.goods_import,
            goods_export=data.goods_export,
            A_ub=data.A_ub,
            b_ub=data.b_ub,
            A_eq=data.A_eq,
            b_eq=data.b_eq,
            bounds=data.bounds,
            inequality_slices=data.inequality_slices,
            equality_slices=data.equality_slices,
            objective_vector=objective_vector,
        )

    def _state_from_levels(
        self,
        problem: _CompiledProblem,
        levels: np.ndarray,
        *,
        method: str = "nominal",
    ) -> EconomyState:
        """Convert solved decision levels to a consistent economy state."""
        return self.model.solve(
            levels,
            method=method,
            goods_import=problem.goods_import,
            throughput_multipliers=problem.throughput_multipliers,
            goods_export=problem.goods_export,
            economy_of_scale_level_cap=0.0,
            workforce_ratio=problem.scenario.workforce_ratio,
        )

    def _throughput_multipliers(self, scenario: Scenario) -> np.ndarray:
        multipliers = np.ones(len(self.model.df_production), dtype=np.float64)
        buildings = self.model.df_production["building"].to_numpy()
        for building_key, multiplier in scenario.throughput_multipliers:
            multipliers[buildings == building_key] *= multiplier
        return multipliers

    def _compile_inequalities(
        self,
        scenario: Scenario,
        net_matrix: np.ndarray,
        goods_import: np.ndarray,
        goods_export: np.ndarray,
    ) -> tuple[np.ndarray | None, np.ndarray | None, ConstraintSlices]:
        blocks: list[tuple[str, np.ndarray, np.ndarray]] = []
        if scenario.min_goods_balance is not None:
            blocks.append(
                (
                    "min_goods_balance",
                    -net_matrix.T,
                    goods_import - goods_export - scenario.min_goods_balance,
                )
            )
        if scenario.construction_cost_cap is not None:
            blocks.append(
                (
                    "construction_cost_cap",
                    self.model.construction_cost_vector,
                    np.array([scenario.construction_cost_cap], dtype=np.float64),
                )
            )
        if scenario.employment_cap is not None:
            blocks.append(
                (
                    "employment_cap",
                    self.model.employment_vector,
                    np.array([scenario.employment_cap], dtype=np.float64),
                )
            )
        if scenario.building_level_caps:
            buildings = self.model.df_production["building"].to_numpy()
            rows = [
                (buildings == building_key).astype(np.float64)
                for building_key, _limit in scenario.building_level_caps
            ]
            blocks.append(
                (
                    "building_level_caps",
                    np.vstack(rows),
                    np.asarray(
                        [limit for _building, limit in scenario.building_level_caps],
                        dtype=np.float64,
                    ),
                )
            )
        if scenario.arable_land_cap is not None:
            blocks.append(
                (
                    "arable_land_cap",
                    self.model.arable_land_vector,
                    np.array([scenario.arable_land_cap], dtype=np.float64),
                )
            )
        if scenario.min_net_infrastructure is not None:
            infrastructure = (
                self.model.df_production["infrastructure_usage_per_level"]
                .fillna(0)
                .to_numpy(dtype=np.float64)
            )
            blocks.append(
                (
                    "min_net_infrastructure",
                    infrastructure,
                    np.array([-scenario.min_net_infrastructure], dtype=np.float64),
                )
            )
        return self._stack_named(blocks)

    def _compile_equalities(
        self, scenario: Scenario
    ) -> tuple[np.ndarray | None, np.ndarray | None, ConstraintSlices]:
        blocks: list[tuple[str, np.ndarray, np.ndarray]] = []
        if scenario.era_cap is not None:
            mask = (self.model.df_production["era"] > scenario.era_cap).to_numpy()
            blocks.append(("era_cap", mask.astype(np.float64), np.array([0.0])))
        if scenario.banned_pms:
            pattern = re.compile(
                r"\b(?:"
                + "|".join(re.escape(key) for key in scenario.banned_pms)
                + r")\b"
            )
            mask = (
                self.model.df_production["production_method"]
                .str.contains(pattern, na=False)
                .to_numpy()
            )
            blocks.append(("banned_pms", mask.astype(np.float64), np.array([0.0])))
        if scenario.banned_building_groups:
            rows = [
                (self.model.df_production["building_group"] == building_group)
                .to_numpy()
                .astype(np.float64)
                for building_group in scenario.banned_building_groups
            ]
            blocks.append(
                (
                    "banned_building_groups",
                    np.vstack(rows),
                    np.zeros(len(rows), dtype=np.float64),
                )
            )
        if scenario.urbanization_per_center is not None:
            urbanization = (
                self.model.df_production["urbanization"]
                .fillna(0)
                .to_numpy(dtype=np.float64)
            )
            urban_center = (
                self.model.df_production["building"] == "building_urban_center"
            ).to_numpy()
            blocks.append(
                (
                    "urbanization_per_center",
                    urbanization - scenario.urbanization_per_center * urban_center,
                    np.array([0.0]),
                )
            )
        return self._stack_named(blocks)

    @staticmethod
    def _stack_named(
        blocks: list[tuple[str, np.ndarray, np.ndarray]],
    ) -> tuple[np.ndarray | None, np.ndarray | None, ConstraintSlices]:
        if not blocks:
            return None, None, MappingProxyType({})
        matrices: list[np.ndarray] = []
        bounds: list[np.ndarray] = []
        slices: dict[str, slice] = {}
        offset = 0
        for name, matrix, bound in blocks:
            rows = np.atleast_2d(np.asarray(matrix, dtype=np.float64))
            rhs = np.atleast_1d(np.asarray(bound, dtype=np.float64))
            if rows.shape[0] != rhs.shape[0]:
                raise ValueError(f"Constraint block {name!r} has mismatched rows.")
            matrices.append(rows)
            bounds.append(rhs)
            slices[name] = slice(offset, offset + rows.shape[0])
            offset += rows.shape[0]
        return (
            np.vstack(matrices),
            np.hstack(bounds),
            MappingProxyType(slices),
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
        slices = BaseOptimizer._retained_slices(problem.equality_slices, keep)
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
    def _check_feasibility_and_boundedness(
        problem: LinearProblem, *, label: str = "Market"
    ) -> None:
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
                f"{label} optimization is infeasible: {boundedness.message}"
            )
        if boundedness.status == 3:
            raise ValueError(
                f"{label} optimization requires a bounded feasible region: "
                f"{boundedness.message}"
            )
        raise ValueError(f"{label} preflight failed: {boundedness.message}")

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
