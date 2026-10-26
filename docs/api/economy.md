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
unchanged. `buy_packages` is an optional read-only wealth-by-goods array with
ascending integer labels in `buy_package_wealth`; both default to `None` and
must be supplied or cleared together. `consumption_scales` is an optional
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

`Economy.calculate_pop_income(state)` returns a fresh writable float64 matrix
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

`Economy.calculate_buy_packages(state_or_context)` returns a fresh mutable
DataFrame, copying prepared baskets when available.
`Economy.calculate_pop_consumption_scales(state_or_context)` returns a fresh writable
float64 matrix of dimensionless household scales:
`pops / 10_000 * consumption_mult * (1 + 0.5 * dependents_per_worker)`.
`calculate_pop_needs()` and `calculate_pop_expenses()` accept keyword-only
`buy_packages=None` and `consumption_scales=None` to reuse baskets and scales
independently. Each omitted argument uses its prepared context value before
falling back to calculation. Supplied scales are authoritative, finite, nonnegative,
population-shaped, and zero for empty cells; profession multipliers are not
recomputed. Refresh them when the population assumptions change.

`Economy.calculate_pop_expenses(state)` returns a fresh writable float64 matrix
of weekly household consumption expenses aligned to configurations × professions.
It prices each wealth basket at the state's market prices and applies the
household scale. It does not change wealth, demand, or `pop_balance`.
See [household expenses](../guides/economy.md#household-expenses) for validation,
reuse conditions, and an explicit `income - expenses` example.

::: vic3_analysis.production_table

::: vic3_analysis.Economy

::: vic3_analysis.EconomyContext

::: vic3_analysis.MarketState

::: vic3_analysis.PopState

::: vic3_analysis.EconomyState
