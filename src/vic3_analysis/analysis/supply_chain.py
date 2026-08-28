"""
Supply-chain analysis for the nominal Victoria 3 economy.

Builds on :class:`~vic3_analysis.analysis.economy.Economy` and
:class:`~vic3_analysis.optimize.nominal.NominalOptimizer` to provide:

* :class:`Scenario` - a cangshulun-style optimisation recipe expressed as data.
* :func:`upstream_tree` - the structured upstream dependency tree of a good
  (recipe or realised view).
* :func:`to_mermaid` - serialise a supply-chain graph to a Mermaid flowchart
  string (recipe or realised view) for rendering in GitHub/MkDocs.
* :func:`build_optimizer` / :func:`optimize_chain` - turn a :class:`Scenario`
  into a configured :class:`NominalOptimizer` or a solved
  :class:`~vic3_analysis.analysis.economy.EconomyState`.
* :func:`value_added_breakdown` - per-config or per-good attribution of GDP,
  employment, and construction cost (chain-scoped or whole-economy).
* :func:`bottleneck` - rank input goods by cost share and, when available,
  report LP shadow prices for the import caps.
* :func:`compare_scenarios` - run multiple scenarios and tabulate metrics.
"""

from dataclasses import dataclass
from typing import Iterable, Iterator

import numpy as np
import pandas as pd

from vic3_analysis.analysis.economy import Economy, EconomyState
from vic3_analysis.optimize.nominal import NominalOptimizer

_TOL = 1e-10


@dataclass(frozen=True)
class Scenario:
    """A cangshulun-style optimisation recipe expressed as data.

    Captures the knobs varied by the ``cangshulun_1`` / ``cangshulun_2`` example
    scripts (terminal good, objective, autarky, banned production methods and
    buildings, throughput bonuses, era cap) so a supply-chain optimisation can
    be re-used and compared without re-writing the constraint plumbing.

    Attributes:
        terminal_good: Good key that the economy must produce (passed to
            :meth:`NominalOptimizer.constraint_produce`).
        target_amount: Minimum net production required of *terminal_good*.
        objective: Named objective. One of ``"gdp"`` (maximise gross GDP),
            ``"employment"`` (maximise total employment), ``"automation"``
            (minimise total employment, i.e. maximise automation) or
            ``"construction_cost"`` (minimise total construction cost).
        autarky: If ``True`` (default), append
            :meth:`NominalOptimizer.constraint_limit_import` with limit ``0``
            so the economy is self-sufficient.
        banned_pms: Production-method identifiers banned via
            :meth:`NominalOptimizer.constraint_ban_pm`.
        banned_buildings: Building identifiers forced to level zero via
            :meth:`NominalOptimizer.constraint_ban_building`.
        throughput_bonuses: Sequence of ``(building_key, multiplier)`` pairs
            applied via :meth:`NominalOptimizer.add_throughput_bonus`.
        era_cap: If not ``None``, cap configurations to this era via
            :meth:`NominalOptimizer.constraint_limit_era`.
        construction_cost_cap: If not ``None``, cap total construction cost.
        employment_cap: If not ``None``, cap total employment.
        name: Optional display name; defaults to *terminal_good* when ``None``.
    """

    terminal_good: str
    target_amount: float
    objective: str = "automation"
    autarky: bool = True
    banned_pms: tuple[str, ...] = ()
    banned_buildings: tuple[str, ...] = ()
    throughput_bonuses: tuple[tuple[str, float], ...] = ()
    era_cap: int | None = None
    construction_cost_cap: float | None = None
    employment_cap: float | None = None
    name: str | None = None

    def display_name(self) -> str:
        """Return the scenario name, falling back to the terminal good."""
        return self.name if self.name is not None else self.terminal_good


