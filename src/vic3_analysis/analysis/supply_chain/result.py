"""Immutable result objects for supply-chain analysis."""

from __future__ import annotations

from collections.abc import Mapping
from dataclasses import dataclass, field
from types import MappingProxyType
from typing import Literal

import networkx as nx
import numpy as np
import pandas as pd
from matplotlib.figure import Figure

from vic3_analysis.analysis.economy import EconomyState
from vic3_analysis.analysis.supply_chain.graph import (
    SupplyChainView,
    condensation_depth,
    cyclic_component_count,
    cyclic_nodes,
    good_keys,
    good_node_id,
    process_node_id,
    process_rows,
    validate_view,
)
from vic3_analysis.optimize.base import ConstraintSlices, LinearProblem
from vic3_analysis.optimize.scenario import Scenario

PROCESS_COLUMNS = [
    "config",
    "building",
    "production_method",
    "building_group",
    "parent_group",
    "land_usage",
    "era",
    "allowed",
    "active",
    "in_terminal_chain",
    "level",
    "throughput_multiplier",
    "unit_input_cost",
    "unit_output_value",
    "unit_value_added",
    "input_cost",
    "output_value",
    "value_added",
    "employment",
    "construction_cost",
    "arable_land",
    "net_infrastructure_usage",
    "is_extractive",
    "is_subsistence",
    "discoverable_resource",
    "depletable_resource",
]
GOOD_COLUMNS = [
    "good",
    "terminal",
    "price",
    "production",
    "consumption",
    "imports",
    "exports",
    "pop_needs",
    "sell_orders",
    "buy_orders",
    "net_balance",
    "output_value",
    "input_value",
    "input_cost_share",
    "allowed_producers",
    "active_producers",
]
FLOW_COLUMNS = [
    "source",
    "target",
    "role",
    "good",
    "process",
    "unit_rate",
    "realized_amount",
    "price",
    "realized_value",
    "active",
    "in_cycle",
]
WORKFORCE_COLUMNS = ["config", "building", "profession", "employment"]
CONSTRAINT_COLUMNS = [
    "kind",
    "family",
    "label",
    "realized_value",
    "bound",
    "slack",
    "residual",
    "binding",
    "solver_marginal",
    "improvement_per_unit",
]
ALTERNATIVE_COLUMNS = [
    "good",
    "config",
    "building",
    "production_method",
    "era",
    "unit_output",
    "unit_input_cost",
    "unit_output_value",
    "unit_value_added",
    "selected",
    "level",
    "parent_group",
    "land_usage",
    "is_extractive",
    "is_subsistence",
    "discoverable_resource",
    "depletable_resource",
]
SUMMARY_FIELDS = [
    "scenario",
    "terminal_good",
    "objective",
    "solver_status",
    "solver_message",
    "objective_value",
    "target_quantity",
    "target_base_value",
    "terminal_base_price",
    "terminal_gross_output",
    "terminal_net_output",
    "terminal_surplus",
    "system_gdp_weekly",
    "system_gdp_annual",
    "chain_gdp_weekly",
    "chain_gdp_annual",
    "system_employment",
    "chain_employment",
    "system_construction_cost",
    "chain_construction_cost",
    "system_arable_land",
    "chain_arable_land",
    "system_net_infrastructure_usage",
    "chain_net_infrastructure_usage",
    "employment_per_terminal_unit",
    "construction_per_terminal_unit",
    "gdp_per_terminal_unit",
    "output_per_10k_workers",
    "realized_process_count",
    "realized_good_count",
    "realized_edge_count",
    "allowed_process_count",
    "allowed_good_count",
    "allowed_edge_count",
    "cyclic_component_count",
    "cyclic_node_count",
    "condensation_depth",
    "extractive_process_count",
    "resource_process_count",
    "chain_gdp_share",
    "chain_employment_share",
    "chain_construction_share",
    "chain_arable_land_share",
    "chain_infrastructure_share",
]


def _readonly(value: np.ndarray) -> np.ndarray:
    result = np.array(value, dtype=np.float64, copy=True)
    result.setflags(write=False)
    return result


def _safe_divide(numerator: float, denominator: float) -> float:
    return numerator / denominator if denominator != 0.0 else 0.0


