"""
Supply-chain analysis for the nominal Victoria 3 economy.

Builds on :class:`~vic3_analysis.analysis.economy.Economy` and
:class:`~vic3_analysis.optimize.nominal.NominalOptimizer` to provide:

* :class:`Scenario` - a cangshulun-style optimisation recipe expressed as data,
  with :meth:`Scenario.build_optimizer` / :meth:`Scenario.optimize` methods.
* :func:`upstream_tree` - the structured upstream dependency tree of a good
  (recipe or realised view).
* :meth:`SupplyChainNode.to_mermaid` - serialise a supply-chain graph to a
  Mermaid flowchart string (recipe or realised view) for rendering in
  GitHub/MkDocs.
* :func:`value_added_breakdown` - per-config or per-good attribution of GDP,
  employment, and construction cost (chain-scoped or whole-economy).
* :func:`bottleneck` - rank input goods by cost share and, when available,
  report LP shadow prices for the import caps.
* :func:`compare_scenarios` - run multiple scenarios and tabulate metrics.
"""

from __future__ import annotations

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

    def build_optimizer(self, economy: Economy) -> NominalOptimizer:
        """Configure a :class:`NominalOptimizer` from this scenario.

        Applies throughput bonuses (before setting the objective so the GDP
        vector reflects them), then the objective via
        :meth:`NominalOptimizer.set_objective` (which accepts ``"automation"``
        to minimise employment), then the constraints in a fixed order: autarky
        (first, so its import-cap marginals lead the inequality block), era cap,
        construction-cost cap, employment cap, banned PMs, banned buildings, and
        finally the terminal-good production constraint.  Does not call
        :meth:`NominalOptimizer.linprog`; call it (or :meth:`optimize`) to
        solve.

        Args:
            economy: The :class:`Economy` to optimise over.

        Returns:
            A configured :class:`NominalOptimizer` ready for :meth:`linprog`.

        Raises:
            ValueError: If the scenario objective is unknown or
                *terminal_good* is not present in the goods index.
        """
        optimizer = NominalOptimizer(economy, objective="gdp")
        for building_key, multiplier in self.throughput_bonuses:
            optimizer.add_throughput_bonus(building_key, multiplier)
        optimizer.set_objective(self.objective)
        if self.autarky:
            optimizer.constraint_limit_import(0.0)
        if self.era_cap is not None:
            optimizer.constraint_limit_era(self.era_cap)
        if self.construction_cost_cap is not None:
            optimizer.constraint_limit_construction_cost(self.construction_cost_cap)
        if self.employment_cap is not None:
            optimizer.constraint_limit_employment(self.employment_cap)
        if self.banned_pms:
            optimizer.constraint_ban_pm(list(self.banned_pms))
        if self.banned_buildings:
            optimizer.constraint_ban_building(list(self.banned_buildings))
        optimizer.constraint_produce(self.terminal_good, self.target_amount)
        return optimizer

    def optimize(self, economy: Economy) -> EconomyState:
        """Solve this scenario and return the resulting :class:`EconomyState`.

        Equivalent to ``self.build_optimizer(economy).linprog()``.

        Args:
            economy: The :class:`Economy` to optimise over.

        Returns:
            The optimal :class:`EconomyState`.
        """
        return self.build_optimizer(economy).linprog()


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

    Provides traversal, analysis, and visualisation methods that operate on
    the memoised DAG rooted at this node.

    Attributes:
        good: The good key this node describes.
        producers: Producer configurations that output *good* (empty for raw
            resources).
        is_raw: ``True`` when *good* has no producers (a raw-resource leaf).
    """

    good: str
    producers: tuple[ProducerNode, ...]
    is_raw: bool

    def iter_producers(self) -> Iterator[ProducerNode]:
        """Yield every :class:`ProducerNode` reachable from this node, depth-first.

        Each :class:`SupplyChainNode` is visited once (tracked by identity), so
        traversal is linear in the number of distinct good-nodes rather than
        exponential in the chain depth.  Victoria 3 has genuine good-level
        cycles (e.g. ``steel`` <-> ``tools``), so a visited guard is required
        to avoid re-traversing shared or cyclic intermediates.  Callers
        aggregating metrics should still de-duplicate by
        :attr:`ProducerNode.config` if a configuration appears under several
        goods.

        Yields:
            Each :class:`ProducerNode` reachable from this node.
        """
        visited: set[int] = set()
        stack: list[SupplyChainNode] = [self]
        while stack:
            current = stack.pop()
            if id(current) in visited:
                continue
            visited.add(id(current))
            for producer in current.producers:
                yield producer
                for child in reversed(producer.upstream):
                    stack.append(child)

    def collect_producers(self) -> dict[str, ProducerNode]:
        """Return unique producer configs reachable from this node, keyed by config.

        Returns:
            A dict mapping each distinct ``"building+production_method"``
            configuration key to its :class:`ProducerNode`.
        """
        result: dict[str, ProducerNode] = {}
        for producer in self.iter_producers():
            if producer.config not in result:
                result[producer.config] = producer
        return result

    def collect_good_nodes(self) -> dict[str, SupplyChainNode]:
        """Return all unique good-nodes in the DAG, preferring non-raw expansions.

        Cycle-broken raw leaves share the same good key as the fully-expanded
        cached node; this method keeps the non-raw version so producers are
        not lost.  Visits each node object once (tracked by identity) to avoid
        exponential re-traversal of shared DAG subtrees.

        Returns:
            A dict mapping each good key to its :class:`SupplyChainNode`.
        """
        result: dict[str, SupplyChainNode] = {}
        visited: set[int] = set()
        stack: list[SupplyChainNode] = [self]
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

    def chain_depth(self) -> int:
        """Return the maximum depth of the supply chain (0 for raw leaves).

        Computed as the longest path from this node to any raw-resource leaf,
        memoised by node identity to handle the shared DAG efficiently.

        Returns:
            The maximum number of production stages between this good and its
            deepest raw input.
        """
        memo: dict[int, int] = {}

        def _depth(node: SupplyChainNode) -> int:
            if id(node) in memo:
                return memo[id(node)]
            if node.is_raw or not node.producers:
                memo[id(node)] = 0
                return 0
            result = 1 + max(
                (_depth(child) for p in node.producers for child in p.upstream),
                default=0,
            )
            memo[id(node)] = result
            return result

        return _depth(self)

    def count_raw_inputs(self) -> int:
        """Count distinct raw-resource leaves in the supply chain.

        Returns:
            The number of unique goods that appear as raw-resource leaves
            (goods with no producer configurations) reachable from this node.
        """
        raw_goods: set[str] = set()
        visited: set[int] = set()
        stack: list[SupplyChainNode] = [self]
        while stack:
            current = stack.pop()
            if id(current) in visited:
                continue
            visited.add(id(current))
            if current.is_raw:
                raw_goods.add(current.good)
            for producer in current.producers:
                for child in producer.upstream:
                    stack.append(child)
        return len(raw_goods)

    def to_mermaid(
        self,
        *,
        realized: bool = False,
        direction: str = "LR",
        title: str | None = None,
    ) -> str:
        """Serialise this supply-chain graph to a Mermaid flowchart string.

        Two rendering modes:

        * **Recipe** (``realized=False``, default): aggregated good→good
          dependency DAG.  Producer configurations are collapsed so each edge
          represents "to produce *B*, input *A* is required".  The node label
          includes the producer count (e.g. ``steel (5)``).  Mutual
          dependencies (e.g. ``steel ↔ tools``) are rendered as dashed edges.
        * **Realised** (``realized=True``): full bipartite graph with good
          nodes (rounded) and producer nodes (box, labelled
          ``building | lvl=…``), showing ``input → producer → output`` for
          every active configuration.

        The returned string is a complete Mermaid ``flowchart`` block that
        renders in GitHub, GitLab, and MkDocs (with ``pymdownx.superfences``
        Mermaid support).

        Args:
            realized: If ``True``, render the realised bipartite graph; if
                ``False`` (default), render the aggregated recipe DAG.
            direction: Mermaid flowchart direction (``"LR"``, ``"TD"``,
                ``"RL"``, ``"BT"``).  Defaults to ``"LR"`` (left-to-right).
            title: Optional comment line prepended to the diagram.

        Returns:
            A Mermaid flowchart string.
        """
        good_nodes = self.collect_good_nodes()

        lines: list[str] = [f"flowchart {direction}"]
        if title:
            lines.append(f"    %% {title}")

        if realized:
            producers = self.collect_producers()
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


def _mermaid_id(prefix: str, key: str) -> str:
    """Sanitise *key* into a Mermaid-safe node ID with *prefix*."""
    return prefix + "".join(c if c.isalnum() else "_" for c in key)


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
        selected = tree.collect_producers()
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
        selected = tree.collect_producers()
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

    marginals = optimizer.import_marginals() if optimizer is not None else None
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
    """Run multiple scenarios and tabulate headline and chain metrics.

    For each scenario solves the LP, then computes annual GDP, total
    employment, construction cost, GDP per capita, GDP per construction cost,
    base price, and supply-chain characteristics (active building count, chain
    depth, raw-input count, bottleneck good / cost share / marginal).
    Scenarios that fail to solve are reported with ``NaN``/zero metrics and an
    ``error`` message so a comparison is not aborted by a single infeasible
    recipe.

    Args:
        economy: The :class:`Economy` to optimise over.
        scenarios: Iterable of :class:`Scenario` objects.

    Returns:
        A ``DataFrame`` with one row per scenario and columns ``name``,
        ``terminal_good``, ``objective``, ``target_amount``, ``base_price``,
        ``annual_gdp``, ``employment``, ``construction_cost``,
        ``gdp_per_capita``, ``gdp_per_construction``, ``n_active_buildings``,
        ``chain_depth``, ``n_raw_inputs``, ``bottleneck_good``,
        ``bottleneck_cost_share``, ``bottleneck_marginal``, and ``error``.
    """
    goods_index = economy.goods_index()
    prices = economy.base_prices()
    price_map = dict(zip(goods_index, prices))

    rows: list[dict[str, object]] = []
    for scenario in scenarios:
        good = scenario.terminal_good
        row: dict[str, object] = {
            "name": scenario.display_name(),
            "terminal_good": good,
            "objective": scenario.objective,
            "target_amount": scenario.target_amount,
            "base_price": price_map.get(good, float("nan")),
        }
        try:
            optimizer = scenario.build_optimizer(economy)
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

            tree = upstream_tree(economy, good, state)
            row["n_active_buildings"] = len(tree.collect_producers())
            row["chain_depth"] = tree.chain_depth()
            row["n_raw_inputs"] = tree.count_raw_inputs()

            bn = bottleneck(economy, state, good=good, optimizer=optimizer)
            if not bn.empty:
                row["bottleneck_good"] = bn.iloc[0]["good"]
                row["bottleneck_cost_share"] = bn.iloc[0]["cost_share"]
                row["bottleneck_marginal"] = bn.iloc[0]["import_marginal"]
            else:
                row["bottleneck_good"] = ""
                row["bottleneck_cost_share"] = 0.0
                row["bottleneck_marginal"] = float("nan")

            row["error"] = ""
        except ValueError as exc:
            row["annual_gdp"] = float("nan")
            row["employment"] = float("nan")
            row["construction_cost"] = float("nan")
            row["gdp_per_capita"] = float("nan")
            row["gdp_per_construction"] = float("nan")
            row["n_active_buildings"] = 0
            row["chain_depth"] = 0
            row["n_raw_inputs"] = 0
            row["bottleneck_good"] = ""
            row["bottleneck_cost_share"] = 0.0
            row["bottleneck_marginal"] = float("nan")
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
        "base_price",
        "annual_gdp",
        "employment",
        "construction_cost",
        "gdp_per_capita",
        "gdp_per_construction",
        "n_active_buildings",
        "chain_depth",
        "n_raw_inputs",
        "bottleneck_good",
        "bottleneck_cost_share",
        "bottleneck_marginal",
        "error",
    ]
    return df[cols]  # pyright: ignore[reportReturnType]
