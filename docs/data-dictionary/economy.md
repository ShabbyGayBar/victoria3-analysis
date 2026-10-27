---
title: Economy reports
description: Building, market, population, and optimization report columns.
---

# Economy reports

These reports export a supplied `EconomyState`; they do not solve a new
scenario. Totals include the entire modeled economy. Monetary values use its
state prices, which are base prices in nominal mode and national market prices
in market and equilibrium modes. See [shared conventions](index.md).

## Snapshot ownership

`EconomyState` composes `context: EconomyContext`, `market: MarketState`, and
`households: PopState`. Flat reads forward to these components. Market and
complete state reference the exact same context object; replacing only market
or household results shares the fixed arrays.

| Owner | Stored quantities | Derived quantities |
| --- | --- | --- |
| `EconomyContext` | Building levels, realized flows, signed trade flows, worker counts, workforce ratio | Imports/exports, input/output totals, sell orders, industrial/export orders, population totals |
| `MarketState` | Shared context and prices | Building surplus/deficit, GDP |
| `PopState` | Wealth, demand, optional weekly income/expenses | Weekly balance (`income - expenses`), or `None` when either is absent |
| `EconomyState` | Component references, optional equilibrium diagnostics | Total buy orders, wealth summaries, per-capita reports |

`EconomyState.pop_buy_orders` forwards to the read-only, goods-aligned
`PopState.pop_buy_orders` array of weekly household demand. Total `buy_orders`
adds these population orders to `non_pop_buy_orders`.

Prepared context fields default to `None`: `goods_buy_packages` is an immutable
`GoodsBuyPackages` object whose read-only `quantities` array is wealth-by-goods float64
in `goods_index` column order, and whose read-only `wealth` array contains
ascending positive int64 wealth labels;
`consumption_scales` is read-only float64, shaped like worker counts.
`prepare_context()` fills missing fields explicitly. Nominal/market solving
leaves these and household finances unevaluated. `Economy.df_buy_packages`
continues to hold raw category budgets, distinct from prepared goods quantities.

`goods_buy_packages()` returns the same `GoodsBuyPackages` representation, reusing
prepared baskets when available. `df_goods_buy_packages(source)` exports a state,
context, or basket object as an independent DataFrame: an ascending int64 index
named `wealth`, and float64 goods-quantity columns in `goods_index` order.

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

`EconomyContext.goods_trade_flow` is a read-only float64 vector aligned to
`goods_index`, with positive imports and negative exports. Each good trades
in one direction. `EconomyState.goods_trade_flow` forwards to the same array;
`imports = maximum(goods_trade_flow, 0)` and
`exports = maximum(-goods_trade_flow, 0)` are cached, read-only context properties.

`EconomyState.building_goods_flow` is a read-only float64 matrix with rows
aligned to `building_index` and columns to `goods_index`. Values are realized
weekly signed quantities after building levels, throughput, and economy of
scale: positive for outputs and negative for inputs. It replaces the former
aggregate constructor fields. Existing aggregate input/output attribute access
is preserved through forwarding properties. The flow matrix is owned by
`EconomyContext`; aggregate inputs/outputs are cached there, while financial
aggregates are cached on `MarketState`.

| Attribute / result | Shape / unit | Meaning / calculation |
| --- | --- | --- |
| `building_goods_input` | Goods / units per week | `maximum(-building_goods_flow, 0).sum(axis=0)`. |
| `building_goods_output` | Goods / units per week | `maximum(building_goods_flow, 0).sum(axis=0)`. |
| `building_surplus` | Configurations / £ per week | `building_goods_flow @ market_prices`, value added before wages; may be negative. |
| `building_deficit` | Configurations / £ per week | `maximum(-building_surplus, 0)`, unfunded input costs. |
| `pop_income(state)` | Configurations × professions / £ per week | Positive surplus allocated by `pops * wage_weight`, plus `pops * dependents_per_worker * dependent_wage / 52`; household totals, not per-worker rates. |

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
and `Q_wg` be the `quantities` matrix from `goods_buy_packages(state)`.

| Result | Shape / unit | Meaning / calculation |
| --- | --- | --- |
| `pop_consumption_scales(state)` | Configurations × professions / dimensionless | `s_ij`, multiples of a weekly basket for 10,000 standard workers. Missing profession multipliers default to one. |
| `pop_buy_orders(state, ...)` | Goods / units per week | `sum_ij(s_ij * Q[pop_wealth_ij, g])`. |
| `pop_expenses(state, ...)` | Configurations × professions / £ per week | `s_ij * sum_g(Q[pop_wealth_ij, g] * market_prices_g)`, household totals. |