@dataclass(frozen=True)
class ProducerNode:
    """One building configuration that produces a good in a supply chain.

    Attributes:
        config: The ``"building+production_method"`` configuration key.
        building: Building identifier.
        production_method: Concatenated production-method string.
        building_group: Building-group identifier (``""`` if absent).
        era: Earliest era at which the configuration unlocks.
        employment: Employment per building level (recipe) or scaled by level
            (realised).
        construction_cost: Construction cost per level, or scaled by level.
        outputs: Mapping of output good to amount (per level or scaled).
        inputs: Mapping of input good to amount (per level or scaled).
        level: ``1.0`` in recipe mode, the solved level in realised mode.
        upstream: Upstream nodes for each input good (in insertion order).
    """

    config: str
    building: str
    production_method: str
    building_group: str
    era: int
    employment: float
    construction_cost: float
    outputs: dict[str, float]
    inputs: dict[str, float]
    level: float
    upstream: tuple["SupplyChainNode", ...]


@dataclass(frozen=True)
class SupplyChainNode:
    """A good and the producer configurations that supply it in a chain.

    Attributes:
        good: The good key this node describes.
        producers: Producer configurations that output *good* (empty for raw
            resources).
        is_raw: ``True`` when *good* has no producers (a raw-resource leaf).
    """

    good: str
    producers: tuple[ProducerNode, ...]
    is_raw: bool


def build_optimizer(economy: Economy, scenario: Scenario) -> NominalOptimizer:
    """Configure a :class:`NominalOptimizer` from a :class:`Scenario`.

    Applies throughput bonuses (before setting the objective so the GDP vector
    reflects them), then the objective via :meth:`NominalOptimizer.set_objective`
    (which accepts ``"automation"`` to minimise employment), then the constraints
    in a fixed order: autarky (first, so its import-cap marginals lead the
    inequality block), era cap, construction-cost cap, employment cap, banned
    PMs, banned buildings, and finally the terminal-good production constraint.
    Does not call :meth:`NominalOptimizer.linprog`; call it (or
    :func:`optimize_chain`) to solve.

    Args:
        economy: The :class:`Economy` to optimise over.
        scenario: The recipe to apply.

    Returns:
        A configured :class:`NominalOptimizer` ready for :meth:`linprog`.

    Raises:
        ValueError: If the scenario objective is unknown or *terminal_good*
            is not present in the goods index.
    """
    optimizer = NominalOptimizer(economy, objective="gdp")
    for building_key, multiplier in scenario.throughput_bonuses:
        optimizer.add_throughput_bonus(building_key, multiplier)
    optimizer.set_objective(scenario.objective)
    if scenario.autarky:
        optimizer.constraint_limit_import(0.0)
    if scenario.era_cap is not None:
        optimizer.constraint_limit_era(scenario.era_cap)
    if scenario.construction_cost_cap is not None:
        optimizer.constraint_limit_construction_cost(scenario.construction_cost_cap)
    if scenario.employment_cap is not None:
        optimizer.constraint_limit_employment(scenario.employment_cap)
    if scenario.banned_pms:
        optimizer.constraint_ban_pm(list(scenario.banned_pms))
    if scenario.banned_buildings:
        optimizer.constraint_ban_building(list(scenario.banned_buildings))
    optimizer.constraint_produce(scenario.terminal_good, scenario.target_amount)
    return optimizer


def optimize_chain(economy: Economy, scenario: Scenario) -> EconomyState:
    """Solve a :class:`Scenario` and return the resulting :class:`EconomyState`.

    Equivalent to ``build_optimizer(economy, scenario).linprog()``.

    Args:
        economy: The :class:`Economy` to optimise over.
        scenario: The recipe to solve.

    Returns:
        The optimal :class:`EconomyState`.
    """
    return build_optimizer(economy, scenario).linprog()


