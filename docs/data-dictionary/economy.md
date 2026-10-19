---
title: Economy reports
description: Building, market, population, and Japan optimization report columns.
---

# Economy reports

These reports export a supplied `EconomyState`; they do not solve a new
scenario. Totals include the entire modeled economy. Monetary values use its
state prices, which are base prices in nominal mode and national market prices
in market mode. See [shared conventions](index.md).

## Building registry

`Economy.df_buildings(state)` returns one row per configuration with level
strictly greater than zero, sorted by `level` descending. It does not aggregate
different configurations of the same building type.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `key` | String / configuration identifier | `building + "+" + production_method` from `Economy.building_index`. | Not just a building-type key; follows production-row identity. |
| `level` | Float / building levels | Solved level for that configuration. | Fractional levels are allowed; zero/negative levels are filtered out. |
| `construction_cost` | Float / construction points | Per-level construction coefficient times `level`. | Zero-cost configurations can have positive levels. |

## Market report

`Economy.df_market(state)` returns one row per good with positive sell **or**
buy orders, sorted by sell orders descending. Goods quantities are weekly;
they include throughput effects already applied to the state. “Gross” input
and output totals are reconstructed from production-table net coefficients.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `goods` | String / identifier | Good key aligned with `Economy.goods_index`. | Includes only goods surviving the order filter. |
| `market_prices` | Float / £ per goods unit | Price in the supplied state. | Base price in nominal mode; market mode derives it from buy/sell orders. |
| `market_prices_variance` | Float / percent price change | `100 * (market_prices / base_prices - 1)`. | `20` means +20%; not statistical variance. Ordinary division at zero base price. |
| `sell_orders` | Float / goods units per week | `building_goods_output + imports`. | Zero is valid when only buy orders are positive. |
| `buy_orders` | Float / goods units per week | `building_goods_input + exports + pop_needs`. | Zero is valid when only sell orders are positive. |
| `building_goods_input` | Float / goods units per week | Sum of configuration levels times adjusted nonnegative input coefficients. | Positive consumption magnitude, unlike signed production-table goods columns. |
| `building_goods_output` | Float / goods units per week | Sum of configuration levels times adjusted nonnegative output coefficients. | Positive production magnitude. |
| `imports` | Float / goods units per week | Supplied import orders for the good. | Defaults to zero when omitted from solving. |
| `exports` | Float / goods units per week | Supplied export orders for the good. | Defaults to zero when omitted from solving. |
| `pop_needs` | Float / goods units per week | Exogenous population-demand orders supplied to solving. | Defaults to zero; not automatically generated from buy-package tables. |

## Population report

`Economy.df_pop(state)` returns one row per profession with positive employment,
sorted by employment descending and with its index reset. Let `n_ij` be workers
of profession `j` in configuration `i`, and `w_ij` their stored wealth level.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `profession` | String / identifier | Profession key aligned with `Economy.pop_index`. | Zero-employment professions are omitted. |
| `employment` | Float / workers | `sum_i(n_ij)`. | Includes the whole system, not just one terminal chain. |
| `employment_share` | Float / fraction | Profession employment divided by all modeled employment. | State returns zeros for zero total employment; such a report has no positive-employment rows. |
| `avg_wealth` | Float / wealth level | `sum_i(w_ij * n_ij) / sum_i(n_ij)`. | State returns zero for a profession without employment. Current solving uses `start_quality_of_life` from pop types. |
| `total_wealth` | Float / worker-weighted wealth levels | `sum_i(w_ij * n_ij)`. | Not a stock of money or GDP. |
| `pop_balance` | Float / stored balance total | Sum of the state's `pop_balance` over configurations for this profession. | Current nominal and market solvers initialize this array to zero; it is not a computed wage or household budget. |

## Japan optimization comparison

The current `examples/optimize_jap.py` writes `optimize_jap.csv`, one row per employment-cap
scenario, in increasing cap order. It solves a nominal autarkic era-5 economy
with selected Japanese state-region resource and arable-land limits and the
example's banned building groups. Its `employment` and other totals are
whole-system values.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `employment_cap` | Integer / workers | Scenario upper bound on total modeled employment. | Retained on both success and failure; not the realized employment. |
| `status` | String / category | `success` or `failure` for the solve. | Failure records a caught `ValueError`. |
| `annual_gdp` | Float / £ per year | `52 * state.gdp_weekly`, using base prices in this example. | NaN on failure. |
| `employment` | Float / workers | Sum of the state's employment array. | NaN on failure. |
| `construction_cost` | Float / construction points | Solved levels dotted with per-level construction coefficients. | NaN on failure. |
| `gdp_per_capita` | Float / £ per worker per year | Annual GDP divided by modeled employment. | Zero for zero employment on a successful state; NaN on failure. |
| `arable_land_consumption` | Float / arable-land units | Solved levels dotted with the model's arable-land coefficients. | NaN on failure. Recognized agricultural building groups consume one unit per level; others zero. |
| `error` | String / diagnostic text | Caught exception message. | Empty string on success; no economic metric is inferred from a failure. |

### Additional columns in the committed snapshot

The committed `artifacts/analyses/optimization/japan/employment_sweep.csv` was generated by an earlier version of
the example (the generator at commit `7e3365c` used `compare_scenarios`). It
has no `status` column: an empty `error` indicates success. Shared metrics have
the meanings above, except the earlier per-capita calculation returned
infinity when successful employment was zero. These additional columns are
still documented for readers of that snapshot; the current generator does
not emit them.

| Column or family | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `objective` | String / category | Scenario objective, `gdp` in the Japan snapshot. | Snapshot-only; retained on failure. |
| `gdp_per_construction` | Float / £ per year per construction point | Annual GDP divided by solved construction cost. | Snapshot-only; zero for nonpositive construction cost, NaN on failure. |
| `era_cap` | Integer or None / era limit | Scenario's maximum allowed technology era, 5 in this snapshot. | Snapshot-only; retained on failure. |
| `level_<building>` | Float / building levels | Sum of solved levels across configurations of a resource-limited building type; e.g. `level_building_coal_mine`. | Snapshot-only family in first-seen building order; zero if unbuilt, NaN on failure. |

The recognized groups are `bg_staple_crops`, `bg_ranching`, `bg_agriculture`,
`bg_plantations`, `bg_subsistence_agriculture`, and `bg_subsistence_ranching`.
The coefficient uses immediate `building_group` membership, not `land_usage`
or ancestor traversal; a missing group column gives all-zero coefficients.

These legacy fields were traced to the earlier comparison implementation;
their presence does not imply that the current example and stored snapshot
share the same output schema.

For the report APIs, see the
[economy API](../api/economy.md). The
[resource-limited optimization showcase](../showcase/resource-limited-optimization.md)
describes the Japan experiment.
