---
title: Supply-chain analysis
description: Analyze one nominal terminal-good chain or sweep all producible goods.
---

# Supply-chain analysis

`SupplyChainAnalyzer` runs one nominal optimization for one terminal good and
returns an immutable result. The scenario must contain exactly one positive
production target, and that target must match `terminal_good`.

```python
from vic3_analysis import Economy, Scenario, SupplyChainAnalyzer

economy = Economy()
scenario = Scenario(
    name="automobiles",
    produce=(("automobiles", 1.0),),
    objective="automation",
)
result = SupplyChainAnalyzer(economy, scenario, "automobiles").run()
```

The result snapshots the compiled matrices, solved state, production metadata,
and HiGHS diagnostics. Later changes to the economy or another optimizer do not
change it.

## Inspect tables and graphs

```python
headline = result.summary()
goods = result.goods()
processes = result.processes()
flows = result.flows()
workforce = result.workforce()
constraints = result.constraints()
bottlenecks = result.bottlenecks()
alternatives = result.alternatives("automobiles")
graph = result.graph()
```

Every table has a stable schema, including when it is empty. Process economics
retain exact coproduct contributions. The API does not silently allocate a
multi-output process's value to individual goods.

Two graph views are available:

- `realized` is the default and contains active configurations upstream of the
  terminal good.
- `allowed` contains technology choices not disabled by era, PM bans,
  building-group bans, or zero building limits. It is not a claim that every
  route is independently LP-feasible.

Both are cyclic bipartite NetworkX graphs: goods point to consuming production
configurations, and configurations point to output goods. Cycles remain
strongly connected components; they are never relabeled as raw-resource leaves.
`graph()` returns a defensive copy.

## Visualize the result

```python
mermaid = result.to_mermaid()
network_figure = result.plot_network(metric="value")
contribution_figure = result.plot_contributions(metric="gdp", scope="chain")
balance_figure = result.plot_goods_balance()
constraint_figure = result.plot_constraints()
```

These methods return text or Matplotlib `Figure` objects and do not write
files. Allowed-view diagrams retain active producers and otherwise show the top
three producers per good by adjusted output rate.

## Sweep all producible goods

```python
from vic3_analysis import Scenario, sweep_supply_chains

template = Scenario(
    name="era_3",
    objective="construction_cost",
    era_cap=3,
)
sweep = sweep_supply_chains(
    economy,
    template,
    target_value=100_000.0,
    keep_results=True,
)

summary = sweep.summary
failures = sweep.failures
automobiles = sweep.result_for("automobiles")
```

The sweep ignores a non-empty template `produce` basket and emits a
`UserWarning`, because each target is derived from `goods` and `target_value`.
By default, it follows `economy.producible_goods()` order and targets an equal
base-price value for each good. Infeasible or unbounded goods become failure
rows and do not abort later runs. Version 1 executes sequentially.

Open the [supply-chain showcase](../showcase/supply-chains.md) for committed
outputs and regeneration commands. The [supply-chain API](../api/supply-chain.md)
documents every public type.
