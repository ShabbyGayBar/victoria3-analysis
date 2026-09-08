---
title: Supply-chain analysis
description: Trace Victoria 3 supply chains, compare scenarios, attribute value, and identify bottlenecks.
---

# Supply-chain analysis

The supply-chain helpers build on `Economy`, `Scenario`, and
`NominalOptimizer`. All are importable directly from `vic3_analysis`.

## Trace upstream inputs

`upstream_tree()` has two modes:

- **Recipe mode** has no state and shows every configuration able to produce a
  good.
- **Realized mode** receives a solved state and shows only active
  configurations, scaled by their solved levels.

```python
from vic3_analysis import Scenario, optimize_chain, upstream_tree

scenario = Scenario(produce=(("automobiles", 1.0),), objective="automation")
state = optimize_chain(economy, scenario)

recipe = upstream_tree(economy, "automobiles")
realized = upstream_tree(economy, "automobiles", state, scenario)
print(recipe.to_mermaid())
print(realized.to_mermaid(realized=True))
```

Pass the scenario with a realized state so fixed throughput bonuses are applied
consistently. Cyclic good dependencies are represented as back-edges rather
than expanded forever.

## Attribute value and inspect bottlenecks

```python
from vic3_analysis import NominalOptimizer, bottleneck, value_added_breakdown

optimizer = NominalOptimizer(economy)
state = optimizer.solve(scenario)

by_good = value_added_breakdown(
    economy, state, good="automobiles", by="good", scenario=scenario
)
constraints = bottleneck(
    economy, state, good="automobiles", optimizer=optimizer
)
```

Value-added results include GDP, employment, and construction cost.
`bottleneck()` ranks input cost shares and, when given the solved optimizer,
includes import-cap shadow prices.

## Compare scenarios

```python
from vic3_analysis import compare_scenarios

comparison = compare_scenarios(economy, [scenario_a, scenario_b, scenario_c])
```

The result contains annual GDP, employment, construction cost, GDP per capita,
chain characteristics, bottleneck metrics, and aggregated resource-building
levels. Infeasible or unbounded scenarios become rows with an `error` message
instead of aborting the sweep.

Open the [supply-chain showcase](../showcase/supply-chains.md) for both Mermaid
graphs, full comparison tables, regeneration commands, and source scripts. The
[supply-chain API](../api/supply-chain.md) documents every argument and return
type.
