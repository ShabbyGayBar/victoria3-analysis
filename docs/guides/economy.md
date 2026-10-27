---
title: Economy modeling
description: Model Victoria 3 goods flows and evaluate building levels with nominal or market prices.
---

# Economy modeling

For calculation dependencies and the owner of each state value, see the
[economy dependency graphs](../design/economy-dependencies.md).

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
    The components of `EconomyState` own read-only copies of input arrays. Its realized
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

The unscaled input and output matrices are prepared together from the production
table and cached as separate read-only arrays. Scaled matrices remain writable
copies.

Snapshot helpers use the `state` argument name, including keyword calls such as
`economy.df_market(state=state)` and `economy.construction_cost(state=state)`.

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

Pass fixed weekly trade quantities with `goods_trade_flow`, a finite 1-D
array aligned to `economy.goods_index`. Positive values import goods and add
sell orders; negative values export goods and add buy orders. Omission means
zero trade. The aggregate model assumes each good trades in one direction.

```python
trade = np.zeros(len(economy.goods_index), dtype=np.float64)
trade[economy.goods_index.index("tools")] = 5.0  # Import 5 tools per week.
trade[economy.goods_index.index("coal")] = -3.0  # Export 3 coal per week.
state = economy.solve(levels, method="market", goods_trade_flow=trade)
```

`EconomyContext` stores this vector, and `state.goods_trade_flow` forwards to
it. Both context and state expose read-only derived `imports` and `exports`
quantities. When migrating existing callers, replace the old `imports=` and
`exports=` inputs with `goods_trade_flow=`; for inputs with disjoint trade
directions, this is `imports - exports`. Inputs with both directions for the
same good cannot be represented without changing the model's buy/sell orders.
Optimization scenarios use the same sign convention with named pairs.

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

### Snapshot components and preparation

All four state classes are available from `vic3_analysis`:

| Component | Stored inputs | Derived values |
| --- | --- | --- |
| `EconomyContext` (`state.context`) | Building levels, realized goods flows, trade, workers, workforce ratio, optional baskets and scales | Goods input/output totals, sell orders, non-household buy orders, population totals |
| `MarketState` (`state.market`) | Shared context reference and prices | Building surplus, deficit, and GDP |
| `PopState` (`state.households`) | Wealth, household demand, optional income and expenses | Balance, when both finances are supplied |
| `EconomyState` | References to these three components | Total buy orders, wealth statistics, per-capita reports |

Existing flat reads such as `state.pops` and `state.market_prices` forward to
their owning components. Direct construction now uses
`EconomyState(context=context, market=market, households=households)`.
The market must reference the exact same context object.

Nominal and market solves leave `goods_buy_packages`,
`consumption_scales`, `pop_income`, and `pop_expenses` as `None`. They continue
to accept externally supplied population demand without evaluating household
finances. `pop_balance` is `None` until both finances exist; `df_pop()` reports
unavailable balances as `NaN`.

Prepare the fixed consumption inputs explicitly, then share them across snapshots:

```python
from dataclasses import replace
from vic3_analysis import MarketState

context = economy.prepare_context(state.context)
state = replace(
    state,
    context=context,
    market=MarketState(context=context, market_prices=state.market_prices),
)
needs = economy.pop_buy_orders(state)
expenses = economy.pop_expenses(state)
```

The context stores `goods_buy_packages` as an immutable `GoodsBuyPackages` object containing
read-only arrays: `wealth` holds ascending positive integer row labels, and
`quantities` holds the wealth-by-goods matrix. Goods columns follow
the owning economy's `goods_index`; worker columns follow `pop_index`.
`goods_buy_packages(context)` returns `GoodsBuyPackages`, reusing the prepared
object when present. `df_goods_buy_packages(source)` exports an independent
DataFrame from a state, context, or basket object, while
`pop_consumption_scales(context)` returns an independent writable
array. Both calculators also accept complete states.

To supply custom prepared baskets, construct one object with both arrays:

```python
import numpy as np

from vic3_analysis import GoodsBuyPackages

packages = GoodsBuyPackages(
    wealth=np.array([1, 5]),
    quantities=np.zeros((2, len(economy.goods_index))),
)
context = replace(state.context, goods_buy_packages=packages)
```

`GoodsBuyPackages` owns copies of its inputs, validates their alignment, and sorts
labels and quantities together. Contexts share the immutable object.
Use `context.goods_buy_packages.wealth` and `context.goods_buy_packages.quantities` after
checking that baskets are prepared. This replaces the former separate
`buy_packages` array and `buy_package_wealth` attributes.

