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

## State flows and cooperative income

`EconomyState.building_goods_flow` is a read-only float64 matrix with rows
aligned to `building_index` and columns to `goods_index`. Values are realized
weekly signed quantities after building levels, throughput, and economy of
scale: positive for outputs and negative for inputs. It replaces the former
aggregate constructor fields. Existing aggregate input/output attribute access
is preserved through cached properties.

| Attribute / result | Shape / unit | Meaning / calculation |
| --- | --- | --- |
| `building_goods_input` | Goods / units per week | `maximum(-building_goods_flow, 0).sum(axis=0)`. |
| `building_goods_output` | Goods / units per week | `maximum(building_goods_flow, 0).sum(axis=0)`. |
| `building_surplus` | Configurations / £ per week | `building_goods_flow @ market_prices`, value added before wages; may be negative. |
| `building_deficit` | Configurations / £ per week | `maximum(-building_surplus, 0)`, unfunded input costs. |
| `calculate_pop_income(state)` | Configurations × professions / £ per week | Positive surplus allocated by `pops * wage_weight`, plus `pops * dependents_per_worker * dependent_wage / 52`; household totals, not per-worker rates. |

The four state properties are cached, owned, read-only float64 arrays. Signs
are split before aggregation to retain opposing flows between configurations;
within-row flows retain the production table's signed-net convention.

The income calculation returns a fresh writable matrix. It includes professions
regardless of `paid_private_wage`, pays zero wages on zero/negative surplus, and
does not pool configurations. Positive surplus with zero total recipient weight
raises `ValueError`. Deficits have no implicit funding source. Dependent earnings
are exogenous and do not alter building surplus or production GDP. Missing
dependent wages mean zero. Income excludes
taxes, transfers, reserves, and subsistence income; it does not update
`pop_balance` or wealth.

## Household consumption calculations

Let `s_ij = pops_ij / 10_000 * consumption_mult_j * (1 + 0.5 * dependents_per_worker)`
and `Q_wg` be standard goods baskets from `calculate_buy_packages(state)`.

| Result | Shape / unit | Meaning / calculation |
| --- | --- | --- |
| `calculate_pop_consumption_scales(state)` | Configurations × professions / dimensionless | `s_ij`, multiples of a weekly basket for 10,000 standard workers. Missing profession multipliers default to one. |
| `calculate_pop_needs(state, ...)` | Goods / units per week | `sum_ij(s_ij * Q[pop_wealth_ij, g])`. |
| `calculate_pop_expenses(state, ...)` | Configurations × professions / £ per week | `s_ij * sum_g(Q[pop_wealth_ij, g] * market_prices_g)`, household totals. |

All three return independent writable float64 arrays. Needs and expenses accept
optional `buy_packages` and `consumption_scales`, independently. Supplied scales
are authoritative and already include all population factors; they must match
the population shape, be finite and nonnegative, and be zero for empty cells.
Unused profession multipliers are not validated when scales are supplied.
Occupied cells require a basket even when their scale is zero; empty cells
have zero expenses and need no defined wealth tier.

Scales can be reused while population assumptions are fixed; baskets can be
reused while production, trade, and substitution assumptions are fixed. Both
allow wealth and market prices to change. Supplied baskets skip validation of
unused goods flows, base prices, and raw need/package definitions. Expenses use
finite nonnegative market prices, including zero. Non-finite calculated results
are errors.

Total expenses equal population demand valued at market prices when using the
same inputs. These helpers do not update the state; compute weekly balances as
`calculate_pop_income(state) - calculate_pop_expenses(state)`. Expenses exclude
taxes, rationing, affordability restrictions, and wealth transitions.

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
Let `r = state.workforce_ratio` and `d = state.dependents_per_worker = (1-r)/r`.
`total_employment` sums workers; `total_population` divides that sum by `r`.
Both direct states and `solve()` default to `r=1.0`.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `profession` | String / identifier | Profession key aligned with `Economy.pop_index`. | Zero-employment professions are omitted. |
| `employment` | Float / workers | `sum_i(n_ij)`. | Includes the whole system, not just one terminal chain. |
| `employment_share` | Float / fraction | Profession employment divided by all modeled employment. | State returns zeros for zero total employment; such a report has no positive-employment rows. |
| `dependents` | Float / people | `sum_i(n_ij) * d`. | Derived using the same economy-wide ratio for every profession. |
| `population` | Float / people | `sum_i(n_ij) / r`. | Workers plus dependents. |
| `avg_wealth` | Float / wealth level | `sum_i(w_ij * n_ij) / sum_i(n_ij)`. | State returns zero for a profession without employment. Current solving uses `start_quality_of_life` from pop types. |
| `total_wealth` | Float / population-weighted wealth levels | `sum_i(w_ij * n_ij) / r`. | Dependents share household wealth; not a stock of money or GDP. |
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
