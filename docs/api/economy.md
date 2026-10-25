---
title: Economy and production API
description: Public production-table, economy-model, and economy-state APIs.
---

# Economy and production API

Used by the [economy guide](../guides/economy.md)
and all optimization showcases.

For returned columns, see the [production dictionary](../data-dictionary/production.md)
and [economy-report dictionary](../data-dictionary/economy.md).

`EconomyState` accepts realized signed `building_goods_flow` quantities shaped
as configurations × goods. Aggregate inputs/outputs and per-configuration
`building_surplus`/`building_deficit` are read-only cached properties. Direct
constructors and replacements must supply the flow matrix instead of aggregate
input/output fields.

`Economy.calculate_pop_income(state)` returns a fresh writable float64 matrix
of weekly cooperative income totals aligned to configurations × professions.
It allocates each configuration's positive surplus using employee counts times
profession wage weights, including professions with `paid_private_wage=False`.
See the [cooperative income guide](../guides/economy.md#building-flows-and-cooperative-income)
for accounting assumptions and failure behavior.

::: vic3_analysis.production_table

::: vic3_analysis.Economy

::: vic3_analysis.analysis.economy.EconomyState