`prepare_context()` computes only missing fields, returning the original context
when fully prepared. Needs and expenses resolve baskets and scales independently:
explicit arguments take precedence, then prepared context values, then calculation.
No household-by-goods tensor is retained.

Refresh baskets when production, trade, or substitution assumptions change.
Refresh scales when workers, workforce ratio, or profession multipliers change.
For example, changing the workforce ratio requires clearing the old scales:

```python
context = economy.prepare_context(
    replace(state.context, workforce_ratio=0.25, consumption_scales=None)
)
state = replace(state, context=context, market=replace(state.market, context=context))
```

Set `goods_buy_packages=None` when refreshing baskets. Wealth and prices may change
while sharing the same context.
Context preparation does not evaluate wealth or implement iteration.

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

Realized flows belong to `EconomyContext`. When changing an existing state,
replace its context and rebind the market to the new context. Clear prepared
baskets because the changed flows affect substitution:

```python
from dataclasses import replace

context = replace(
    state.context,
    building_goods_flow=state.building_goods_flow * 2,
    goods_buy_packages=None,
)
changed_state = replace(state, context=context, market=replace(state.market, context=context))
```

`state.building_surplus` is each configuration's weekly goods value added at
the state's prices, **before wages**. `state.building_deficit` is the positive
magnitude of a negative surplus, representing input costs not covered by output
revenue. Both are cached, read-only arrays aligned to `building_index`.
Replacing flows or prices creates a new state with fresh caches.

`pop_income(state)` implements a simplified worker-cooperative policy:
each configuration distributes all positive surplus to its employees in
proportion to employee counts times profession `wage_weight`. Every employed
profession participates regardless of `paid_private_wage`; zero weights receive
zero cooperative income. Configurations of the same building type distribute independently.

```python
state = economy.solve(levels, method="market")
income = economy.pop_income(state)
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

`pop_buy_orders(state)` returns weekly goods quantities aligned to
`goods_index`. It uses the state's employed-worker counts and integer wealth,
the model's `df_buy_packages`, and the goods substitution definitions in
`df_pop_needs`. Both tables can be passed as keyword arguments when constructing
`Economy`; omitted tables are parsed from the game files.

```python
from dataclasses import replace

state = economy.solve(levels)
needs = economy.pop_buy_orders(state)
state_with_needs = replace(state, households=replace(state.households, pop_buy_orders=needs))
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

`goods_buy_packages(state)` returns immutable `GoodsBuyPackages` of weekly goods
quantities per **10,000 standard workers**. Its read-only `wealth` array contains
ascending positive int64 labels, and `quantities` is a read-only float64 matrix
with columns in `goods_index` order and zeros for unconsumed goods. Prepared
context baskets are authoritative and reused; otherwise every level defined in
the raw `df_buy_packages` table is calculated.

```python
packages = economy.goods_buy_packages(state)
wealth = int(packages.wealth[0])
goods_at_wealth = packages.quantities[0]
# Convert only when a table or export is needed:
report = economy.df_goods_buy_packages(packages)
```

The packages use the state's building inputs/outputs, imports, and exports for
goods substitution. They do not depend on population counts, occupied wealth
levels, profession consumption multipliers, market prices, or existing
population demand. Even an empty population has a complete set of calculated baskets.
Each row's value at base prices equals its wealth tier's total category budget.
The returned object owns read-only arrays. `df_goods_buy_packages(state)`,
`df_goods_buy_packages(context)`, or `df_goods_buy_packages(packages)` returns
an independently mutable report with int64 index named `wealth` and goods
columns in model order. Editing that report changes no baskets or model tables.

Pass the basket object to `pop_buy_orders` to reuse its goods quantities:

```python
packages = economy.goods_buy_packages(state)
needs = economy.pop_buy_orders(state, goods_buy_packages=packages)
next_state = economy.solve(levels, method="market", pop_needs=needs)
next_needs = economy.pop_buy_orders(next_state, goods_buy_packages=packages)
```

Supplied baskets stay fixed when market supply changes. Demand is calculated
directly from each occupied wealth tier's goods quantities, scaled by worker-
equivalent counts including half-rate dependent consumption, and profession
consumption multipliers per 10,000 workers. Substitution,
base-price conversion, and validation of unused state goods flows and raw
need/package tables are skipped.

