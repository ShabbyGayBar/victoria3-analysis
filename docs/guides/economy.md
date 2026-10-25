---
title: Economy modeling
description: Model Victoria 3 goods flows and evaluate building levels with nominal or market prices.
---

# Economy modeling

See the [production-table dictionary](../data-dictionary/production.md) for
input coefficients and the [economy-report dictionary](../data-dictionary/economy.md)
for exported state columns, formulas, and units.

## Economy data and alignment

An `Economy` model uses production, goods, pop-types, pop-needs, and buy-package
tables, each represented by a parsed DataFrame in [parsing](parsing.md).

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
`df_goods`, `df_pop_types`, `df_pop_needs`, or `df_buy_packages` is supplied explicitly, its contents are copied
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

## Population needs

`calculate_pop_needs(state)` returns weekly goods quantities aligned to
`goods_index`. It uses the state's employed-worker counts and integer wealth,
the model's `df_buy_packages`, and the goods substitution definitions in
`df_pop_needs`. Both tables can be passed as keyword arguments when constructing
`Economy`; omitted tables are parsed from the game files.

```python
from dataclasses import replace

state = economy.solve(levels)
needs = economy.calculate_pop_needs(state)
state_with_needs = replace(state, pop_needs=needs)
# Or explicitly include these orders in a new market-price evaluation:
market_state = economy.solve(levels, method="market", pop_needs=needs)
```

`solve()` does not automatically calculate population demand or iterate wealth.
The calculation leaves the supplied state unchanged. `pop_wealth` and
`pop_wealth_init` are read-only `int64` arrays; integer-valued floating inputs
are accepted, while fractional, negative, non-finite, or overflowing wealth is
rejected. Occupied wealth levels must have a buy package. Empty cells can use
zero or other undefined integer wealth levels.

For each need, effective supply is sell orders minus half of building and
export demand, clamped to zero. Goods' shares of that supply are clipped to
their configured minimum and maximum, multiplied by their weights, and then
normalized. These limits apply before normalization, so a final purchase share
can exceed its configured maximum supply share. Minimum shares can generate
demand for absent goods; if all purchase weights are zero, the default good
receives the whole category's demand.

Wealth packages specify category values at base prices per 10,000 workers.
Values are scaled by represented employment and profession `consumption_mult`
(default `1`, with peasants normally consuming `0.05`), allocated by purchase
weights, and divided by each good's base price. Existing population demand and
market prices do not affect the calculation. Dependents, cultural modifiers,
prestige goods, local-state effects, weekly adjustment, and wealth feedback are
not modeled here.

### Standard packages by wealth

`calculate_buy_packages(state)` returns a DataFrame of weekly goods quantities
per **10,000 standard workers**. Its integer index, named `wealth`, includes
every level defined in `df_buy_packages`, sorted ascending. Columns include all
goods in `goods_index` order, with `float64` values and zeros for unconsumed
goods.

```python
packages = economy.calculate_buy_packages(state)
wealth = int(packages.index[0])
goods_at_wealth = packages.loc[wealth]
```

The packages use the state's building inputs/outputs, imports, and exports for
goods substitution. They do not depend on population counts, occupied wealth
levels, profession consumption multipliers, market prices, or existing
population demand. Even an empty population has a complete package table.
Each row's value at base prices equals its wealth tier's total category budget.
The returned DataFrame is independently mutable; modifying it does not change
the state, model tables, or later results.

To export packages for an economy with no buildings, run
`examples/buy_packages.py` from the repository root:

```bash
uv run python examples/buy_packages.py
# Equivalent module invocation:
uv run python -m examples.buy_packages
```

The example parses the local game installation directly, without requiring
previously exported parser tables. Initialize the artifact checkout first with
`git submodule update --init --recursive` if necessary. It constructs an
`EconomyState` with zero building levels, production, imports, exports, and
represented employment. Standard packages remain defined for all wealth tiers:
with zero supply, minimum shares apply, and categories with zero purchase
weights fall back to their default goods.

The UTF-8 output is `artifacts/analyses/buy_packages/default.csv`, with `wealth`
as the first column followed by goods in model order. Re-running the example
replaces this CSV, and the script prints its output path.

The method's docstring links the game definitions, the
[Needs formulas](https://vic3.paradoxwikis.com/Needs#Formulas), and the
[official developer diary](https://steamcommunity.com/games/529340/announcements/detail/2965045886379003737).
The half-non-pop-demand deduction comes from community reverse engineering
documented by the wiki; zero-clamping effective supply is a model convention.