def upstream_tree(
    economy: Economy,
    good: str,
    state: EconomyState | None = None,
    max_depth: int = 64,
) -> SupplyChainNode:
    """Build the upstream dependency graph of *good*.

    Uses the separate goods input/output matrices (not the net matrix) so
    producers and consumers are distinguished.  Two modes:

    * **Recipe** (``state is None``): every configuration that can produce
      *good* appears, with per-level flows and ``level == 1.0``.
    * **Realised** (``state`` given): only configurations with non-zero solved
      level appear, and flows, employment, and construction cost are scaled by
      the solved level.

    Nodes are memoised per good, so the result is a rooted DAG with shared
    subtrees (an intermediate good fed by several producers is expanded once and
    referenced by each parent) rather than an exponentially-branching tree.
    Cycles (a good reappearing on its own recursion path) are broken by
    rendering the repeat as a raw leaf; a depth guard does the same past
    *max_depth*.

    Args:
        economy: The :class:`Economy` whose production table is traced.
        good: The terminal good key to trace upstream from.
        state: Optional solved state for the realised view.
        max_depth: Recursion guard against pathological deep graphs.

    Returns:
        The :class:`SupplyChainNode` rooted at *good*.

    Raises:
        ValueError: If *good* is not present in the goods index.
    """
    goods_index = economy.goods_index()
    if good not in goods_index:
        raise ValueError(f"Good '{good}' not found in goods index.")
    good_to_col = {g: j for j, g in enumerate(goods_index)}

    out_mat = economy.goods_output_matrix()
    in_mat = economy.goods_input_matrix()
    df = economy.df_production
    n_configs = len(df)
    buildings = df["building"].to_numpy()
    pms = df["production_method"].to_numpy()
    if "building_group" in df.columns:
        groups = df["building_group"].fillna("").to_numpy()
    else:
        groups = np.array([""] * n_configs, dtype=object)
    eras = df["era"].to_numpy(dtype=int)
    employments = df["employment"].fillna(0).to_numpy(dtype=np.float64)
    costs = df["construction_cost"].to_numpy(dtype=np.float64)
    config_keys = economy.building_index()

    levels = state.building_levels if state is not None else None
    cache: dict[str, SupplyChainNode] = {}
    on_path: set[str] = set()

    def _node(current_good: str, depth: int) -> SupplyChainNode:
        cached = cache.get(current_good)
        if cached is not None:
            return cached
        if current_good in on_path or depth >= max_depth:
            return SupplyChainNode(good=current_good, producers=(), is_raw=True)
        on_path.add(current_good)
        col = good_to_col[current_good]
        producer_rows = np.nonzero(out_mat[:, col] > 0.0)[0]
        if levels is not None:
            producer_rows = producer_rows[levels[producer_rows] > _TOL]
        producers: list[ProducerNode] = []
        for row in producer_rows:
            i = int(row)
            scale = float(levels[i]) if levels is not None else 1.0
            outs = {
                g: float(out_mat[i, j]) * scale
                for j, g in enumerate(goods_index)
                if out_mat[i, j] > 0.0
            }
            ins = {
                g: float(in_mat[i, j]) * scale
                for j, g in enumerate(goods_index)
                if in_mat[i, j] > 0.0
            }
            children = [_node(input_good, depth + 1) for input_good in ins]
            producers.append(
                ProducerNode(
                    config=config_keys[i],
                    building=str(buildings[i]),
                    production_method=str(pms[i]),
                    building_group=str(groups[i]),
                    era=int(eras[i]),
                    employment=float(employments[i]) * scale,
                    construction_cost=float(costs[i]) * scale,
                    outputs=outs,
                    inputs=ins,
                    level=scale,
                    upstream=tuple(children),
                )
            )
        on_path.discard(current_good)
        node = SupplyChainNode(
            good=current_good,
            producers=tuple(producers),
            is_raw=len(producers) == 0,
        )
        cache[current_good] = node
        return node

    return _node(good, 0)


def iter_producers(node: SupplyChainNode) -> Iterator[ProducerNode]:
    """Yield every :class:`ProducerNode` reachable from *node*, depth-first.

    Each :class:`SupplyChainNode` is visited once (tracked by identity), so
    traversal is linear in the number of distinct good-nodes rather than
    exponential in the chain depth.  Victoria 3 has genuine good-level cycles
    (e.g. ``steel`` <-> ``tools``), so a visited guard is required to avoid
    re-traversing shared or cyclic intermediates.  Callers aggregating metrics
    should still de-duplicate by :attr:`ProducerNode.config` if a configuration
    appears under several goods.

    Args:
        node: The root :class:`SupplyChainNode`.

    Yields:
        Each :class:`ProducerNode` reachable from *node*.
    """
    visited: set[int] = set()
    stack: list[SupplyChainNode] = [node]
    while stack:
        current = stack.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        for producer in current.producers:
            yield producer
            for child in reversed(producer.upstream):
                stack.append(child)


