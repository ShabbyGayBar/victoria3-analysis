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
    `EconomyState` also owns read-only copies of its input arrays. Its realized
    `building_goods_flow` matrix has one row per configuration and one column per
    good, in model index order. Entries are weekly quantities after levels,
    throughput, and economy-of-scale bonuses: outputs are positive and inputs
    negative.

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
print("Total employed population: ", state.total_employment)
print("Workers and dependents: ", state.total_population)
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

### Workers and dependents

`EconomyState.pops` always stores employed workers. Set the economy-wide
`workforce_ratio` to the worker share of total population; it defaults to `1.0`
to preserve worker-only accounting. The ratio must be finite and in `(0, 1]`.

```python
state = economy.solve(levels, method="market", workforce_ratio=0.25)
print(state.dependents_per_worker)  # 3.0, a cached property
print(state.total_employment)      # workers
print(state.total_population)      # four times the workers
```

Dependents are derived without another population matrix. They share each
worker group's profession and wealth, consume half as much per person, and earn
the profession's annual `dependent_wage` divided by 52 per week. For 100 workers
at a ratio of `0.25`, there are 300 dependents, 400 people, and 250 standard-worker
equivalents of consumption before profession consumption multipliers.

GDP per capita divides production GDP by workers plus dependents. Total wealth
weights wealth tiers by all people; averages, wealth distributions, Gini, and
profession shares are unchanged by a uniform ratio. `df_pop()` reports separate
`employment`, `dependents`, and `population` counts. Unemployed workers and
demographic transitions are not inferred.

## Building flows and cooperative income

`state.building_goods_input` and `state.building_goods_output` are cached,
read-only totals derived from `state.building_goods_flow`. Signs are split
before summing configurations, so a good produced by one configuration and
consumed by another contributes to both sell and buy orders. The matrix retains
the production table's signed net coefficients within each configuration; it
does not recover gross inputs offset by outputs of the same good within a row.

Direct `EconomyState` construction now requires `building_goods_flow` instead
of the former aggregate input/output arguments. When changing an existing state,
replace its flow matrix rather than the derived properties:

```python
from dataclasses import replace

changed_state = replace(state, building_goods_flow=state.building_goods_flow * 2)
```

`state.building_surplus` is each configuration's weekly goods value added at
the state's prices, **before wages**. `state.building_deficit` is the positive
magnitude of a negative surplus, representing input costs not covered by output
revenue. Both are cached, read-only arrays aligned to `building_index`.
Replacing flows or prices creates a new state with fresh caches.

`calculate_pop_income(state)` implements a simplified worker-cooperative policy:
each configuration distributes all positive surplus to its employees in
proportion to employee counts times profession `wage_weight`. Every employed
profession participates regardless of `paid_private_wage`; zero weights receive
zero cooperative income. Configurations of the same building type distribute independently.

```python
state = economy.solve(levels, method="market")
income = economy.calculate_pop_income(state)
income_by_profession = income.sum(axis=0)
deficits_by_configuration = state.building_deficit
```

The returned writable float64 matrix matches `state.pops.shape` and records
household totals in pounds per week, rather than per-worker income. It uses stored
flows and prices directly, so no throughput arguments are needed. Loss-making
configurations pay zero wages and retain an unfunded deficit. A positive surplus
without any positive recipient weight raises `ValueError` identifying the
configuration. Missing, negative, or non-finite wage weights are also errors.

Dependent earnings are added as `pops * dependents_per_worker * dependent_wage / 52`;
missing wages mean zero. Only coefficients used by represented dependents are
validated. These exogenous earnings do not reduce building surplus or increase
production GDP, and remain available when a workplace has a loss.

The calculation leaves the state and `pop_balance` unchanged. Existing solve
modes do not automatically calculate income. This policy excludes taxes,
transfers, reserves, subsistence income, and wealth iteration.

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
Values are scaled by `employment * (1 + 0.5 * dependents_per_worker)` and profession `consumption_mult`
(default `1`, with peasants normally consuming `0.05`), allocated by purchase
weights, and divided by each good's base price. Existing population demand and
market prices do not affect the calculation. Cultural modifiers,
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