@dataclass(frozen=True)
class SolverDiagnostics:
    """Snapshot of solver metadata needed for reporting."""

    status: int
    message: str
    objective_value: float
    inequality_marginals: np.ndarray | None = field(default=None, repr=False)
    equality_marginals: np.ndarray | None = field(default=None, repr=False)

    def __post_init__(self) -> None:
        if self.inequality_marginals is not None:
            object.__setattr__(
                self, "inequality_marginals", _readonly(self.inequality_marginals)
            )
        if self.equality_marginals is not None:
            object.__setattr__(
                self, "equality_marginals", _readonly(self.equality_marginals)
            )


@dataclass(frozen=True)
class SupplyChainResult:
    """Immutable, reproducible result of one terminal-good analysis."""

    scenario: Scenario
    terminal_good: str
    target_quantity: float
    problem: LinearProblem = field(repr=False, compare=False)
    state: EconomyState = field(repr=False, compare=False)
    diagnostics: SolverDiagnostics
    production: pd.DataFrame = field(repr=False, compare=False)
    goods_index: tuple[str, ...]
    config_index: tuple[str, ...]
    profession_index: tuple[str, ...]
    employment_matrix: np.ndarray = field(repr=False, compare=False)
    employment_vector: np.ndarray = field(repr=False, compare=False)
    construction_cost_vector: np.ndarray = field(repr=False, compare=False)
    arable_land_vector: np.ndarray = field(repr=False, compare=False)
    infrastructure_vector: np.ndarray = field(repr=False, compare=False)
    realized_graph: nx.DiGraph = field(repr=False, compare=False)
    allowed_graph: nx.DiGraph = field(repr=False, compare=False)
    tolerance: float = 1e-9

    def __post_init__(self) -> None:
        for name in (
            "employment_matrix",
            "employment_vector",
            "construction_cost_vector",
            "arable_land_vector",
            "infrastructure_vector",
        ):
            object.__setattr__(self, name, _readonly(getattr(self, name)))
        object.__setattr__(self, "production", self.production.copy(deep=True))
        object.__setattr__(
            self, "realized_graph", nx.freeze(self.realized_graph.copy())
        )
        object.__setattr__(self, "allowed_graph", nx.freeze(self.allowed_graph.copy()))

    def _source_graph(self, view: SupplyChainView) -> nx.DiGraph:
        return self.realized_graph if view == "realized" else self.allowed_graph

    def graph(self, view: str = "realized") -> nx.DiGraph:
        """Return a defensive copy of the requested bipartite graph."""
        narrowed = validate_view(view)
        return self._source_graph(narrowed).copy()

    def _rows_for_view(self, view: SupplyChainView) -> tuple[int, ...]:
        return process_rows(self._source_graph(view))

    def _process_table(self, rows: tuple[int, ...]) -> pd.DataFrame:
        realized_rows = set(process_rows(self.realized_graph))
        prices = self.state.market_prices
        result: list[dict[str, object]] = []
        for i in rows:
            source = self.production.iloc[i]
            level = float(self.state.building_levels[i])
            unit_input = float(self.problem.input_matrix[i] @ prices)
            unit_output = float(self.problem.output_matrix[i] @ prices)
            result.append(
                {
                    "config": self.config_index[i],
                    "building": str(source["building"]),
                    "production_method": str(source["production_method"]),
                    "building_group": str(source.get("building_group", "")),
                    "parent_group": str(source.get("parent_group", "")),
                    "land_usage": str(source.get("land_usage", "")),
                    "era": int(source["era"]),
                    "allowed": process_node_id(self.config_index[i])
                    in self.allowed_graph,
                    "active": level > self.tolerance,
                    "in_terminal_chain": i in realized_rows,
                    "level": level,
                    "throughput_multiplier": float(
                        self.problem.throughput_multipliers[i]
                    ),
                    "unit_input_cost": unit_input,
                    "unit_output_value": unit_output,
                    "unit_value_added": unit_output - unit_input,
                    "input_cost": unit_input * level,
                    "output_value": unit_output * level,
                    "value_added": (unit_output - unit_input) * level,
                    "employment": float(self.employment_vector[i]) * level,
                    "construction_cost": float(self.construction_cost_vector[i])
                    * level,
                    "arable_land": float(self.arable_land_vector[i]) * level,
                    "net_infrastructure_usage": float(self.infrastructure_vector[i])
                    * level,
                    "is_extractive": bool(
                        self.allowed_graph.nodes.get(
                            process_node_id(self.config_index[i]), {}
                        ).get("is_extractive", False)
                    ),
                    "is_subsistence": bool(source.get("is_subsistence", False)),
                    "discoverable_resource": bool(
                        source.get("discoverable_resource", False)
                    ),
                    "depletable_resource": bool(
                        source.get("depletable_resource", False)
                    ),
                }
            )
        return pd.DataFrame(result, columns=PROCESS_COLUMNS)

    def processes(self, view: str = "realized") -> pd.DataFrame:
        """Return process economics and resource attributes for one view."""
        narrowed = validate_view(view)
        return self._process_table(self._rows_for_view(narrowed))

    def goods(self, view: str = "realized") -> pd.DataFrame:
        """Return good balances for processes present in one graph view."""
        narrowed = validate_view(view)
        graph = self._source_graph(narrowed)
        rows = self._rows_for_view(narrowed)
        levels = self.state.building_levels
        if rows:
            idx = np.asarray(rows, dtype=np.int64)
            output = levels[idx] @ self.problem.output_matrix[idx]
            inputs = levels[idx] @ self.problem.input_matrix[idx]
        else:
            output = np.zeros(len(self.goods_index), dtype=np.float64)
            inputs = np.zeros(len(self.goods_index), dtype=np.float64)
        present = set(good_keys(graph, self.goods_index))
        total_input_value = float(inputs @ self.state.market_prices)
        rows_out: list[dict[str, object]] = []
        for j, good in enumerate(self.goods_index):
            if good not in present:
                continue
            input_value = float(inputs[j] * self.state.market_prices[j])
            allowed_producers = sum(
                1
                for predecessor in self.allowed_graph.predecessors(good_node_id(good))
                if self.allowed_graph.nodes[predecessor].get("kind") == "process"
            )
            active_producers = sum(
                1
                for predecessor in self.realized_graph.predecessors(good_node_id(good))
                if self.realized_graph.nodes[predecessor].get("kind") == "process"
            )
            sell = float(output[j] + self.state.imports[j])
            buy = float(inputs[j] + self.state.exports[j] + self.state.pop_needs[j])
            rows_out.append(
                {
                    "good": good,
                    "terminal": good == self.terminal_good,
                    "price": float(self.state.market_prices[j]),
                    "production": float(output[j]),
                    "consumption": float(inputs[j]),
                    "imports": float(self.state.imports[j]),
                    "exports": float(self.state.exports[j]),
                    "pop_needs": float(self.state.pop_needs[j]),
                    "sell_orders": sell,
                    "buy_orders": buy,
                    "net_balance": sell - buy,
                    "output_value": float(output[j] * self.state.market_prices[j]),
                    "input_value": input_value,
                    "input_cost_share": _safe_divide(input_value, total_input_value),
                    "allowed_producers": allowed_producers,
                    "active_producers": active_producers,
                }
            )
        return pd.DataFrame(rows_out, columns=GOOD_COLUMNS)

    def flows(self, view: str = "realized") -> pd.DataFrame:
        """Return one row per goods/process edge in one graph view."""
        narrowed = validate_view(view)
        graph = self._source_graph(narrowed)
        in_cycle = cyclic_nodes(graph)
        rows: list[dict[str, object]] = []
        for source, target, data in sorted(graph.edges(data=True)):
            rows.append(
                {
                    "source": source,
                    "target": target,
                    "role": str(data["role"]),
                    "good": str(data["good"]),
                    "process": str(data["process"]),
                    "unit_rate": float(data["unit_rate"]),
                    "realized_amount": float(data["realized_amount"]),
                    "price": float(data["price"]),
                    "realized_value": float(data["realized_value"]),
                    "active": bool(data["active"]),
                    "in_cycle": source in in_cycle and target in in_cycle,
                }
            )
        return pd.DataFrame(rows, columns=FLOW_COLUMNS)

    def workforce(self) -> pd.DataFrame:
        """Return realized terminal-chain employment by process and profession."""
        rows: list[dict[str, object]] = []
        for i in self._rows_for_view("realized"):
            for j, profession in enumerate(self.profession_index):
                employment = float(self.state.pops[i, j])
                if employment <= self.tolerance:
                    continue
                rows.append(
                    {
                        "config": self.config_index[i],
                        "building": str(self.production.iloc[i]["building"]),
                        "profession": profession,
                        "employment": employment,
                    }
                )
        return pd.DataFrame(rows, columns=WORKFORCE_COLUMNS)

    def _constraint_labels(self, family: str, count: int) -> tuple[str, ...]:
        if family == "import_limit":
            labels = self.goods_index
        elif family == "produce":
            labels = tuple(good for good, _amount in self.scenario.produce)
        elif family == "building_limits":
            labels = tuple(
                building for building, _limit in self.scenario.building_limits
            )
        elif family == "banned_building_groups":
            labels = self.scenario.banned_building_groups
        elif family == "banned_pms":
            labels = ("+".join(self.scenario.banned_pms),)
        else:
            labels = (family,)
        if len(labels) != count:
            return tuple(f"{family}[{i}]" for i in range(count))
        return tuple(str(label) for label in labels)

    def constraints(self) -> pd.DataFrame:
        """Return named LP constraint values, slacks, and solver marginals."""
        levels = self.state.building_levels
        rows: list[dict[str, object]] = []

        def append_blocks(
            kind: Literal["inequality", "equality"],
            matrix: np.ndarray | None,
            bounds: np.ndarray | None,
            slices: ConstraintSlices,
            marginals: np.ndarray | None,
        ) -> None:
            if matrix is None or bounds is None:
                return
            values = matrix @ levels
            for family, row_slice in slices.items():
                start = 0 if row_slice.start is None else row_slice.start
                stop = start if row_slice.stop is None else row_slice.stop
                labels = self._constraint_labels(str(family), stop - start)
                for offset, position in enumerate(range(start, stop)):
                    lhs = float(values[position])
                    bound = float(bounds[position])
                    slack = bound - lhs if kind == "inequality" else float("nan")
                    residual = lhs - bound if kind == "equality" else 0.0
                    binding = (
                        slack <= self.tolerance
                        if kind == "inequality"
                        else abs(residual) <= self.tolerance
                    )
                    marginal = (
                        float(marginals[position])
                        if marginals is not None and position < len(marginals)
                        else float("nan")
                    )
                    rows.append(
                        {
                            "kind": kind,
                            "family": str(family),
                            "label": labels[offset],
                            "realized_value": lhs,
                            "bound": bound,
                            "slack": slack,
                            "residual": residual,
                            "binding": binding,
                            "solver_marginal": marginal,
                            "improvement_per_unit": (
                                max(0.0, -marginal)
                                if kind == "inequality" and np.isfinite(marginal)
                                else float("nan")
                            ),
                        }
                    )

        append_blocks(
            "inequality",
            self.problem.A_ub,
            self.problem.b_ub,
            self.problem.inequality_slices,
            self.diagnostics.inequality_marginals,
        )
        append_blocks(
            "equality",
            self.problem.A_eq,
            self.problem.b_eq,
            self.problem.equality_slices,
            self.diagnostics.equality_marginals,
        )
        return pd.DataFrame(rows, columns=CONSTRAINT_COLUMNS)

    def bottlenecks(self) -> pd.DataFrame:
        """Return binding inequalities with a useful relaxation marginal."""
        constraints = self.constraints()
        selected = constraints[
            constraints["kind"].eq("inequality")
            & constraints["binding"].eq(True)
            & constraints["improvement_per_unit"].gt(self.tolerance)
        ].copy()
        order = np.lexsort(
            (
                np.asarray(selected["label"], dtype=str),
                np.asarray(selected["family"], dtype=str),
                -np.asarray(selected["improvement_per_unit"], dtype=np.float64),
            )
        )
        return selected.iloc[order].reset_index(drop=True)

    def alternatives(self, good: str | None = None) -> pd.DataFrame:
        """Return scenario-allowed producer alternatives for one or all goods."""
        if good is not None and good not in self.goods_index:
            raise ValueError(f"Good '{good}' not found in goods index.")
        prices = self.state.market_prices
        rows: list[dict[str, object]] = []
        selected_rows = set(process_rows(self.realized_graph))
        goods = (
            (good,)
            if good is not None
            else good_keys(self.allowed_graph, self.goods_index)
        )
        for output_good in goods:
            good_id = good_node_id(output_good)
            if good_id not in self.allowed_graph:
                continue
            good_position = self.goods_index.index(output_good)
            for process_id in self.allowed_graph.predecessors(good_id):
                data = self.allowed_graph.nodes[process_id]
                if data.get("kind") != "process":
                    continue
                i = int(data["row"])
                unit_input = float(self.problem.input_matrix[i] @ prices)
                unit_output = float(self.problem.output_matrix[i] @ prices)
                rows.append(
                    {
                        "good": output_good,
                        "config": self.config_index[i],
                        "building": str(self.production.iloc[i]["building"]),
                        "production_method": str(
                            self.production.iloc[i]["production_method"]
                        ),
                        "era": int(self.production.iloc[i]["era"]),
                        "unit_output": float(
                            self.problem.output_matrix[i, good_position]
                        ),
                        "unit_input_cost": unit_input,
                        "unit_output_value": unit_output,
                        "unit_value_added": unit_output - unit_input,
                        "selected": i in selected_rows,
                        "level": float(self.state.building_levels[i]),
                        "parent_group": str(data.get("parent_group", "")),
                        "land_usage": str(data.get("land_usage", "")),
                        "is_extractive": bool(data.get("is_extractive", False)),
                        "is_subsistence": bool(data.get("is_subsistence", False)),
                        "discoverable_resource": bool(
                            data.get("discoverable_resource", False)
                        ),
                        "depletable_resource": bool(
                            data.get("depletable_resource", False)
                        ),
                    }
                )
        frame = pd.DataFrame(rows, columns=ALTERNATIVE_COLUMNS)
        if frame.empty:
            return frame
        frame = frame.sort_values("config", kind="mergesort")
        frame = frame.sort_values("unit_output", ascending=False, kind="mergesort")
        frame = frame.sort_values("selected", ascending=False, kind="mergesort")
        return frame.sort_values("good", kind="mergesort").reset_index(drop=True)

    def summary(self) -> pd.Series:
        """Return stable headline, structural, and efficiency metrics."""
        terminal_position = self.goods_index.index(self.terminal_good)
        terminal_output = float(self.state.building_goods_output[terminal_position])
        terminal_net = float(
            self.state.building_levels @ self.problem.net_matrix[:, terminal_position]
        )
        chain = self.processes("realized")
        system_levels = self.state.building_levels
        system_gdp = self.state.gdp_weekly
        chain_gdp = float(np.asarray(chain["value_added"], dtype=np.float64).sum())
        system_employment = self.state.total_population
        chain_employment = float(
            np.asarray(chain["employment"], dtype=np.float64).sum()
        )
        system_construction = float(system_levels @ self.construction_cost_vector)
        chain_construction = float(
            np.asarray(chain["construction_cost"], dtype=np.float64).sum()
        )
        system_land = float(system_levels @ self.arable_land_vector)
        chain_land = float(np.asarray(chain["arable_land"], dtype=np.float64).sum())
        system_infrastructure = float(system_levels @ self.infrastructure_vector)
        chain_infrastructure = float(
            np.asarray(chain["net_infrastructure_usage"], dtype=np.float64).sum()
        )
        realized_cycles = cyclic_nodes(self.realized_graph)
        realized_processes = self.processes("realized")
        allowed_processes = self.processes("allowed")
        values: dict[str, object] = {
            "scenario": self.scenario.display_name(),
            "terminal_good": self.terminal_good,
            "objective": self.scenario.objective,
            "solver_status": self.diagnostics.status,
            "solver_message": self.diagnostics.message,
            "objective_value": self.diagnostics.objective_value,
            "target_quantity": self.target_quantity,
            "target_base_value": self.target_quantity
            * float(self.state.market_prices[terminal_position]),
            "terminal_base_price": float(self.state.market_prices[terminal_position]),
            "terminal_gross_output": terminal_output,
            "terminal_net_output": terminal_net,
            "terminal_surplus": terminal_net - self.target_quantity,
            "system_gdp_weekly": system_gdp,
            "system_gdp_annual": system_gdp * 52.0,
            "chain_gdp_weekly": chain_gdp,
            "chain_gdp_annual": chain_gdp * 52.0,
            "system_employment": system_employment,
            "chain_employment": chain_employment,
            "system_construction_cost": system_construction,
            "chain_construction_cost": chain_construction,
            "system_arable_land": system_land,
            "chain_arable_land": chain_land,
            "system_net_infrastructure_usage": system_infrastructure,
            "chain_net_infrastructure_usage": chain_infrastructure,
            "employment_per_terminal_unit": _safe_divide(
                chain_employment, terminal_net
            ),
            "construction_per_terminal_unit": _safe_divide(
                chain_construction, terminal_net
            ),
            "gdp_per_terminal_unit": _safe_divide(chain_gdp, terminal_net),
            "output_per_10k_workers": _safe_divide(
                terminal_net * 10_000.0, chain_employment
            ),
            "realized_process_count": len(realized_processes),
            "realized_good_count": sum(
                data.get("kind") == "good"
                for _node, data in self.realized_graph.nodes(data=True)
            ),
            "realized_edge_count": self.realized_graph.number_of_edges(),
            "allowed_process_count": len(allowed_processes),
            "allowed_good_count": sum(
                data.get("kind") == "good"
                for _node, data in self.allowed_graph.nodes(data=True)
            ),
            "allowed_edge_count": self.allowed_graph.number_of_edges(),
            "cyclic_component_count": cyclic_component_count(self.realized_graph),
            "cyclic_node_count": len(realized_cycles),
            "condensation_depth": condensation_depth(self.realized_graph),
            "extractive_process_count": int(
                np.asarray(realized_processes["is_extractive"], dtype=bool).sum()
            ),
            "resource_process_count": int(
                (
                    np.asarray(realized_processes["discoverable_resource"], dtype=bool)
                    | np.asarray(realized_processes["depletable_resource"], dtype=bool)
                ).sum()
            ),
            "chain_gdp_share": _safe_divide(chain_gdp, system_gdp),
            "chain_employment_share": _safe_divide(chain_employment, system_employment),
            "chain_construction_share": _safe_divide(
                chain_construction, system_construction
            ),
            "chain_arable_land_share": _safe_divide(chain_land, system_land),
            "chain_infrastructure_share": _safe_divide(
                chain_infrastructure, system_infrastructure
            ),
        }
        return pd.Series(values, index=SUMMARY_FIELDS, name=self.terminal_good)

    def to_mermaid(
        self,
        view: str = "realized",
        *,
        max_producers_per_good: int = 3,
    ) -> str:
        """Return a deterministic Mermaid representation."""
        from vic3_analysis.analysis.supply_chain.visualization import to_mermaid

        return to_mermaid(
            self,
            view=view,
            max_producers_per_good=max_producers_per_good,
        )

    def plot_network(
        self,
        view: str = "realized",
        *,
        metric: str = "value",
        max_producers_per_good: int = 3,
    ) -> Figure:
        """Return a deterministic weighted network figure."""
        from vic3_analysis.analysis.supply_chain.visualization import plot_network

        return plot_network(
            self,
            view=view,
            metric=metric,
            max_producers_per_good=max_producers_per_good,
        )

    def plot_contributions(
        self,
        metric: str = "gdp",
        *,
        scope: str = "chain",
        top_n: int = 15,
    ) -> Figure:
        """Return a process-contribution bar chart."""
        from vic3_analysis.analysis.supply_chain.visualization import (
            plot_contributions,
        )

        return plot_contributions(self, metric=metric, scope=scope, top_n=top_n)

    def plot_goods_balance(self, *, top_n: int = 15) -> Figure:
        """Return a goods supply-and-demand chart."""
        from vic3_analysis.analysis.supply_chain.visualization import (
            plot_goods_balance,
        )

        return plot_goods_balance(self, top_n=top_n)

    def plot_constraints(self, *, top_n: int = 15) -> Figure:
        """Return a binding-constraint marginal chart."""
        from vic3_analysis.analysis.supply_chain.visualization import (
            plot_constraints,
        )

        return plot_constraints(self, top_n=top_n)


@dataclass(frozen=True)
class SupplyChainSweepResult:
    """Result of applying one scenario template across terminal goods."""

    _summary: pd.DataFrame = field(repr=False)
    _failures: pd.DataFrame = field(repr=False)
    _results: Mapping[str, SupplyChainResult] = field(repr=False)

    def __post_init__(self) -> None:
        object.__setattr__(self, "_summary", self._summary.copy(deep=True))
        object.__setattr__(self, "_failures", self._failures.copy(deep=True))
        object.__setattr__(self, "_results", MappingProxyType(dict(self._results)))

    @property
    def summary(self) -> pd.DataFrame:
        """Return one fixed-schema row per requested good."""
        return self._summary.copy(deep=True)

    @property
    def failures(self) -> pd.DataFrame:
        """Return unsuccessful sweep rows."""
        return self._failures.copy(deep=True)

    @property
    def results(self) -> Mapping[str, SupplyChainResult]:
        """Return retained successful results, empty when not requested."""
        return self._results

    def result_for(self, good: str) -> SupplyChainResult:
        """Return the retained analysis for *good*."""
        if good not in self._results:
            raise KeyError(
                f"No retained result for {good!r}; use keep_results=True and "
                "ensure the analysis succeeds."
            )
        return self._results[good]