def _collect_producers(node: SupplyChainNode) -> dict[str, ProducerNode]:
    """Return unique producer configs in a tree keyed by config string."""
    result: dict[str, ProducerNode] = {}
    for producer in iter_producers(node):
        if producer.config not in result:
            result[producer.config] = producer
    return result


def _collect_good_nodes(node: SupplyChainNode) -> dict[str, SupplyChainNode]:
    """Return all unique good-nodes in a DAG, preferring non-raw expansions.

    Cycle-broken raw leaves share the same good key as the fully-expanded
    cached node; this helper keeps the non-raw version so producers are not
    lost.  Visits each node object once (tracked by identity) to avoid
    exponential re-traversal of shared DAG subtrees.
    """
    result: dict[str, SupplyChainNode] = {}
    visited: set[int] = set()
    stack: list[SupplyChainNode] = [node]
    while stack:
        current = stack.pop()
        if id(current) in visited:
            continue
        visited.add(id(current))
        existing = result.get(current.good)
        if existing is None or (existing.is_raw and not current.is_raw):
            result[current.good] = current
        for producer in current.producers:
            for child in producer.upstream:
                stack.append(child)
    return result


def _mermaid_id(prefix: str, key: str) -> str:
    """Sanitise *key* into a Mermaid-safe node ID with *prefix*."""
    return prefix + "".join(c if c.isalnum() else "_" for c in key)


def to_mermaid(
    node: SupplyChainNode,
    *,
    realized: bool = False,
    direction: str = "LR",
    title: str | None = None,
) -> str:
    """Serialise a supply-chain graph to a Mermaid flowchart string.

    Two rendering modes:

    * **Recipe** (``realized=False``, default): aggregated good→good dependency
      DAG.  Producer configurations are collapsed so each edge represents "to
      produce *B*, input *A* is required".  The node label includes the producer
      count (e.g. ``steel (5)``).  Mutual dependencies (e.g. ``steel ↔ tools``)
      are rendered as dashed edges.
    * **Realised** (``realized=True``): full bipartite graph with good nodes
      (rounded) and producer nodes (box, labelled ``building | lvl=…``),
      showing ``input → producer → output`` for every active configuration.

    The returned string is a complete Mermaid ``flowchart`` block that renders
    in GitHub, GitLab, and MkDocs (with ``pymdownx.superfences`` Mermaid
    support).

    Args:
        node: The root :class:`SupplyChainNode` (from :func:`upstream_tree`).
        realized: If ``True``, render the realised bipartite graph; if ``False``
            (default), render the aggregated recipe DAG.
        direction: Mermaid flowchart direction (``"LR"``, ``"TD"``, ``"RL"``,
            ``"BT"``).  Defaults to ``"LR"`` (left-to-right).
        title: Optional comment line prepended to the diagram.

    Returns:
        A Mermaid flowchart string.
    """
    good_nodes = _collect_good_nodes(node)

    lines: list[str] = [f"flowchart {direction}"]
    if title:
        lines.append(f"    %% {title}")

    if realized:
        producers = _collect_producers(node)
        all_goods: set[str] = set(good_nodes.keys())
        for p in producers.values():
            all_goods.update(p.inputs)
            all_goods.update(p.outputs)
        for g in sorted(all_goods):
            lines.append(f'    {_mermaid_id("g_", g)}(("{g}"))')
        for config, p in producers.items():
            label = f"{p.building}<br/>lvl={p.level:.4g}"
            lines.append(f'    {_mermaid_id("p_", config)}["{label}"]')
        for config, p in producers.items():
            pid = _mermaid_id("p_", config)
            for input_good in sorted(p.inputs):
                lines.append(f"    {_mermaid_id('g_', input_good)} --> {pid}")
            for output_good in sorted(p.outputs):
                lines.append(f"    {pid} --> {_mermaid_id('g_', output_good)}")
    else:
        edges: set[tuple[str, str]] = set()
        for g, gnode in good_nodes.items():
            for producer in gnode.producers:
                for input_good in producer.inputs:
                    edges.add((input_good, g))
        all_goods = {g for edge in edges for g in edge} | set(good_nodes.keys())
        for g in sorted(all_goods):
            gn = good_nodes.get(g)
            if gn is not None and not gn.is_raw:
                label = f"{g} ({len(gn.producers)})"
            else:
                label = f"{g} [raw]"
            lines.append(f'    {_mermaid_id("g_", g)}(("{label}"))')
        mutual = {e for e in edges if (e[1], e[0]) in edges}
        for src, dst in sorted(edges):
            arrow = "-.->" if (src, dst) in mutual else "-->"
            lines.append(
                f"    {_mermaid_id('g_', src)} {arrow} {_mermaid_id('g_', dst)}"
            )

    return "\n".join(lines)


