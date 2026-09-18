"""Graph construction for supply-chain analyses."""

from __future__ import annotations

import re
from collections.abc import Iterable
from typing import Literal

import networkx as nx
import numpy as np
import pandas as pd

from vic3_analysis.optimize.scenario import Scenario

SupplyChainView = Literal["realized", "allowed"]


def good_node_id(good: str) -> str:
    """Return the stable graph node identifier for a good."""
    return f"good:{good}"


def process_node_id(config: str) -> str:
    """Return the stable graph node identifier for a production configuration."""
    return f"process:{config}"


def validate_view(view: str) -> SupplyChainView:
    """Validate and narrow a supply-chain view name."""
    if view not in ("realized", "allowed"):
        raise ValueError(f"view must be 'realized' or 'allowed', got {view!r}")
    return view


def allowed_process_mask(
    production: pd.DataFrame,
    scenario: Scenario,
    *,
    tolerance: float,
) -> np.ndarray:
    """Return configurations not statically disabled by *scenario*."""
    allowed = np.ones(len(production), dtype=bool)
    if scenario.era_cap is not None:
        allowed &= production["era"].to_numpy(dtype=np.float64) <= scenario.era_cap
    if scenario.banned_pms:
        pattern = re.compile(
            r"\b(?:" + "|".join(re.escape(key) for key in scenario.banned_pms) + r")\b"
        )
        allowed &= (
            ~production["production_method"]
            .astype(str)
            .str.contains(pattern, na=False)
            .to_numpy()
        )
    if scenario.banned_building_groups:
        allowed &= (
            ~production["building_group"]
            .isin(scenario.banned_building_groups)
            .to_numpy()
        )
    if scenario.building_limits:
        buildings = production["building"].astype(str).to_numpy()
        for building, limit in scenario.building_limits:
            if float(limit) <= tolerance:
                allowed &= buildings != building
    return allowed


def _metadata_value(row: pd.Series, name: str, default: object) -> object:
    """Return one process metadata value with a stable missing-value default."""
    value = row.get(name, default)
    if value is None or value is pd.NA or value is pd.NaT:
        return default
    if isinstance(value, (float, np.floating)) and np.isnan(value):
        return default
    return value


def _is_extractive(row: pd.Series) -> bool:
    """Return whether a production row represents resource extraction."""
    return bool(
        _metadata_value(row, "parent_group", "") == "bg_extraction"
        or _metadata_value(row, "discoverable_resource", False)
        or _metadata_value(row, "depletable_resource", False)
    )


def build_supply_graph(
    *,
    production: pd.DataFrame,
    goods_index: tuple[str, ...],
    config_index: tuple[str, ...],
    input_matrix: np.ndarray,
    output_matrix: np.ndarray,
    levels: np.ndarray,
    prices: np.ndarray,
    terminal_good: str,
    selected_processes: np.ndarray,
    allowed_processes: np.ndarray,
    tolerance: float,
) -> nx.DiGraph:
    """Build an upstream-restricted bipartite goods/process graph."""
    graph = nx.DiGraph()
    active = levels > tolerance
    for i in np.flatnonzero(selected_processes):
        row = production.iloc[int(i)]
        config = config_index[int(i)]
        process_id = process_node_id(config)
        graph.add_node(
            process_id,
            kind="process",
            key=config,
            row=int(i),
            building=str(row["building"]),
            production_method=str(row["production_method"]),
            building_group=str(row.get("building_group", "")),
            parent_group=str(_metadata_value(row, "parent_group", "")),
            land_usage=str(_metadata_value(row, "land_usage", "")),
            era=int(row["era"]),
            active=bool(active[i]),
            allowed=bool(allowed_processes[i]),
            level=float(levels[i]),
            is_extractive=_is_extractive(row),
            is_subsistence=bool(_metadata_value(row, "is_subsistence", False)),
            discoverable_resource=bool(
                _metadata_value(row, "discoverable_resource", False)
            ),
            depletable_resource=bool(
                _metadata_value(row, "depletable_resource", False)
            ),
        )
        for j in np.flatnonzero(input_matrix[i] > 0.0):
            good = goods_index[int(j)]
            good_id = good_node_id(good)
            graph.add_node(
                good_id,
                kind="good",
                key=good,
                terminal=good == terminal_good,
            )
            rate = float(input_matrix[i, j])
            amount = rate * float(levels[i])
            graph.add_edge(
                good_id,
                process_id,
                role="input",
                good=good,
                process=config,
                unit_rate=rate,
                realized_amount=amount,
                price=float(prices[j]),
                realized_value=amount * float(prices[j]),
                active=amount > tolerance,
            )
        for j in np.flatnonzero(output_matrix[i] > 0.0):
            good = goods_index[int(j)]
            good_id = good_node_id(good)
            graph.add_node(
                good_id,
                kind="good",
                key=good,
                terminal=good == terminal_good,
            )
            rate = float(output_matrix[i, j])
            amount = rate * float(levels[i])
            graph.add_edge(
                process_id,
                good_id,
                role="output",
                good=good,
                process=config,
                unit_rate=rate,
                realized_amount=amount,
                price=float(prices[j]),
                realized_value=amount * float(prices[j]),
                active=amount > tolerance,
            )

    terminal_id = good_node_id(terminal_good)
    if terminal_id not in graph:
        graph.add_node(
            terminal_id,
            kind="good",
            key=terminal_good,
            terminal=True,
        )
        return graph
    upstream = nx.ancestors(graph, terminal_id)
    upstream_processes = {
        node for node in upstream if graph.nodes[node].get("kind") == "process"
    }
    chain_nodes = set(upstream) | {terminal_id}
    for process in upstream_processes:
        chain_nodes.update(graph.predecessors(process))
        chain_nodes.update(graph.successors(process))
    return graph.subgraph(chain_nodes).copy()


def cyclic_nodes(graph: nx.DiGraph) -> frozenset[str]:
    """Return nodes participating in a directed cycle."""
    result: set[str] = set()
    for component in nx.strongly_connected_components(graph):
        if len(component) > 1:
            result.update(component)
        elif component:
            node = next(iter(component))
            if graph.has_edge(node, node):
                result.add(node)
    return frozenset(result)


def cyclic_component_count(graph: nx.DiGraph) -> int:
    """Return the number of strongly connected components containing a cycle."""
    count = 0
    for component in nx.strongly_connected_components(graph):
        if len(component) > 1:
            count += 1
        elif component:
            node = next(iter(component))
            count += int(graph.has_edge(node, node))
    return count


def condensation_depth(graph: nx.DiGraph) -> int:
    """Return the longest-path depth after directed cycles are condensed."""
    if graph.number_of_nodes() == 0:
        return 0
    condensed = nx.condensation(graph)
    if condensed.number_of_nodes() <= 1:
        return 0
    return int(nx.dag_longest_path_length(condensed))


def process_rows(graph: nx.DiGraph) -> tuple[int, ...]:
    """Return production-table rows present in *graph*, in row order."""
    rows = [
        int(data["row"])
        for _node, data in graph.nodes(data=True)
        if data.get("kind") == "process"
    ]
    return tuple(sorted(rows))


def good_keys(graph: nx.DiGraph, goods_index: Iterable[str]) -> tuple[str, ...]:
    """Return graph goods in economy order."""
    present = {
        str(data["key"])
        for _node, data in graph.nodes(data=True)
        if data.get("kind") == "good"
    }
    return tuple(good for good in goods_index if good in present)
