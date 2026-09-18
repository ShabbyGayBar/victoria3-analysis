"""Matplotlib and Mermaid renderers for supply-chain results."""

from __future__ import annotations

import networkx as nx
import numpy as np
from matplotlib import pyplot as plt
from matplotlib.figure import Figure

from vic3_analysis.analysis.supply_chain.graph import (
    cyclic_nodes,
    good_node_id,
    validate_view,
)
from vic3_analysis.analysis.supply_chain.result import SupplyChainResult


def _display_graph(
    result: SupplyChainResult,
    view: str,
    max_producers_per_good: int,
) -> nx.DiGraph:
    narrowed = validate_view(view)
    graph = result.graph(narrowed)
    if narrowed == "realized":
        return graph
    if max_producers_per_good <= 0:
        raise ValueError("max_producers_per_good must be positive.")

    selected_processes: set[str] = {
        node
        for node, data in graph.nodes(data=True)
        if data.get("kind") == "process" and data.get("active")
    }
    for good_node, node_data in graph.nodes(data=True):
        if node_data.get("kind") != "good":
            continue
        producers = [
            predecessor
            for predecessor in graph.predecessors(good_node)
            if graph.nodes[predecessor].get("kind") == "process"
        ]
        producers.sort(
            key=lambda process: (
                -float(graph.edges[process, good_node]["unit_rate"]),
                str(graph.nodes[process]["key"]),
            )
        )
        selected_processes.update(producers[:max_producers_per_good])

    nodes: set[str] = set(selected_processes)
    for process in selected_processes:
        nodes.update(graph.predecessors(process))
        nodes.update(graph.successors(process))
    terminal = good_node_id(result.terminal_good)
    return graph.subgraph(nodes | {terminal}).copy()


def _escape_mermaid(value: object) -> str:
    return str(value).replace('"', "'")


def to_mermaid(
    result: SupplyChainResult,
    *,
    view: str,
    max_producers_per_good: int,
) -> str:
    """Render a deterministic Mermaid bipartite flowchart."""
    graph = _display_graph(result, view, max_producers_per_good)
    ordered_nodes = sorted(graph.nodes())
    identifiers = {node: f"n{i}" for i, node in enumerate(ordered_nodes)}
    cycles = cyclic_nodes(graph)
    lines = ["flowchart LR"]
    for node in ordered_nodes:
        data = graph.nodes[node]
        identifier = identifiers[node]
        if data.get("kind") == "good":
            label = _escape_mermaid(data["key"])
            suffix = " ★" if data.get("terminal") else ""
            lines.append(f'    {identifier}(("{label}{suffix}"))')
        else:
            label = _escape_mermaid(data.get("building", data["key"]))
            level = float(data.get("level", 0.0))
            active = " | active" if data.get("active") else ""
            lines.append(f'    {identifier}["{label}<br/>lvl={level:.4g}{active}"]')
    for source, target, data in sorted(graph.edges(data=True)):
        amount = float(data["realized_amount"])
        rate = float(data["unit_rate"])
        label = f"{amount:.4g}" if amount > result.tolerance else f"r={rate:.4g}"
        arrow = "-.->" if source in cycles and target in cycles else "-->"
        lines.append(
            f'    {identifiers[source]} {arrow}|"{label}"| {identifiers[target]}'
        )
    process_cycle = [identifiers[node] for node in ordered_nodes if node in cycles]
    resource_nodes = [
        identifiers[node]
        for node in ordered_nodes
        if graph.nodes[node].get("kind") == "process"
        and graph.nodes[node].get("is_extractive")
    ]
    active_nodes = [
        identifiers[node]
        for node in ordered_nodes
        if graph.nodes[node].get("kind") == "process"
        and graph.nodes[node].get("active")
    ]
    if process_cycle:
        lines.append(f"    class {','.join(process_cycle)} cyclic")
    if resource_nodes:
        lines.append(f"    class {','.join(resource_nodes)} resource")
    if active_nodes:
        lines.append(f"    class {','.join(active_nodes)} active")
    lines.extend(
        [
            "    classDef cyclic stroke:#d97706,stroke-width:2px",
            "    classDef resource fill:#dcfce7,stroke:#15803d",
            "    classDef active fill:#dbeafe,stroke:#1d4ed8",
        ]
    )
    return "\n".join(lines)


