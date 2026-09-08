---
title: Quickstart
description: Solve and inspect a reproducible Victoria 3 production scenario from the committed data snapshots.
---

# Quickstart

This tutorial builds a small, reproducible analysis from the CSV snapshots in
the repository. It does not parse your game installation or overwrite any
generated data.

## 1. Prepare the checkout

Clone the repository and install its locked development environment:

```bash
git clone https://github.com/ShabbyGayBar/victoria3-analysis.git
cd victoria3-analysis
uv sync
uv pip install -e .
```

The example below needs `production_table.csv`, `goods.csv`, and
`pop_types.csv`, all of which are committed under `tables/`.

## 2. Load an economy

```python
import pandas as pd

from vic3_analysis import Economy

economy = Economy(
    df_production=pd.read_csv("tables/production_table.csv"),
    df_goods=pd.read_csv("tables/goods.csv"),
    df_pop_types=pd.read_csv("tables/pop_types.csv"),
)

print(f"{len(economy.building_index())} production configurations")
print(f"{len(economy.goods_index())} goods")
```

`Economy` keeps every array aligned to the production-table and goods-table row
orders. Prefer its matrix and aggregation methods over reconstructing those
mappings yourself.

## 3. Define and solve a scenario

Produce at least 100 units of steel per week under autarky while minimizing the
construction cost of the required buildings:

```python
from vic3_analysis import NominalOptimizer, Scenario

scenario = Scenario(
    name="steel quickstart",
    produce=(("steel", 100.0),),
    objective="construction_cost",
    import_limit=0.0,
)
state = NominalOptimizer(economy).solve(scenario)
```

`Scenario` owns the problem definition. `NominalOptimizer` only translates it
to a linear program and returns an `EconomyState`.

## 4. Inspect the result

```python
active_buildings = economy.df_buildings(state).query("level > 1e-9")
market = economy.df_market(state)

print(active_buildings.to_string(index=False))
print(market.loc[market["sell_orders"] > 0].to_string(index=False))
print(f"Annual GDP: {state.gdp(annual=True):,.0f}")
print(f"Employment: {state.total_population():,.0f}")
print(f"Construction cost: {economy.construction_cost(state):,.0f}")
```

The optimizer is nominal: it uses base prices and disables level-dependent
economy-of-scale behavior so the problem remains linear. To evaluate a chosen
building vector with market prices, call `Economy.solve(..., method="market")`
and provide any population-needs demand required by the experiment.

## 5. Continue from here

<div class="grid cards" markdown>

- [Parse your installed game](guides/parsing.md) to refresh the source tables.
- [Model and optimize economies](guides/economy.md) with more constraints and
  direct solving.
- [Trace the steel supply chain](guides/supply-chain.md) and compare scenarios.
- [Browse every generated result](showcase/index.md) and its runnable script.

</div>
