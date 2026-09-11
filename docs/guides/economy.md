---
title: Economy and optimization
description: Model Victoria 3 goods flows and solve constrained production scenarios.
---

# Economy and optimization

## Economy data and alignment

An `Economy` wraps three DataFrames: production configurations, goods, and pop
types. Building-level vectors align with production-table rows; goods vectors
align with goods-table rows. Use `building_index()`, `goods_index()`, and the
model's matrix methods to preserve that contract.

```python
inputs = economy.goods_input_matrix()
outputs = economy.goods_output_matrix()
employment = economy.employment_matrix()
```

## Direct solving

`Economy.solve()` evaluates a building-level vector. Nominal mode uses base
prices; market mode derives national prices from buy and sell orders.

```python
import numpy as np

levels = np.zeros(len(economy.building_index()), dtype=np.float64)
state = economy.solve(levels, method="nominal")
```

Economy of scale is level-dependent and therefore belongs only to direct
solving. Set `economy_of_scale_level_cap=20.0` to apply up to +20% throughput;
leave it at `0.0` to disable the effect. Explicit throughput multipliers and
economy-of-scale bonuses affect goods inputs and outputs, not employment.

## Scenario optimization

A frozen `Scenario` expresses the objective and constraints as data. Supported
objectives are:

| Objective | Direction | Meaning |
| --- | --- | --- |
| `gdp` | maximize | Gross GDP valued at base prices |
| `gdp_per_capita` | maximize | Market-price GDP per employed person |
| `employment` | maximize | Total employed population |
| `automation` | minimize | Employment required by the scenario |
| `construction_cost` | minimize | Construction cost required by the scenario |

```python
from vic3_analysis import NominalOptimizer, Scenario

scenario = Scenario(
    produce=(("automobiles", 100.0),),
    objective="automation",
    import_limit=0.0,
    era_cap=5,
    banned_pms=("pm_diesel_engines",),
)
state = NominalOptimizer(economy).solve(scenario)
```

Other fields cap construction cost, employment, arable land, individual
buildings, or resource availability; ban building groups; apply fixed
throughput bonuses; and enforce infrastructure or urban-center relationships.
The optimizer disables economy of scale because level-dependent flows are not
linear.

For endogenous national prices, use `MarketOptimizer`. It supports `gdp` and
`gdp_per_capita`, requires `import_limit=None`, and treats `imports`, `exports`,
and `pop_needs` as fixed market orders that affect prices rather than goods
balance constraints. Its SLSQP solve is local and requires a bounded scenario.
The model excludes shortages, MAPI and local prices, wealth feedback,
endogenous demand, and economy-of-scale bonuses.

```python
from vic3_analysis import MarketOptimizer, Scenario

scenario = Scenario(
    produce=(("automobiles", 100.0),),
    objective="gdp_per_capita",
    import_limit=None,
    exports=(("automobiles", 100.0),),
    employment_cap=1_000_000.0,
)
state = MarketOptimizer(economy).solve(scenario)
```

## State-region limits

```python
from vic3_analysis import (
    StateRegionsParser,
    state_region_arable_land_limit,
    state_region_resource_limits,
)

regions = StateRegionsParser().to_dataframe()
keys = ("STATE_KANTO", "STATE_KANSAI")
limits = state_region_resource_limits(regions, keys)
land = state_region_arable_land_limit(regions, keys)

scenario = Scenario(
    objective="gdp",
    building_limits=tuple(limits.items()),
    arable_land_cap=land,
)
```

See the [economy API](../api/economy.md), [optimization API](../api/optimization.md),
and [resource-limited optimization showcase](../showcase/resource-limited-optimization.md)
for a complete regional experiment.
