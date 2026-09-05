# Production Optimization

This is my main purpose for creating this project.

Optimisation is split into two layers: a [`Scenario`](../api.md) (in
`vic3_analysis.optimize.scenario`) defines the problem — objective,
constraints, and throughput bonuses as data — and [`NominalOptimizer`](../api.md)
(in `vic3_analysis.optimize.nominal`) is solely the solver, wrapping
`scipy.optimize.linprog`. `NominalOptimizer.solve(scenario)` returns an
`EconomyState` containing the optimal building levels and the resulting
economy state.

To perform a production optimisation, we must first acquire the following:

+ An `Economy` instance, which wraps the production table, goods table, and pop-types table parsed from the Victoria 3 game files.

+ A `Scenario`, constructed from named fields. The `objective` accepts `"gdp"` (maximise gross GDP), `"employment"` (maximise total employment), `"automation"` (minimise employment, i.e. maximise automation) and `"construction_cost"` (minimise total construction cost). `produce` is a tuple of `(good, amount)` pairs, each of which must be produced with at least that net output per week. `import_limit=0.0` (the default) enforces autarky and `None` disables import caps. The remaining fields cover banned PMs / buildings / building groups, per-building level limits (a limit of `0` bans outright), throughput bonuses, era / construction-cost / employment caps, a minimum net-infrastructure floor, and the urban-center urbanization tie.

The scenario's translation is pure and deterministic: constraint order is fixed (inequality: import cap, construction-cost cap, employment cap, produce basket, building limits, infrastructure floor; equality: era cap, banned PMs, banned groups, urban-center tie), so throughput bonuses are reflected consistently everywhere and LP duals can be mapped back to their meaning without inspecting solver internals. `Scenario.linprog_args(economy)` returns the `c` / `A_ub` / `b_ub` / `A_eq` / `b_eq` keyword dict, so `scipy.optimize.linprog` can also be invoked directly (`opt.linprog(**scenario.linprog_args(economy))`) for solver options the wrapper does not expose.

Say you want to know what building combination can produce at least 100 units of steel with the least population:

```python
from vic3_analysis import Economy, NominalOptimizer, Scenario

economy = Economy()
scenario = Scenario(
    produce=(("steel", 100),),
    objective="automation",  # minimise employment (max automation)
    import_limit=0.0,        # autarky
)
state = NominalOptimizer(economy).solve(scenario)

import numpy as np
annual_gdp = float(np.dot(state.building_levels, scenario.gdp_vector(economy))) * 52
employment = float(np.sum(state.pops))
construction_cost = economy.construction_cost(state)
print(f"GDP: {annual_gdp}")
print(f"Employment: {employment}")
print(f"Construction Cost: {construction_cost}")
print(economy.df_buildings(state))
```

# Supply Chain Analysis

On top of the `Scenario` / `NominalOptimizer` split, the
`vic3_analysis.analysis.supply_chain` module turns the "cangshulun" experiment
pattern into a reusable toolkit for trace, optimisation, value-added
attribution, bottleneck ranking, and scenario comparison. All public symbols
are re-exported from `vic3_analysis`.

## Scenario-based optimisation

A [`Scenario`](../api.md) captures the recipe (produce basket, objective,
import policy, banned production methods / buildings, throughput bonuses,
caps) as data. `optimize_chain` solves it:

```python
from vic3_analysis import Economy, Scenario, optimize_chain

economy = Economy()
state = optimize_chain(
    economy,
    Scenario(
        produce=(("automobiles", 10e6 / 5200.0),),
        objective="automation",   # minimise employment (max automation)
        import_limit=0.0,         # autarky
        banned_pms=("pm_diesel_engines",),
        building_limits=(("building_dye_plantation", 0.0),),
        throughput_bonuses=(("building_automotive_industry", 2.45),),
    ),
)
```

`objective` accepts `"gdp"` (maximise), `"employment"` (maximise),
`"automation"` (minimise employment), and `"construction_cost"` (minimise).
For solver-level access (including the retained LP result with duals), use
`NominalOptimizer(economy).solve(scenario)` directly.

## Upstream trace

[`upstream_tree`](../api.md) returns a rooted dependency graph for a good. In
**recipe mode** (`state=None`) every configuration that can produce the good
appears with per-level flows; in **realised mode** (pass a solved
`EconomyState`) only active configurations appear, scaled by their solved
level. Victoria 3 has genuine good-level cycles (e.g. `steel` ↔ `tools`), so
the graph is memoised per good and cyclic back-edges are rendered as raw
leaves.

```python
from vic3_analysis import upstream_tree

recipe = upstream_tree(economy, "automobiles")          # all producers
realised = upstream_tree(economy, "automobiles", state, scenario)  # actual chain
```