def value_added_breakdown(
    economy: Economy,
    state: EconomyState,
    good: str | None = None,
    by: str = "config",
) -> pd.DataFrame:
    """Attribute GDP, employment, and construction cost across the economy.

    Args:
        economy: The :class:`Economy` *state* was solved on.
        state: A solved :class:`EconomyState`.
        good: If given, restrict to the realised upstream chain of *good*
            (configs with non-zero level feeding it).  If ``None``, cover every
            active config in the economy.
        by: Aggregation level.  ``"config"`` (default) yields one row per active
            building configuration; ``"good"`` aggregates each config's metrics
            across its output goods, allocated by output-value share.

    Returns:
        A ``DataFrame``.  For ``by="config"``: columns ``config``, ``building``,
        ``production_method``, ``level``, ``output_value``, ``input_cost``,
        ``gdp``, ``employment``, ``construction_cost`` (sorted by ``gdp``
        descending).  For ``by="good"``: columns ``good``, ``output_value``,
        ``input_cost``, ``gdp``, ``employment``, ``construction_cost``.

    Raises:
        ValueError: If *by* is not ``"config"`` or ``"good"``, or if *good* is
            not in the goods index.
    """
    if by not in ("config", "good"):
        raise ValueError(f"by must be 'config' or 'good', got {by!r}")
    prices = economy.base_prices()
    in_mat = economy.goods_input_matrix()
    out_mat = economy.goods_output_matrix()
    levels = state.building_levels
    emp_vec = economy.df_production["employment"].fillna(0).to_numpy(dtype=np.float64)
    cost_vec = economy.construction_cost_vector()
    goods_index = economy.goods_index()
    config_keys = economy.building_index()
    key_to_i = {k: i for i, k in enumerate(config_keys)}

    if good is not None:
        if good not in goods_index:
            raise ValueError(f"Good '{good}' not found in goods index.")
        tree = upstream_tree(economy, good, state)
        selected = _collect_producers(tree)
        idxs = [key_to_i[k] for k in selected]
    else:
        idxs = [i for i in range(len(config_keys)) if levels[i] > _TOL]

    if by == "config":
        rows: list[dict[str, object]] = []
        for i in idxs:
            level = float(levels[i])
            out_val = float(np.dot(out_mat[i], prices) * level)
            in_cost = float(np.dot(in_mat[i], prices) * level)
            rows.append(
                {
                    "config": config_keys[i],
                    "building": str(economy.df_production["building"].to_numpy()[i]),
                    "production_method": str(
                        economy.df_production["production_method"].to_numpy()[i]
                    ),
                    "level": level,
                    "output_value": out_val,
                    "input_cost": in_cost,
                    "gdp": out_val - in_cost,
                    "employment": float(emp_vec[i]) * level,
                    "construction_cost": float(cost_vec[i]) * level,
                }
            )
        df = pd.DataFrame(rows)
        if not df.empty:
            df = df.sort_values("gdp", ascending=False).reset_index(drop=True)
        return df

    # by == "good": allocate each config's cost-side metrics across its outputs.
    agg: dict[str, dict[str, float]] = {}
    for i in idxs:
        level = float(levels[i])
        out_cols = np.nonzero(out_mat[i] > 0.0)[0]
        if len(out_cols) == 0:
            continue
        out_vals = np.array(
            [out_mat[i, j] * prices[j] * level for j in out_cols], dtype=np.float64
        )
        total_out = float(out_vals.sum())
        total_in_cost = float(np.dot(in_mat[i], prices) * level)
        emp_i = float(emp_vec[i]) * level
        cost_i = float(cost_vec[i]) * level
        n_out = len(out_cols)
        for k, j in enumerate(out_cols):
            g = goods_index[int(j)]
            share = float(out_vals[k] / total_out) if total_out > 0 else 1.0 / n_out
            entry = agg.setdefault(
                g,
                {
                    "output_value": 0.0,
                    "input_cost": 0.0,
                    "employment": 0.0,
                    "construction_cost": 0.0,
                },
            )
            entry["output_value"] += float(out_vals[k])
            entry["input_cost"] += share * total_in_cost
            entry["employment"] += share * emp_i
            entry["construction_cost"] += share * cost_i
    rows_g: list[dict[str, object]] = []
    for g, e in agg.items():
        rows_g.append(
            {
                "good": g,
                "output_value": e["output_value"],
                "input_cost": e["input_cost"],
                "gdp": e["output_value"] - e["input_cost"],
                "employment": e["employment"],
                "construction_cost": e["construction_cost"],
            }
        )
    df = pd.DataFrame(rows_g)
    if not df.empty:
        df = df.sort_values("gdp", ascending=False).reset_index(drop=True)
    return df


