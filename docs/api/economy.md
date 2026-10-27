---
title: Economy and production API
description: Public production-table, economy-model, and economy-state APIs.
---

# Economy and production API

Used by the [economy guide](../guides/economy.md)
and all optimization showcases.

For returned columns, see the [production dictionary](../data-dictionary/production.md)
and [economy-report dictionary](../data-dictionary/economy.md).

`EconomyState(context, market, households)` composes `EconomyContext`,
`MarketState`, and `PopState`. All four are exported from `vic3_analysis`.
Flat attribute reads are preserved; constructors and replacements use the
component fields. `market.context` must be the exact same object as `context`.
Components own read-only copies of their arrays; constructing a complete state
does not copy its context or evaluate dependent results.

`EconomyContext` stores realized signed `building_goods_flow` quantities shaped
as configurations × goods, trade, workers, and workforce ratio. It derives goods
input/output totals and fixed orders. `MarketState` stores prices and derives
building surplus/deficit and GDP from those prices and the shared context.
`PopState` stores wealth, demand, and optional `pop_income` and `pop_expenses`.
Its derived `pop_balance` is `None` unless both finances exist. Nominal/market
solves leave these finances unevaluated; `df_pop()` reports balances as `NaN`.

`Economy.prepare_context(context)` returns a context with prepared baskets and
scales, computing only missing fields and returning a fully prepared context
unchanged. `goods_buy_packages` is an optional immutable `GoodsBuyPackages` object with
read-only `quantities` (wealth × goods) and ascending integer `wealth` labels;
it defaults to `None`. Construct it with `GoodsBuyPackages(wealth=..., quantities=...)`
or clear it with `goods_buy_packages=None`. `consumption_scales` is an optional
read-only configuration-by-profession array. Goods and profession axes follow
the owning economy's indexes. Existing solves leave these fields unprepared.

`Economy.evaluate_wealth(context, pop_wealth)` returns `(market, households)`
for one fixed wealth assignment. It automatically prepares missing context
baskets and scales, calculates demand and market prices, then evaluates income
and expenses at those prices. Balance is derived from the returned finances.
The market references the prepared context: fully prepared inputs retain their
identity; incomplete inputs produce a new context without modifying the original.
Compose the results with `EconomyState(market.context, market, households)`.
See [evaluating fixed wealth](../guides/economy.md#evaluating-fixed-wealth).

`Economy.iterate(context, market, households, *, rtol=1e-9, atol=1e-8)` returns
matching `(MarketState, PopState)` after one simultaneous one-tier wealth
transition. Initialize through `evaluate_wealth()` first: iteration trusts
economic consistency, requires evaluated finances and prepared consecutive
tiers, and shares the supplied context. An unchanged assignment returns the
same components. See [iterating wealth](../guides/economy.md#iterating-wealth)
for affordability thresholds and numerical comparisons.

`Economy.solve(..., method="equilibrium", initial_wealth=None,
max_iterations=1000, rtol=1e-9, atol=1e-8)` calculates endogenous household
demand and returns a complete, verified state with `equilibrium_diagnostics`.
Explicit `pop_needs` is rejected. The optional initial wealth is a full
configuration/profession integer matrix. Nominal/market modes ignore these
controls and leave diagnostics as `None`.

`EquilibriumDiagnostics` and `EquilibriumError` are exported from `vic3_analysis`.
The immutable diagnostics distinguish stationary wealth from financial
sustainability: unaffordable floor households and unfunded building losses
are flags on successful results. Errors retain `.state` and `.diagnostics`
for cycles, exhausted iterations, evaluation failures, and final-verification
failures. Setup/initial-evaluation errors remain `ValueError`. See
[solving equilibrium](../guides/economy.md#solving-equilibrium) for exception
handling and [diagnostic fields](../data-dictionary/economy.md#equilibrium-diagnostics).

`Economy.pop_income(state)` returns a fresh writable float64 matrix
of weekly cooperative income totals aligned to configurations × professions.
It allocates each configuration's positive surplus using employee counts times
profession wage weights, including professions with `paid_private_wage=False`.
It adds dependent earnings from profession `dependent_wage` values, converted
from annual to weekly amounts.
See the [cooperative income guide](../guides/economy.md#building-flows-and-cooperative-income)
for accounting assumptions and failure behavior.

`EconomyContext` and `Economy.solve()` accept keyword-only `workforce_ratio=1.0`.
This uniform worker share must be in `(0, 1]`; `dependents_per_worker` is cached
as `(1 - workforce_ratio) / workforce_ratio`. `pops` and `total_employment`
count workers; `total_population` includes dependents. `Scenario.workforce_ratio`
passes the same assumption to optimizer-created states.

`Economy.goods_buy_packages(state_or_context)` returns immutable `GoodsBuyPackages`,
reusing prepared baskets when available. Its `wealth` labels and `quantities`
matrix are read-only; goods columns follow `economy.goods_index` order.
`Economy.df_goods_buy_packages(source)` exports a fresh mutable DataFrame from
an `EconomyState`, `EconomyContext`, or `GoodsBuyPackages`, copying both quantities and
wealth labels. The index is named `wealth` and columns follow `goods_index`.
The raw `Economy.df_buy_packages` input table remains separate and unchanged.
`Economy.pop_consumption_scales(state_or_context)` returns a fresh writable
float64 matrix of dimensionless household scales:
`pops / 10_000 * consumption_mult * (1 + 0.5 * dependents_per_worker)`.
`pop_buy_orders()` and `pop_expenses()` accept keyword-only
`goods_buy_packages: GoodsBuyPackages | None = None` and `consumption_scales=None` to reuse baskets and scales
independently. Each omitted argument uses its prepared context value before
falling back to calculation. Explicit and prepared baskets share the same
selection and alignment checks; DataFrame basket arguments are rejected.
Supplied scales are authoritative, finite, nonnegative,
population-shaped, and zero for empty cells; profession multipliers are not
recomputed. Refresh them when the population assumptions change.

`Economy.pop_expenses(state)` returns a fresh writable float64 matrix
of weekly household consumption expenses aligned to configurations × professions.
It prices each wealth basket at the state's market prices and applies the
household scale. It does not change wealth, demand, or `pop_balance`.
See [household expenses](../guides/economy.md#household-expenses) for validation,
reuse conditions, and an explicit `income - expenses` example.

::: vic3_analysis.production_table

::: vic3_analysis.Economy

::: vic3_analysis.EconomyContext

::: vic3_analysis.GoodsBuyPackages

::: vic3_analysis.MarketState

::: vic3_analysis.PopState

::: vic3_analysis.EconomyState

::: vic3_analysis.EquilibriumDiagnostics

::: vic3_analysis.EquilibriumError
