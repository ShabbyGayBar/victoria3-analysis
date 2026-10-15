---
title: Economy modeling
description: Model Victoria 3 goods flows and evaluate building levels with nominal or market prices.
---

# Economy modeling

See the [production-table dictionary](../data-dictionary/production.md) for
input coefficients and the [economy-report dictionary](../data-dictionary/economy.md)
for exported state columns, formulas, and units.

## Economy data and alignment

It takes three kinds of information to define an `Economy` model: production table, goods table, and pop types table, each of which being presented by a parsed DataFrame in [parsing](parsing.md).

You can either construct an `Economy` from the parsed tables, or let it parse them internally as below:

```python
from vic3_analysis import Economy
economy = Economy()
```

!!! warning "Immutability"

    `Economy` is a frozen dataclass that deep-copies its input tables. Its public
    DataFrames remain mutable, but editing them is unsupported: construct a new
    `Economy` for changed model data, because cached coefficients are not invalidated.
    Indexes (`building_index`, `goods_index`, `pop_index`, and `producible_goods`) are
    cached tuples. Fixed coefficients such as `base_prices`, `employment_matrix`,
    `employment_vector`, `construction_cost_vector`, `arable_land_vector`,
    `infrastructure_vector`, and `pop_wealth_init` are cached, read-only arrays.

To display names while keeping the model's key-based alignment, request a
language when parsing the internal tables:

```python
from vic3_analysis import Economy

economy = Economy(language="english")
```

Localization is added only to internally parsed DataFrames. If `df_production`,
`df_goods`, or `df_pop_types` is supplied explicitly, its contents are copied
without adding localization or changing the supplied data.

```python
import numpy as np

unscaled = economy.goods_input_matrix_unscaled
multipliers = np.full(unscaled.shape[0], 2.0)
scaled = economy.goods_input_matrix(throughput_multipliers=multipliers)
```

## Direct solving

Now that we have a model of the economy, if we know the levels of each building, we can solve for all kinds of metrics we care about, such as employment, goods flows, and GDP, all of which stored in the `EconomyState` dataclass.

```python
import numpy as np
# Assume we have one level of everything
levels = np.ones(len(economy.building_index), dtype=np.float64)
state = economy.solve(levels)
print("Class of the state:", type(state))
print("Annual GDP: ", state.gdp(annual=True))
print("Total employed population: ", state.total_population)
```

`Economy.solve()` default to `nominal` mode, which ignores the market price mechanic and uses base prices for each good.

You can also use `market` mode, which derives national prices from buy and sell orders, just like the game does (still no local prices though).

`Economy.solve()` also supports throughput bonuses via economy of scale and parameterized `throughput_multipliers`. The two are applied additively to the raw throughput of each building, which is then used to compute goods flows.

Set `economy_of_scale_level_cap=20.0` to apply up to +20% economy of scale throughput; leave it at `0.0` to disable the effect.

```python
import numpy as np

levels = np.ones(len(economy.building_index), dtype=np.float64)
state = economy.solve(
    levels,
    method="market",
    throughput_multipliers=np.full(len(economy.building_index), 1.5),
    economy_of_scale_level_cap=20.0
)
```

To choose building levels from objectives and constraints, continue with the
[optimization guide](optimization.md). See the [economy API](../api/economy.md)
for model parameters and state reports.