def _import_marginals(
    optimizer: NominalOptimizer | None, n_goods: int
) -> np.ndarray | None:
    """Return import-cap shadow prices from a solved optimizer, if available.

    Locates the autarky constraint block by matching its matrix to
    ``-optimizer.goods_matrix.T`` (shape ``(n_goods, n_buildings)``) and slices
    the corresponding marginals from the inequality block.

    Args:
        optimizer: A solved :class:`NominalOptimizer`, or ``None``.
        n_goods: Expected number of goods (length of the import block).

    Returns:
        The import-cap marginal values of length *n_goods*, or ``None`` when no
        solved result or matching block is available.
    """
    if optimizer is None:
        return None
    result = getattr(optimizer, "result", None)
    if result is None:
        return None
    ineqlin = getattr(result, "ineqlin", None)
    if ineqlin is None:
        return None
    marginals = getattr(ineqlin, "marginals", None)
    if marginals is None:
        return None
    marginals_arr = np.asarray(marginals, dtype=np.float64)
    goods_matrix = optimizer.goods_matrix
    target = -goods_matrix.T
    offset = 0
    for A, _b in optimizer.inequality_constraints:
        if (
            A.shape[0] == n_goods
            and A.shape[1] == goods_matrix.shape[0]
            and np.allclose(A, target)
        ):
            return marginals_arr[offset : offset + n_goods]
        offset += A.shape[0]
    return None


