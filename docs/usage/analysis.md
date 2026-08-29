# Production Optimization

This is my main purpose for creating this project.

The optimization is implemented in the `NominalOptimizer` class, using linear programming and other optimization functions provided by the `scipy` library.

The method responsible for performing the optimization is `linprog()`, which returns an `EconomyState` containing the optimal building levels and their corresponding economy state.

To perform a production optimization, we must first acquire the following:

+ An `Economy` instance, which wraps the production table, goods table, and pop-types table parsed from the Victoria 3 game files. The `NominalOptimizer` is constructed with an `Economy` and derives per-building vectors (GDP, employment, construction cost, goods flows) from it.

+ An objective, set via `set_objective()`. Named objectives include `"gdp"` (maximise gross GDP), `"employment"` (maximise total employment), and `"construction_cost"` (minimise total construction cost). For custom objectives, you can set `objective_vector` directly to any `*_vector()` result (e.g. `employment_vector()` to *minimise* employment).

+ Constraints, added incrementally via the fluent `constraint_*` methods. For example, if you want to ensure that your economy must be self-sufficient, i.e., does not import any goods, call `constraint_limit_import(limit=0)`. Or if you want to ensure that your economy produces at least 100 units of steel, call `constraint_produce('steel', 100)`. All constraint methods start with `constraint_`, append to the optimizer's constraint lists, and return `self` for chaining.

When calling the `linprog()` method, no arguments are needed — the objective vector and constraints are already stored on the `NominalOptimizer` instance. The `linprog()` method will automatically combine the constraints into the format required by the `scipy` library.

Say you want to know what building combination can produce at least 100 units of steel with the least population. In this case, the objective vector is `employment_vector()`, since the population is represented by the employment in the production table. The constraint is `constraint_produce('steel', 100)` and `constraint_limit_import(0)`. The code for this optimization is as follows:

```python
from vic3_analysis import Economy, NominalOptimizer

economy = Economy()
optimizer = NominalOptimizer(economy)
optimizer.objective_vector = optimizer.employment_vector()
optimizer.constraint_produce("steel", 100)
optimizer.constraint_limit_import(0)
state = optimizer.linprog()

import numpy as np
annual_gdp = float(np.dot(state.building_levels, optimizer.gdp_vector())) * 52
employment = float(np.sum(state.pops))
construction_cost = economy.construction_cost(state)
print(f"GDP: {annual_gdp}")
print(f"Employment: {employment}")
print(f"Construction Cost: {construction_cost}")
print(economy.df_buildings(state))
```

# Supply Chain Analysis

On top of the `NominalOptimizer`, the `vic3_analysis.analysis.supply_chain`
module turns the "cangshulun" experiment pattern into a reusable toolkit for
trace, optimisation, value-added attribution, bottleneck ranking, and
scenario comparison. All public symbols are re-exported from `vic3_analysis`.

## Scenario-based optimisation

A [`Scenario`](../api.md#vic3_analysis.analysis.supply_chain.Scenario)
captures the recipe (terminal good, target, objective, autarky, banned
production methods / buildings, throughput bonuses, era cap, construction-cost
and employment caps) as data. `Scenario.build_optimizer()` configures a
`NominalOptimizer` from it, and `Scenario.optimize()` solves it:

```python
from vic3_analysis import Economy, Scenario

economy = Economy()
state = Scenario(
    terminal_good="automobiles",
    target_amount=10e6 / 5200.0,
    objective="automation",   # minimise employment (max automation)
    autarky=True,
    banned_pms=("pm_diesel_engines",),
    banned_buildings=("building_dye_plantation",),
    throughput_bonuses=(("building_automotive_industry", 2.45),),
).optimize(economy)
```

`objective` accepts `"gdp"` (maximise), `"employment"` (maximise),
`"automation"` (minimise employment), and `"construction_cost"` (minimise).

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
realised = upstream_tree(economy, "automobiles", state)  # actual chain
```

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

per_config = value_added_breakdown(economy, state, good="automobiles")
per_good = value_added_breakdown(economy, state, by="good")
```

## Bottleneck

[`bottleneck`](../api.md) ranks input goods by cost share and reports net
supply. When passed the solved optimizer, it also reads the LP shadow prices
(marginals) of the autarky import caps — the most negative marginal flags the
input whose relaxation would most reduce the objective.

```python
from vic3_analysis import bottleneck

optimizer = scenario.build_optimizer(economy)
state = optimizer.linprog()
bottlenecks = bottleneck(economy, state, good="automobiles", optimizer=optimizer)
```

## Scenario comparison

[`compare_scenarios`](../api.md) runs several `Scenario` objects and tabulates
annual GDP, employment, construction cost, GDP per capita, and GDP per
construction cost. Infeasible or unbounded scenarios are reported with `NaN`
metrics and an `error` message rather than aborting the table.

```python
from vic3_analysis import compare_scenarios

df = compare_scenarios(economy, [scenario_a, scenario_b, scenario_c])
print(df.to_string(index=False))
```

The `examples/supply_chain_optimize.py`, `examples/supply_chain_trace.py`, and
`examples/supply_chain_compare.py` scripts demonstrate each facet end-to-end.
The optimisation script also generates matplotlib bar charts (building levels,
net goods, value-added by good, bottleneck) saved as PNGs to `figures/`.