All three return independent writable float64 arrays. Needs and expenses accept
optional `goods_buy_packages: GoodsBuyPackages | None` and `consumption_scales`, independently. Each resolves
explicit arguments first, then prepared context values, then calculation.
Supplied scales
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
`pop_income(state) - pop_expenses(state)`. Expenses exclude
taxes, rationing, affordability restrictions, and wealth transitions.

## Equilibrium diagnostics

`EconomyState.equilibrium_diagnostics` is `None` for nominal/market solves and
manually composed snapshots unless explicitly supplied. Equilibrium successes
and `EquilibriumError.state` carry immutable `EquilibriumDiagnostics`.
`error.diagnostics` is the same object as on its retained state. All demand,
prices, wealth, income, expenses, and balances in that state describe the same
evaluation. Runtime calculation errors retain the preceding complete evaluation
and chain the original error.

| Field | Type / unit | Meaning |
| --- | --- | --- |
| `status` | String | `converged`, `cycle`, `max_iterations`, `evaluation_failed`, or `verification_failed`. |
| `iterations` | Integer / transition steps | Completed transitions after initialization; excludes final verification. Initially stable wealth reports zero. |
| `increasing_cells` | Tuple of integer pairs | Occupied configuration/profession coordinates requiring a permitted increase. |
| `decreasing_cells` | Tuple of integer pairs | Occupied configuration/profession coordinates requiring a permitted decrease. |
| `unaffordable_floor_cells` | Tuple of integer pairs | Occupied minimum-tier households below the lower affordability threshold; downward changes are blocked. |
| `loss_buildings` | Tuple of integers | Configuration indices with losses exceeding `atol + rtol * max(output_value, input_value)`. |
| `cycle_start` | Integer or `None` / iteration index | First appearance of the repeated wealth assignment, counting initialization as zero. |
| `cycle_length` | Integer or `None` / transition steps | Detected cycle period; only populated with `cycle_start` for cycles. |

Coordinates use `Economy.building_index` and `Economy.pop_index` in row-major
order. Loss values follow the current signed-net production-flow convention
and use weekly pounds; household affordability uses weekly group totals.
`converged` means no permitted wealth changes remain, including at boundaries.
It does not guarantee affordability or self-financing buildings: the two
financial flags do not change success status. Setup and initial-evaluation
errors raise `ValueError` without a partial result.

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
| `imports` | Float / goods units per week | Derived `maximum(goods_trade_flow, 0)` for the good. | Non-negative; zero unless the signed flow is positive. |
| `exports` | Float / goods units per week | Derived `maximum(-goods_trade_flow, 0)` for the good. | Non-negative; zero unless the signed flow is negative. |
| `pop_needs` | Float / goods units per week | Population-demand orders from `state.pop_buy_orders`. | Exogenous and zero by default in nominal/market modes; endogenous from wealth baskets in equilibrium mode. |

## Population report

`Economy.df_pop(state)` returns one row per profession with positive employment,
sorted by employment descending and with its index reset. Let `n_ij` be workers
of profession `j` in configuration `i`, and `w_ij` their stored wealth level.
Let `r = state.workforce_ratio` and `d = state.dependents_per_worker = (1-r)/r`.
`total_employment` sums workers; `total_population` divides that sum by `r`.
Both direct contexts and `solve()` default to `r=1.0`.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `profession` | String / identifier | Profession key aligned with `Economy.pop_index`. | Zero-employment professions are omitted. |
| `employment` | Float / workers | `sum_i(n_ij)`. | Includes the whole system, not just one terminal chain. |
| `employment_share` | Float / fraction | Profession employment divided by all modeled employment. | State returns zeros for zero total employment; such a report has no positive-employment rows. |
| `dependents` | Float / people | `sum_i(n_ij) * d`. | Derived using the same economy-wide ratio for every profession. |
| `population` | Float / people | `sum_i(n_ij) / r`. | Workers plus dependents. |
| `avg_wealth` | Float / wealth level | `sum_i(w_ij * n_ij) / sum_i(n_ij)`. | State returns zero for a profession without employment. Nominal/market modes use starting tiers; equilibrium mode iterates them. |
| `total_wealth` | Float / population-weighted wealth levels | `sum_i(w_ij * n_ij) / r`. | Dependents share household wealth; not a stock of money or GDP. |
| `pop_balance` | Float / £ per week | Sum of derived household income minus expenses over configurations for this profession. | `NaN` until both income and expenses are supplied on `PopState`; nominal and market solves leave them as `None`. |