def bottleneck(
    economy: Economy,
    state: EconomyState,
    good: str | None = None,
    optimizer: NominalOptimizer | None = None,
) -> pd.DataFrame:
    """Rank the input goods of a chain (or economy) by constrainedness.

    The primary signal is cost share: each input good's share of total input
    cost (valued at base prices).  When *optimizer* has been solved (via
    :meth:`NominalOptimizer.linprog`) and the autarky import caps are present,
    the LP shadow price (marginal) of each good's import cap is also reported -
    the most negative marginal identifies the input whose relaxation would most
    reduce the objective.

    Args:
        economy: The :class:`Economy` *state* was solved on.
        state: A solved :class:`EconomyState`.
        good: If given, restrict to the realised upstream chain of *good*.
        optimizer: Optional solved :class:`NominalOptimizer` whose LP marginals
            are read for shadow prices.

    Returns:
        A ``DataFrame`` with columns ``good``, ``input_cost``, ``cost_share``,
        ``net_supply``, and ``import_marginal`` (``NaN`` when unavailable),
        sorted by ``input_cost`` descending.  Rows with no input cost are
        omitted.

    Raises:
        ValueError: If *good* is not in the goods index.
    """
    prices = economy.base_prices()
    in_mat = economy.goods_input_matrix()
    out_mat = economy.goods_output_matrix()
    levels = state.building_levels
    goods_index = economy.goods_index()
    config_keys = economy.building_index()
    key_to_i = {k: i for i, k in enumerate(config_keys)}

    if good is not None:
        if good not in goods_index:
            raise ValueError(f"Good '{good}' not found in goods index.")
        tree = upstream_tree(economy, good, state)
        selected = _collect_producers(tree)
        idxs = [key_to_i[k] for k in selected]
    else:
        idxs = [i for i in range(len(config_keys)) if levels[i] > _TOL]

    input_cost = np.zeros(len(goods_index), dtype=np.float64)
    net_supply = np.zeros(len(goods_index), dtype=np.float64)
    for i in idxs:
        level = float(levels[i])
        input_cost += in_mat[i] * prices * level
        net_supply += (out_mat[i] - in_mat[i]) * level
    total_input = float(input_cost.sum())

    marginals = _import_marginals(optimizer, len(goods_index))
    rows: list[dict[str, object]] = []
    for j, g in enumerate(goods_index):
        if input_cost[j] <= _TOL:
            continue
        rows.append(
            {
                "good": g,
                "input_cost": float(input_cost[j]),
                "cost_share": float(input_cost[j] / total_input)
                if total_input > 0
                else 0.0,
                "net_supply": float(net_supply[j]),
                "import_marginal": float(marginals[j])
                if marginals is not None
                else float("nan"),
            }
        )
    df = pd.DataFrame(rows)
    if not df.empty:
        df = df.sort_values("input_cost", ascending=False).reset_index(drop=True)
    return df


def compare_scenarios(economy: Economy, scenarios: Iterable[Scenario]) -> pd.DataFrame:
    """Run multiple scenarios and tabulate headline metrics.

    For each scenario solves the LP, then computes annual GDP, total
    employment, construction cost, GDP per capita, and GDP per construction
    cost.  Scenarios that fail to solve are reported with ``NaN`` metrics and an
    ``error`` message so a comparison is not aborted by a single infeasible
    recipe.

    Args:
        economy: The :class:`Economy` to optimise over.
        scenarios: Iterable of :class:`Scenario` objects.

    Returns:
        A ``DataFrame`` with one row per scenario and columns ``name``,
        ``terminal_good``, ``objective``, ``target_amount``, ``annual_gdp``,
        ``employment``, ``construction_cost``, ``gdp_per_capita``,
        ``gdp_per_construction`` and ``error``.
    """
    rows: list[dict[str, object]] = []
    for scenario in scenarios:
        row: dict[str, object] = {
            "name": scenario.display_name(),
            "terminal_good": scenario.terminal_good,
            "objective": scenario.objective,
            "target_amount": scenario.target_amount,
        }
        try:
            optimizer = build_optimizer(economy, scenario)
            state = optimizer.linprog()
            annual_gdp = (
                float(np.dot(state.building_levels, optimizer.gdp_vector())) * 52
            )
            employment = float(np.sum(state.pops))
            construction_cost = economy.construction_cost(state)
            row["annual_gdp"] = annual_gdp
            row["employment"] = employment
            row["construction_cost"] = construction_cost
            row["gdp_per_capita"] = (
                annual_gdp / employment if employment > 0 else float("inf")
            )
            row["gdp_per_construction"] = (
                annual_gdp / construction_cost if construction_cost > 0 else 0.0
            )
            row["error"] = ""
        except ValueError as exc:
            row["annual_gdp"] = float("nan")
            row["employment"] = float("nan")
            row["construction_cost"] = float("nan")
            row["gdp_per_capita"] = float("nan")
            row["gdp_per_construction"] = float("nan")
            row["error"] = str(exc)
        rows.append(row)
    df = pd.DataFrame(rows)
    if df.empty:
        return df
    cols = [
        "name",
        "terminal_good",
        "objective",
        "target_amount",
        "annual_gdp",
        "employment",
        "construction_cost",
        "gdp_per_capita",
        "gdp_per_construction",
        "error",
    ]
    return df[cols]