`GoodsBuyPackages` construction validates unique positive integer wealth labels and
finite nonnegative quantities, and sorts rows with their labels. Quantity
columns must already follow the model's `goods_index` order; consumption
calculations check the column count and coverage of occupied tiers. Only
occupied wealth tiers need rows; empty population cells need no matching
package. Explicit baskets, prepared context baskets, and freshly calculated
baskets use the same selection path. DataFrames are not accepted as basket
arguments. The basket object and state remain unchanged.

### Reusable household consumption scales

`pop_consumption_scales(state)` returns a fresh writable float64
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
packages = economy.goods_buy_packages(state)
scales = economy.pop_consumption_scales(state)
needs = economy.pop_buy_orders(
    state, goods_buy_packages=packages, consumption_scales=scales
)
expenses = economy.pop_expenses(
    state, goods_buy_packages=packages, consumption_scales=scales
)
income = economy.pop_income(state)
balance = income - expenses
```

Supplied scales are authoritative: they must match `state.pops.shape`, contain
finite nonnegative values, and be zero wherever worker counts are zero. They
already include all population factors, which are not reapplied or checked
against the current profession multipliers or workforce ratio. The caller is
responsible for refreshing stale scales. Omitted scales reuse prepared context
scales when present, otherwise calling `pop_consumption_scales(state)`.
Every occupied wealth tier needs a
basket even if its scale is zero; empty cells need no defined wealth tier.

### Household expenses

`pop_expenses(state)` returns a fresh writable float64 matrix shaped
like `state.pops`, containing household consumption expenses in pounds per week.
It values each occupied wealth tier's goods basket at `state.market_prices`
and multiplies by its consumption scale, including profession and dependent
effects. Prices must be finite, nonnegative, and goods-aligned; zero prices are
valid. Changing prices changes expenses without changing basket quantities.

The `goods_buy_packages` argument follows the same contract as for needs. Supplied
baskets bypass unused production flows, base prices, and raw needs/package
tables. Empty households have zero expenses; an empty population may use an
empty supplied basket table. All calculated costs and expenses must be finite.

With matching baskets and scales, total expenses equal
`needs @ state.market_prices`. The methods aggregate quantities by wealth tier
and do not allocate a configuration-by-profession-by-goods tensor. They leave
the state, supplied arrays/tables, and model tables unchanged. In particular,
`balance` above is calculated explicitly; `state.pop_balance` is unchanged.
Store finances explicitly to obtain a derived balance on a new snapshot:

```python
state = replace(
    state,
    households=replace(state.households, pop_income=income, pop_expenses=expenses),
)
balance = state.pop_balance  # Read-only income minus expenses.
```

Replacing just the market or household component shares `state.context` and
its production arrays. The caller must refresh dependent results when changing
wealth or prices; constructing a snapshot does not recalculate demand or finances.
Expenses price target consumption without affordability limits, rationing,
taxes, or wealth transitions. Nominal and market modes do not automatically calculate
expenses or balances.

### Evaluating fixed wealth

`evaluate_wealth(context, pop_wealth)` evaluates one wealth assignment and returns
matching market and household components. It calls `prepare_context()` to fill
missing baskets and consumption scales, preserving any supplied prepared fields.
It then calculates household goods demand, derives market prices from industrial,
export, and household buy orders against production and import sell orders, and
evaluates cooperative income and household expenses at those same prices.

```python
initial = economy.solve(building_levels, workforce_ratio=0.25)
market, households = economy.evaluate_wealth(initial.context, initial.pop_wealth)
state = EconomyState(market.context, market, households)
balance = state.pop_balance  # Evaluated, read-only weekly income minus expenses.
```

Use `market.context` when composing the result: it is the supplied context when
already fully prepared, or a newly prepared context otherwise. Inputs and model
tables remain unchanged. Returned arrays are read-only, and supplied wealth
values are preserved as `int64`. Wealth must match configurations × professions;
every occupied tier needs a basket, including households with zero consumption
scales. Empty cells may use undefined nonnegative integer tiers.

Total household expenses equal `households.pop_buy_orders @ market.market_prices`
within floating-point precision. Existing preparation, input validation, and
income-allocation errors propagate. This evaluates target consumption without
affordability limits or wealth transitions; nominal and market solve modes
continue to leave household finances unevaluated.

### Iterating wealth

Initialize matching components, then take one simultaneous step:

```python
market, households = economy.evaluate_wealth(initial.context, initial.pop_wealth)
context = market.context
market, households = economy.iterate(context, market, households)
state = EconomyState(context, market, households)
```

`iterate()` trusts the supplied components' economic consistency. It requires
evaluated income and expenses, a market referencing the exact same context,
and prepared baskets/scales. Reevaluate after externally changing wealth,
production, or trade. Prepared wealth labels must be consecutive; occupied
wealth must be covered. Empty cells retain their original wealth labels.

Using previous prices and income, each occupied household decreases one tier
when income is below **98% of its current-tier cost**. Otherwise, it increases
one tier when income reaches **102% of its next-tier cost**. Other households
retain their tier. Decreases take precedence even if basket costs are
nonmonotonic. These constants follow `WEALTH_PROGRESS_ACCEPTABLE_DEFICIT` and
`WEALTH_PROGRESS_WANTED_BUFFER` in the local game's `common/defines/00_defines.txt`.
The steps are numerical; weekly wealth-progress timing is not simulated.

For a threshold `B`, comparisons use `t = atol + rtol * max(abs(income), abs(B))`:
decrease when `income < B - t`, advance when `income >= B - t`. Defaults are
`rtol=1e-9`, `atol=1e-8`; zero tolerances recover exact comparisons. Costs and
income are weekly totals for each configuration/profession household group.
At the minimum tier, downward movement is suppressed; at the maximum tier,
advancement is omitted. If nothing changes, `iterate()` returns the supplied
objects. Otherwise, it evaluates the new assignment once and returns matching
read-only components sharing the fixed context.

### Solving equilibrium

```python
from vic3_analysis import EquilibriumError