Passing the solved *scenario* makes the realised view use its
throughput-adjusted flows, consistent with the scenario's solved GDP.

## Mermaid visualisation

`SupplyChainNode.to_mermaid()` serialises a supply-chain graph to a Mermaid
`flowchart` string that renders in GitHub, GitLab, and MkDocs. In **recipe
mode** (default) it emits an aggregated good→good dependency DAG with producer
counts and dashed edges for mutual dependencies (e.g. `steel ↔ tools`). In
**realised mode** it emits a bipartite graph with good nodes (rounded) and
producer nodes (box, labelled with building and level).

```python
from vic3_analysis import upstream_tree

recipe = upstream_tree(economy, "automobiles")
print(recipe.to_mermaid())                         # aggregated DAG
print(recipe.to_mermaid(realized=True))            # bipartite graph
```

The `examples/supply_chain_trace.py` script writes both views to
`figures/supply_chain_recipe.mmd` and `figures/supply_chain_realised.mmd`.

### Recipe: automobiles (all producers)

```mermaid
--8<-- "figures/supply_chain_recipe.mmd"
```

### Realised: automobiles (1/wk, autarky, max automation)

```mermaid
--8<-- "figures/supply_chain_realised.mmd"
```

## Value-added breakdown

[`value_added_breakdown`](../api.md) attributes GDP, employment, and
construction cost either per configuration (`by="config"`) or per good
(`by="good"`, allocated by output-value share). Pass `good=` to restrict to a
chain.

```python
from vic3_analysis import value_added_breakdown

per_config = value_added_breakdown(economy, state, good="automobiles", scenario=scenario)
per_good = value_added_breakdown(economy, state, by="good", scenario=scenario)
```

Passing the solved *scenario* values flows with its throughput-adjusted
matrices, so GDP totals match `scenario.gdp_vector(economy)`.

## Bottleneck

[`bottleneck`](../api.md) ranks input goods by cost share and reports net
supply. When passed the solved optimizer, it also reads the LP shadow prices
(marginals) of the autarky import caps — the most negative marginal flags the
input whose relaxation would most reduce the objective.

```python
from vic3_analysis import NominalOptimizer, Scenario, bottleneck

optimizer = NominalOptimizer(economy)
state = optimizer.solve(scenario)
bottlenecks = bottleneck(economy, state, good="automobiles", optimizer=optimizer)
```

The solved scenario's `import_marginals(economy, optimizer.result)` interprets
its own duals, so the ranking reflects the scenario's constraint layout.

## Scenario comparison

[`compare_scenarios`](../api.md) runs several `Scenario` objects and tabulates
annual GDP, employment, construction cost, GDP per capita, GDP per construction
cost, base price, and supply-chain characteristics (active building count, chain
depth, raw-input count, bottleneck good / cost share / marginal). The table's
headline output metrics are `annual_gdp` and `gdp_per_capita`. It also adds
one dynamic `level_<building_key>` column for every resource-limited building
found in the production table's `bg_mining`, `bg_logging`, `bg_rubber`,
`bg_fishing`, `bg_whaling`, and `bg_oil_extraction` groups. Each value is the
sum of the solved levels across all production-method configurations for that
building, using `Economy.levels_per_building()`; columns follow their first
appearance in the production table.
Infeasible or unbounded scenarios are reported with `NaN`/zero metrics and an
`error` message rather than aborting the table.

```python
from vic3_analysis import compare_scenarios

df = compare_scenarios(economy, [scenario_a, scenario_b, scenario_c])
print(df.to_string(index=False))
```

For the complete cangshulun per-product report, run
`uv run python -m examples.supply_chain_cangshulun`. The script writes
`tables/supply_chain_cangshulun.csv`: one normalised automation scenario
for each producible good plus named railway, glass, furniture, logging,
groceries, clothing, grain, and urban-centre variants. It records both
`annual_gdp` and `gdp_per_capita`, as well as absolute and employment-normalised
resource-building levels.

`Economy.producible_goods()` returns all goods that have at least one
producer configuration, useful for generating a sweep over every terminal good:

```python
from vic3_analysis import Scenario, compare_scenarios

scenarios = [
    Scenario(name=g, produce=((g, 100.0 / price_map[g]),),
             objective="construction_cost")
    for g in economy.producible_goods()
]
df = compare_scenarios(economy, scenarios)
```

The `examples/supply_chain_trace.py`, `examples/supply_chain_compare.py`, and
`examples/supply_chain_cangshulun.py` scripts demonstrate each facet
end-to-end. The comparison script preserves the historical
`tables/supply_chain_sweep.csv` export. The product-details script writes the
separate `tables/supply_chain_cangshulun.csv` export with one normalised
automation scenario per producible good and named PM variants.