Pass this table to `calculate_pop_needs` to reuse its goods baskets:

```python
packages = economy.calculate_buy_packages(state)
needs = economy.calculate_pop_needs(state, buy_packages=packages)
next_state = economy.solve(levels, method="market", pop_needs=needs)
next_needs = economy.calculate_pop_needs(next_state, buy_packages=packages)
```

Supplied baskets stay fixed when market supply changes. Demand is calculated
directly from each occupied wealth tier's goods quantities, scaled by worker-
equivalent counts including half-rate dependent consumption, and profession
consumption multipliers per 10,000 workers. Substitution,
base-price conversion, and validation of unused state goods flows and raw
need/package tables are skipped.

The table must have unique positive integer-valued wealth labels and exactly
the model's goods columns, with finite nonnegative quantities. Rows and columns
can be in any order, and the index name is ignored. Only occupied wealth tiers
need rows; empty population cells need no matching package. The supplied table
and state remain unchanged. Omitting `buy_packages` retains the calculation
using the current state's supply.

### Reusable household consumption scales

`calculate_pop_consumption_scales(state)` returns a fresh writable float64
matrix aligned to configurations × professions. Each cell is a dimensionless
multiple of a weekly basket for 10,000 standard workers:

```text
scale = workers / 10_000 * consumption_mult * (1 + 0.5 * dependents_per_worker)
```

Missing profession multipliers default to `1`. Scales are independent of wealth,
market prices, and goods flows. Reuse scales while worker counts, workforce
ratio, and profession multipliers remain unchanged. Reuse the basket table while
production, trade, and substitution assumptions remain unchanged; both can be
reused after changing household wealth or market prices.

Pass either or both precomputed inputs to needs and expense calculations:

```python
packages = economy.calculate_buy_packages(state)
scales = economy.calculate_pop_consumption_scales(state)
needs = economy.calculate_pop_needs(
    state, buy_packages=packages, consumption_scales=scales
)
expenses = economy.calculate_pop_expenses(
    state, buy_packages=packages, consumption_scales=scales
)
income = economy.calculate_pop_income(state)
balance = income - expenses
```

Supplied scales are authoritative: they must match `state.pops.shape`, contain
finite nonnegative values, and be zero wherever worker counts are zero. They
already include all population factors, which are not reapplied or checked
against the current profession multipliers or workforce ratio. The caller is
responsible for refreshing stale scales. Omitted scales are calculated using
`calculate_pop_consumption_scales(state)`. Every occupied wealth tier needs a
basket even if its scale is zero; empty cells need no defined wealth tier.

### Household expenses

`calculate_pop_expenses(state)` returns a fresh writable float64 matrix shaped
like `state.pops`, containing household consumption expenses in pounds per week.
It values each occupied wealth tier's goods basket at `state.market_prices`
and multiplies by its consumption scale, including profession and dependent
effects. Prices must be finite, nonnegative, and goods-aligned; zero prices are
valid. Changing prices changes expenses without changing basket quantities.

The `buy_packages` argument follows the same contract as for needs. Supplied
baskets bypass unused production flows, base prices, and raw needs/package
tables. Empty households have zero expenses; an empty population may use an
empty supplied basket table. All calculated costs and expenses must be finite.

With matching baskets and scales, total expenses equal
`needs @ state.market_prices`. The methods aggregate quantities by wealth tier
and do not allocate a configuration-by-profession-by-goods tensor. They leave
the state, supplied arrays/tables, and model tables unchanged. In particular,
`balance` above is calculated explicitly; `state.pop_balance` is unchanged.
Expenses price target consumption without affordability limits, rationing,
taxes, or wealth transitions. Existing solve modes do not automatically calculate
expenses or balances.

### Exporting standard packages

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