`state.average_wealth_by_profession` contains profession averages, while
`state.total_wealth_by_profession` caches employment-weighted wealth sums,
excluding dependents. The report divides those sums by the workforce ratio for
its population-weighted `total_wealth` column. Because dependents share household
wealth and the workforce ratio is
uniform, `state.average_wealth` equals total wealth divided by total population
and supplies `state.wealth_distribution["mean"]`. Both return zero for an empty
population.

## Equilibrium optimization summary

`examples/optimize_equilibrium.py` writes one row to
`artifacts/analyses/optimization/equilibrium/summary.csv` for the best feasible,
verified state found by its GDP search. A budget-limited search saves that state
with an unsuccessful search status. Errors before a verified result propagate
without writing new files. The companion `buildings.csv` uses the
[building registry](#building-registry) schema above.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `objective` | String / category | Scenario objective, `gdp`. | Maximized at equilibrium prices. |
| `employment_cap` | Integer / workers | Upper bound on employed workers, 1,000,000. | Does not require full employment. |
| `workforce_ratio` | Float / fraction | Workers divided by total population, 0.4. | Shared uniformly across households. |
| `banned_building_groups` | String / identifiers | Semicolon-separated `DEFAULT_BANNED_BGS`. | Excluded configurations have zero levels. |
| `min_net_infrastructure_usage` | Float / infrastructure units | Scenario lower bound on net usage, zero. | Uses the existing net-usage convention. |
| `default_min_goods_output` | Float or empty / weekly goods units | Default minimum net domestic output. | Empty means `None`, leaving unspecified goods unconstrained. |
| `throughput_multiplier` | Float / multiplier | Common fixed multiplier, 1.0. | No throughput bonus. |
| `economy_of_scale_level_cap` | Float / building levels | Economy-of-scale cap, zero. | Level-dependent bonuses are disabled. |
| `max_evaluations` | Integer / trials | Requested hard optimizer budget. | Baseline evaluation and final verification are additional solves. |
| `initial_gdp_weekly` | Float / £ per week | GDP at the initial, uniformly scaled allowed mix after household equilibrium. | Uses the same scenario and wealth seed as search trials. |
| `initial_annual_gdp` | Float / £ per year | `52 * initial_gdp_weekly`. | Baseline for comparison with the final state. |
| `gdp_weekly` | Float / £ per week | Returned state's equilibrium GDP. | Best verified value found during search. |
| `annual_gdp` | Float / £ per year | `52 * gdp_weekly`. | Includes all modeled production. |
| `employment` | Float / workers | Returned state's total employed workers. | At most the cap within solver tolerance. |
| `population` | Float / people | `employment / workforce_ratio`. | Includes dependents. |
| `gdp_per_capita` | Float / £ per person per year | Annual GDP divided by total population. | Zero for an empty population. |
| `average_wealth` | Float / wealth tier | Population-weighted household wealth tier. | Equal to employment-weighted wealth with a uniform workforce ratio. |
| `net_infrastructure_usage` | Float / infrastructure units | Levels dotted with the model infrastructure vector. | Satisfies the configured floor within solver tolerance. |
| `search_success` | Boolean | Optimizer search success flag. | Can be false for a saved, converged household equilibrium. |
| `search_status` | Integer / code | Optimizer termination code. | Interpret together with `search_message`. |
| `search_message` | String / diagnostic text | Search termination message. | Explicitly reports budget exhaustion. |
| `trial_evaluations` | Integer / trials | Optimizer `result.nfev`. | Includes rejected physical trials; consecutive repeated points reuse a score. |
| `equilibrium_evaluations` | Integer / inner attempts | Household solves attempted by the search. | Excludes the separate baseline and final verification. |
| `failed_equilibrium_evaluations` | Integer / inner failures | Sum of trial equilibrium failures across diagnostic statuses. | Failed trials are skipped while search continues. |
| `equilibrium_status` | String / category | Household solver status for the returned state. | Always `converged` in a saved result. |
| `equilibrium_iterations` | Integer / transitions | Household transition steps in the fresh final solve. | Initialization and final accounting verification are excluded. |
| `loss_buildings_count` | Integer / configurations | Number of materially loss-making configurations. | A financial flag, without implicit financing. |
| `unaffordable_floor_cells_count` | Integer / household cells | Number of configuration/profession cells unable to afford the lowest tier. | A financial flag that does not prevent numerical convergence. |

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