def plot_network(
    result: SupplyChainResult,
    *,
    view: str,
    metric: str,
    max_producers_per_good: int,
) -> Figure:
    """Plot a deterministic weighted bipartite network."""
    if metric not in ("quantity", "value"):
        raise ValueError("metric must be 'quantity' or 'value'.")
    graph = _display_graph(result, view, max_producers_per_good)
    figure, axis = plt.subplots(figsize=(14, 9), layout="constrained")
    if graph.number_of_nodes() == 0:
        axis.text(0.5, 0.5, "No supply-chain nodes", ha="center", va="center")
        axis.axis("off")
        return figure

    positions = nx.spring_layout(graph, seed=42, k=1.5 / np.sqrt(len(graph)))
    goods = [
        node for node, data in graph.nodes(data=True) if data.get("kind") == "good"
    ]
    processes = [
        node for node, data in graph.nodes(data=True) if data.get("kind") == "process"
    ]
    process_colors = [
        "#86efac"
        if graph.nodes[node].get("is_extractive")
        else "#93c5fd"
        if graph.nodes[node].get("active")
        else "#d1d5db"
        for node in processes
    ]
    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=goods,
        node_color=[
            "#fca5a5" if graph.nodes[node].get("terminal") else "#fde68a"
            for node in goods
        ],
        node_shape="o",
        node_size=900,
        ax=axis,
    )
    nx.draw_networkx_nodes(
        graph,
        positions,
        nodelist=processes,
        node_color=process_colors,
        node_shape="s",
        node_size=500,
        ax=axis,
    )
    attribute = "realized_amount" if metric == "quantity" else "realized_value"
    weights = np.asarray(
        [float(data[attribute]) for _u, _v, data in graph.edges(data=True)],
        dtype=np.float64,
    )
    if weights.size == 0 or float(weights.max()) == 0.0:
        widths = np.ones(graph.number_of_edges())
        edge_colors = [(0.39, 0.45, 0.55, 1.0)] * graph.number_of_edges()
    else:
        widths = 0.5 + 4.5 * weights / float(weights.max())
        color_map = plt.get_cmap("viridis")
        edge_colors: list[tuple[float, float, float, float]] = []
        for weight in weights:
            red, green, blue, alpha = color_map(weight / weights.max())
            edge_colors.append((float(red), float(green), float(blue), float(alpha)))
    nx.draw_networkx_edges(
        graph,
        positions,
        width=widths.tolist(),
        edge_color=edge_colors,
        alpha=0.75,
        arrows=True,
        ax=axis,
    )
    labels = {
        node: str(data["key"])
        if data.get("kind") == "good"
        else str(data.get("building", data["key"])).removeprefix("building_")
        for node, data in graph.nodes(data=True)
    }
    nx.draw_networkx_labels(graph, positions, labels=labels, font_size=7, ax=axis)
    axis.set_title(
        f"{result.terminal_good} supply chain ({view}, weighted by {metric})"
    )
    axis.axis("off")
    return figure


def plot_contributions(
    result: SupplyChainResult,
    *,
    metric: str,
    scope: str,
    top_n: int,
) -> Figure:
    """Plot leading process contributions."""
    metric_columns = {
        "gdp": "value_added",
        "employment": "employment",
        "construction_cost": "construction_cost",
        "input_cost": "input_cost",
        "output_value": "output_value",
    }
    if metric not in metric_columns:
        raise ValueError(f"Unknown contribution metric: {metric!r}")
    if scope not in ("chain", "system"):
        raise ValueError("scope must be 'chain' or 'system'.")
    if top_n <= 0:
        raise ValueError("top_n must be positive.")
    if scope == "chain":
        frame = result.processes("realized")
    else:
        rows = tuple(
            int(row)
            for row in np.flatnonzero(result.state.building_levels > result.tolerance)
        )
        frame = result._process_table(rows)
    column = metric_columns[metric]
    order = np.argsort(-np.abs(frame[column].to_numpy(dtype=np.float64)))
    frame = frame.iloc[order].head(top_n)
    figure, axis = plt.subplots(figsize=(10, 6), layout="constrained")
    if frame.empty:
        axis.text(0.5, 0.5, "No process contributions", ha="center", va="center")
        axis.axis("off")
        return figure
    labels = frame["building"].astype(str).str.removeprefix("building_")
    axis.barh(labels.iloc[::-1], frame[column].iloc[::-1], color="#3b82f6")
    axis.set_xlabel(column.replace("_", " "))
    axis.set_title(f"Top {scope} process contributions: {metric}")
    return figure


def plot_goods_balance(result: SupplyChainResult, *, top_n: int) -> Figure:
    """Plot leading realized good supply and demand."""
    if top_n <= 0:
        raise ValueError("top_n must be positive.")
    frame = result.goods("realized").copy()
    frame["activity"] = frame["sell_orders"] + frame["buy_orders"]
    frame = frame.sort_values("activity", ascending=False).head(top_n)
    figure, axis = plt.subplots(figsize=(11, 6), layout="constrained")
    if frame.empty:
        axis.text(0.5, 0.5, "No good balances", ha="center", va="center")
        axis.axis("off")
        return figure
    positions = np.arange(len(frame))
    axis.bar(positions - 0.2, frame["sell_orders"], width=0.4, label="supply")
    axis.bar(positions + 0.2, frame["buy_orders"], width=0.4, label="demand")
    axis.set_xticks(positions, frame["good"], rotation=45, ha="right")
    axis.set_ylabel("weekly quantity")
    axis.set_title(f"{result.terminal_good} chain goods balance")
    axis.legend()
    return figure


def plot_constraints(result: SupplyChainResult, *, top_n: int) -> Figure:
    """Plot leading binding-constraint improvement values."""
    if top_n <= 0:
        raise ValueError("top_n must be positive.")
    frame = result.bottlenecks().head(top_n)
    figure, axis = plt.subplots(figsize=(10, 6), layout="constrained")
    if frame.empty:
        axis.text(
            0.5,
            0.5,
            "No binding constraints with useful marginals",
            ha="center",
            va="center",
        )
        axis.axis("off")
        return figure
    labels = frame["family"].astype(str) + ": " + frame["label"].astype(str)
    axis.barh(
        labels.iloc[::-1],
        frame["improvement_per_unit"].iloc[::-1],
        color="#f59e0b",
    )
    axis.set_xlabel("objective improvement per relaxed unit")
    axis.set_title("Binding supply-chain constraints")
    return figure
