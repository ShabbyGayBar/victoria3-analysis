---
title: Supply-chain analysis
description: Analyze one nominal terminal-good chain or sweep all producible goods.
---

# Supply-chain analysis

The [supply-chain data dictionary](../data-dictionary/supply-chain.md) defines
every report column, its scope, units, formulas, and failure behavior.

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

## Why the graph uses processes

A **process** is one production-table configuration: a building type with one
complete combination of production methods. Its input/output rates describe
one building level, and its solved `level` scales those rates. A building key
can therefore appear in several process nodes with different technology,
employment, and goods flows.

This terminology follows the process/product distinction explained in
[Brightway's inventory documentation](https://docs.brightway.dev/en/latest/content/overview/inventory.html#processes-products-and-something-in-between).
Brightway is a Python life cycle assessment (LCA) framework whose inventory
model separates transformations from the products they consume and supply.
Here, production configurations are the transformations and Victoria 3 goods
are the products. Brightway also uses `activity` in its API; its
[glossary](https://docs.brightway.dev/en/latest/content/overview/glossary.html#activity)
shows that this term has broader usage than just production processes.

The naming alternatives describe different parts of our model:

| Term | Meaning here | Why it is not the graph node type |
| --- | --- | --- |
| Building | The game building type shared by multiple PM configurations. | It does not identify the complete technology choice. |
| Production method | One selected method within a configuration. | One node combines a method from every applicable PM group. |
| Production | Output or the act of producing. | It does not clearly distinguish the transformation from its output flows. |
| Producer | A process viewed as a supplier of a particular good. | The same node consumes inputs and may supply several coproducts. |
| Recipe | The per-level input/output coefficients. | The node also carries solved levels, employment, construction, and resource metadata. |

Consequently, `process:<configuration-key>` identifies a node, `building`
remains its source metadata, and `result.processes()` reports configuration
economics. The term does not mean an operating-system process.

The [supply-chain design references](../supply-chain-design.md) compare this
architecture with Brightway, PyPSA, Calliope, pymrio, and openLCA. They explain
the shared ideas behind graphs, optimization, economic accounting, and explicit
coproduct treatment, together with the limits of each comparison.

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
By default, it follows `economy.producible_goods` order and targets an equal
base-price value for each good. Infeasible or unbounded goods become failure
rows and do not abort later runs. Version 1 executes sequentially.

Open the [supply-chain showcase](../showcase/supply-chains.md) for committed
outputs and regeneration commands. The [supply-chain API](../api/supply-chain.md)
documents every public type.
