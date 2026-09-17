"""Shared compilation infrastructure for Victoria 3 optimizers."""

from __future__ import annotations

import re
from abc import ABC, abstractmethod
from collections.abc import Callable, Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Generic, TypeVar, TypedDict

import numpy as np
from scipy.optimize import OptimizeResult

from vic3_analysis.analysis.economy import Economy, EconomyState
from vic3_analysis.optimize.scenario import Scenario


Bounds = tuple[tuple[float, float | None], ...]
ConstraintSlices = Mapping[str, slice]


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
    imports: np.ndarray = field(repr=False, compare=False)
    exports: np.ndarray = field(repr=False, compare=False)
    pop_needs: np.ndarray = field(repr=False, compare=False)
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
            "imports",
            "exports",
            "pop_needs",
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
    imports: np.ndarray
    exports: np.ndarray
    pop_needs: np.ndarray
    A_ub: np.ndarray | None
    b_ub: np.ndarray | None
    A_eq: np.ndarray | None
    b_eq: np.ndarray | None
    bounds: Bounds
    inequality_slices: ConstraintSlices
    equality_slices: ConstraintSlices


ProblemT = TypeVar("ProblemT", bound=_CompiledProblem)


class BaseOptimizer(ABC, Generic[ProblemT]):
    """Abstract base for economy-bound optimization formulations."""

    model: Economy
    result: OptimizeResult | None
    scenario: Scenario | None
    problem: ProblemT | None

    def __init__(self, model: Economy) -> None:
        """Bind the optimizer to *model*."""
        self.model = model
        self.result = None
        self.scenario = None
        self.problem = None

    @abstractmethod
    def compile(self, scenario: Scenario) -> ProblemT:
        """Compile *scenario* into the concrete optimizer's problem type."""

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
        """Retain *problem* and invalidate any previous solver result."""
        self._validate_problem_economy(problem)
        self.problem = problem
        self.scenario = problem.scenario
        self.result = None

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
        imports = self._goods_context_vector(scenario.imports, "imports")
        exports = self._goods_context_vector(scenario.exports, "exports")
        pop_needs = self._goods_context_vector(scenario.pop_needs, "pop_needs")
        A_ub, b_ub, inequality_slices = self._compile_inequalities(scenario, net_matrix)
        A_eq, b_eq, equality_slices = self._compile_equalities(scenario)
        n_buildings = len(self.model.building_index())
        return _CompilationData(
            economy=self.model,
            scenario=scenario,
            throughput_multipliers=multipliers,
            input_matrix=input_matrix,
            output_matrix=output_matrix,
            net_matrix=net_matrix,
            gdp_vector=net_matrix @ self.model.base_prices(),
            imports=imports,
            exports=exports,
            pop_needs=pop_needs,
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
            imports=data.imports,
            exports=data.exports,
            pop_needs=data.pop_needs,
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
            imports=problem.imports,
            exports=problem.exports,
            throughput_multipliers=problem.throughput_multipliers,
            pop_needs=problem.pop_needs,
            economy_of_scale_level_cap=0.0,
        )

    def _goods_context_vector(
        self, entries: tuple[tuple[str, float], ...], name: str
    ) -> np.ndarray:
        """Translate named fixed market context into a goods-aligned vector."""
        positions = {good: i for i, good in enumerate(self.model.goods_index())}
        vector = np.zeros(len(positions), dtype=np.float64)
        for entry in entries:
            if not isinstance(entry, tuple) or len(entry) != 2:
                raise ValueError(f"{name} entries must be (good, amount) pairs.")
            good, amount = entry
            if not isinstance(good, str):
                raise ValueError(f"{name} good keys must be strings.")
            if good not in positions:
                raise ValueError(
                    f"Good '{good}' in {name} was not found in goods index."
                )
            try:
                value = float(amount)
            except (TypeError, ValueError) as exc:
                raise ValueError(
                    f"{name} amounts must be finite non-negative numbers."
                ) from exc
            if not np.isfinite(value) or value < 0:
                raise ValueError(f"{name} amounts must be finite non-negative numbers.")
            position = positions[good]
            if value > np.finfo(np.float64).max - vector[position]:
                raise ValueError(f"{name} totals must remain finite.")
            vector[position] += value
        return vector

    def _throughput_multipliers(self, scenario: Scenario) -> np.ndarray:
        multipliers = np.ones(len(self.model.df_production), dtype=np.float64)
        buildings = self.model.df_production["building"].to_numpy()
        for building_key, multiplier in scenario.throughput_bonuses:
            multipliers[buildings == building_key] *= multiplier
        return multipliers

    def _compile_inequalities(
        self, scenario: Scenario, net_matrix: np.ndarray
    ) -> tuple[np.ndarray | None, np.ndarray | None, ConstraintSlices]:
        blocks: list[tuple[str, np.ndarray, np.ndarray]] = []
        if scenario.import_limit is not None:
            blocks.append(
                (
                    "import_limit",
                    -net_matrix.T,
                    np.full(
                        net_matrix.shape[1],
                        scenario.import_limit,
                        dtype=np.float64,
                    ),
                )
            )
        if scenario.construction_cost_cap is not None:
            blocks.append(
                (
                    "construction_cost_cap",
                    self.model.construction_cost_vector(),
                    np.array([scenario.construction_cost_cap], dtype=np.float64),
                )
            )
        if scenario.employment_cap is not None:
            blocks.append(
                (
                    "employment_cap",
                    self.model.employment_vector(),
                    np.array([scenario.employment_cap], dtype=np.float64),
                )
            )
        if scenario.produce:
            positions = {good: i for i, good in enumerate(self.model.goods_index())}
            rows: list[np.ndarray] = []
            amounts: list[float] = []
            for good, amount in scenario.produce:
                if good not in positions:
                    raise ValueError(f"Good '{good}' not found in goods index.")
                rows.append(-net_matrix[:, positions[good]])
                amounts.append(-amount)
            blocks.append(
                (
                    "produce",
                    np.vstack(rows),
                    np.asarray(amounts, dtype=np.float64),
                )
            )
        if scenario.building_limits:
            buildings = self.model.df_production["building"].to_numpy()
            rows = [
                (buildings == building_key).astype(np.float64)
                for building_key, _limit in scenario.building_limits
            ]
            blocks.append(
                (
                    "building_limits",
                    np.vstack(rows),
                    np.asarray(
                        [limit for _building, limit in scenario.building_limits],
                        dtype=np.float64,
                    ),
                )
            )
        if scenario.arable_land_cap is not None:
            blocks.append(
                (
                    "arable_land_cap",
                    self.model.arable_land_vector(),
                    np.array([scenario.arable_land_cap], dtype=np.float64),
                )
            )
        if scenario.min_infrastructure is not None:
            infrastructure = (
                self.model.df_production["infrastructure_usage_per_level"]
                .fillna(0)
                .to_numpy(dtype=np.float64)
            )
            blocks.append(
                (
                    "min_infrastructure",
                    -infrastructure,
                    np.array([-scenario.min_infrastructure], dtype=np.float64),
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