try:
    state = economy.solve(
        building_levels,
        method="equilibrium",
        workforce_ratio=0.25,
        max_iterations=1000,
        # initial_wealth=previous_state.pop_wealth,  # Optional full-matrix warm start.
    )
except EquilibriumError as error:
    last_state = error.state
    print(error.diagnostics.status, error.diagnostics.iterations)
    print(error.diagnostics.increasing_cells, error.diagnostics.decreasing_cells)
else:
    diagnostics = state.equilibrium_diagnostics
    print(diagnostics)
```

Equilibrium prepares fixed production, trade, baskets, consumption scales,
cooperative allocation shares, and dependent earnings once. The solver then
iterates wealth, demand, prices, income, and expenses. `initial_wealth` defaults
to profession starting tiers, or accepts a nonnegative integer matrix matching
configurations × professions. Unsupported occupied tiers are rejected rather
than clipped. Explicit `pop_needs`, including a zero vector, is rejected:
household demand is calculated endogenously.

Success requires no permitted wealth changes and a fresh final verification
through the accounting calculators. An initially stable assignment reports
zero iterations. `max_iterations` is a positive integer counting completed
transition steps; initialization and final verification do not count. Convergence
and cycles are checked at the final allowed step before exhaustion is reported.

`state.equilibrium_diagnostics.status == "converged"` describes stationary wealth.
It can coexist with `unaffordable_floor_cells` or `loss_buildings`. The former
identifies households below their lower affordability threshold at the minimum
tier. The latter identifies unfunded losses larger than
`atol + rtol * max(output_value, input_value)`, using the existing signed-flow
accounting. These are financial flags on a successful solve. No subsidies,
reserves, wage changes, or financing are introduced; dependent earnings remain
exogenous, and trade remains fixed orders.

`EquilibriumError` distinguishes `cycle`, `max_iterations`, `evaluation_failed`,
and `verification_failed`. Its immutable `.state` retains the last complete
evaluation and references the same `.diagnostics`. Diagnostics identify cells
requiring changes and financial flags; cycles additionally report `cycle_start`
and `cycle_length`. Household coordinates are `(configuration_index,
profession_index)` in economy index order; building flags are configuration
indices. Calculation failures chain their original exception as `__cause__`.
Invalid setup or initial evaluations raise `ValueError` directly. A detected
cycle or exhausted budget does not prove that no equilibrium exists.

Nominal and market modes retain their existing behavior and leave equilibrium
diagnostics as `None`; equilibrium controls are ignored in those modes.

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

The example calls `economy.df_goods_buy_packages(state)` for the DataFrame export.
The UTF-8 output is `artifacts/analyses/buy_packages/default.csv`, with `wealth`
as the first column followed by goods in model order. Re-running the example
replaces this CSV, and the script prints its output path.

The method's docstring links the game definitions, the
[Needs formulas](https://vic3.paradoxwikis.com/Needs#Formulas), and the
[official developer diary](https://steamcommunity.com/games/529340/announcements/detail/2965045886379003737).
The half-non-pop-demand deduction comes from community reverse engineering
documented by the wiki; zero-clamping effective supply is a model convention.
