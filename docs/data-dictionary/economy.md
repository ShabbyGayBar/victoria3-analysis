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
| `EconomyContext` | Building levels, realized flows, gross imports and exports, worker counts, workforce ratio | Net trade, input/output totals, sell orders, industrial/export orders, population totals |
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
different configurations of the same building type. The returned DataFrame is
independent and mutable; editing it does not change the economy or state.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `building` | String / building key | Building key from the aligned production-table row. | Replaces the building portion of the former combined `key` column. |
| `production_method` | String / PM combination | Complete production-method combination from the aligned production-table row. | Multiple PM keys remain joined by `+`; configurations are not aggregated. |
| `level` | Float / building levels | Solved level for that configuration. | Fractional levels are allowed; zero/negative levels are filtered out. |
| `construction_cost` | Float / construction points | Per-level construction coefficient times `level`. | Zero-cost configurations can have positive levels. |
| `building_surplus` | Float / £ per week | `state.building_surplus`: realized goods value added before wages at state prices. | Negative values are retained. |
| `profit_per_capita` | Float / £ per worker per week | `building_surplus / employment`. | Excludes dependents regardless of `workforce_ratio`; NaN for zero employment. |
| `employment` | Float / workers | Row sum of `state.pops`. | Realized total across all professions. |
| `goods_<good>` | Float / units per week | Aligned column of `state.building_goods_flow`. | Positive outputs, negative inputs; already includes levels and throughput. |
| `employment_<profession>` | Float / workers | Aligned column of `state.pops`. | Already includes building levels; excludes dependents. |

Columns follow the order above, with all `goods_<good>` columns in
`Economy.goods_index` order, then all `employment_<profession>` columns in
`Economy.pop_index` order. Entirely zero columns are retained, including when
the report has no rows. Building and PM columns use game keys rather than
localized names; the former combined `key` column is removed.

## Historical building registry

The committed `artifacts/analyses/optimization/equilibrium/buildings.csv`
uses the earlier three-column schema: `key`, `level`, and `construction_cost`.
Level and construction cost retain the meanings above. New exports use the
expanded [building registry](#building-registry) schema.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `key` | String / configuration identifier | `building + "+" + production_method` from `Economy.building_index`. | Historical snapshot only; current reports provide separate building and PM columns. |

## State flows and cooperative income

`EconomyContext.goods_import` and `goods_export` are read-only float64 vectors
aligned to `goods_index`, holding non-negative weekly gross trade quantities.
A good may have both import and export orders. `EconomyState` forwards both
arrays; `imports` and `exports` alias the respective arrays on context and state.
The cached read-only `goods_trade_flow` vector is `goods_import - goods_export`.
Market orders use the gross quantities independently.

`EconomyState.building_goods_flow` is a read-only float64 matrix with rows
aligned to `building_index` and columns to `goods_index`. Values are realized
weekly signed quantities after building levels, throughput, and economy of
scale: positive for outputs and negative for inputs. Aggregate input/output
attributes are derived from this matrix. The flow matrix is owned by
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
| `imports` | Float / goods units per week | The good's `state.goods_import` quantity. | Non-negative; may coexist with exports. |
| `exports` | Float / goods units per week | The good's `state.goods_export` quantity. | Non-negative; may coexist with imports. |
| `pop_needs` | Float / goods units per week | Population-demand orders from `state.pop_buy_orders`. | Zero in nominal/market solves; calculated from wealth baskets by household evaluation and equilibrium solving. |

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

`examples/optimize_equilibrium.py` writes one row per completed local search to
`artifacts/analyses/optimization/equilibrium/summary.csv`, including the worse
attempt that ends iteration. The current objective is average wealth. A resumed
invocation includes iteration zero for the re-evaluated saved solution, with
empty search diagnostics. `is_best` identifies the earliest highest-objective
state exported in the solution files. Each local search gets a fresh trial
budget; equal objectives continue until a strict decrease or the optional
iteration cap. A budget-limited search may return a verified state with an
unsuccessful search status. Validation and equilibrium errors propagate without
writing new files. The companion `buildings.csv` uses the
[building registry](#building-registry) schema above.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `objective` | String / category | Scenario objective, currently `average_wealth`. | Older snapshots may use `gdp`; GDP remains a reported metric. |
| `employment_cap` | Integer / workers | Upper bound on employed workers, 1,000,000. | Does not require full employment. |
| `workforce_ratio` | Float / fraction | Workers divided by total population, 0.4. | Shared uniformly across households. |
| `banned_building_groups` | String / identifiers | Semicolon-separated `DEFAULT_BANNED_BGS`. | Excluded configurations have zero levels. |
| `min_net_infrastructure` | Float or empty / infrastructure units | Scenario minimum infrastructure generation minus consumption. | Empty in both equilibrium examples: infrastructure is unconstrained. If configured elsewhere, zero prevents deficits; positive values require surplus; negative values allow a bounded deficit. |
| `min_net_infrastructure_usage` | Float / infrastructure units | Historical minimum consumption minus generation. | Present only in older snapshots. Replaced by `min_net_infrastructure`, which uses the opposite sign convention; the old name is no longer a scenario parameter. |
| `min_goods_balance` | Float or empty / weekly goods units | Minimum building output + imports − building inputs − exports, for every good. | Excludes household consumption; empty means `None`, disabling the floor. |
| `throughput_multiplier` | Float / multiplier | Common fixed multiplier, 1.0. | No throughput bonus. |
| `economy_of_scale_level_cap` | Float / building levels | Economy-of-scale cap, zero. | Level-dependent bonuses are disabled. |
| `configuration_count` | Integer / configurations | Number of configurations in the selected production basis. | Includes configurations with zero returned levels. |
| `construction_cost` | Float / construction points | Model construction cost at this row's returned levels. | Uses the current production coefficients. |
| `arable_land_consumption` | Float / land units | Model arable-land consumption at this row's returned levels. | No arable-land cap is added by this example. |
| `max_evaluations` | Integer / trials | Requested hard budget for each local search. | Separate starting-point/baseline evaluations and final verification are additional solves. |
| `initial_gdp_weekly` | Float / £ per week | GDP at this search's initial mix after household equilibrium. | Uses the same scenario and wealth seed as search trials; baseline rows use their own state. |
| `initial_annual_gdp` | Float / £ per year | `52 * initial_gdp_weekly`. | Baseline for comparison with the final state. |
| `gdp_weekly` | Float / £ per week | This row's returned equilibrium GDP. | Selection uses the scenario objective, which may differ from GDP. |
| `annual_gdp` | Float / £ per year | `52 * gdp_weekly`. | Includes all modeled production. |
| `employment` | Float / workers | Returned state's total employed workers. | At most the cap within solver tolerance. |
| `population` | Float / people | `employment / workforce_ratio`. | Includes dependents. |
| `gdp_per_capita` | Float / £ per person per year | Annual GDP divided by total population. | Zero for an empty population. |
| `average_wealth` | Float / wealth tier | Population-weighted household wealth tier. | Equal to employment-weighted wealth with a uniform workforce ratio. |
| `net_infrastructure_usage` | Float / infrastructure units | Consumption minus generation: levels dotted with the model infrastructure vector. | Diagnostic in both equilibrium examples; positive values are permitted. When a minimum is configured elsewhere, at most `-min_net_infrastructure` within solver tolerance. |
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
| `iteration` | Integer / searches | One-based local-search number. | Zero identifies the re-evaluated saved baseline on resume. |
| `initialization` | String / category | `equal_configurations`, `saved_solution`, or `previous_iteration`. | The fresh initial mix scales equal allowed configuration levels to the employment cap without balancing infrastructure. |
| `initial_average_wealth` | Float / wealth tier | Average wealth at this search's starting levels. | Baseline rows use their own state. |
| `loss_reduction` | Float / fraction | Fraction applied to loss-making configurations before this search. | Defaults to 0.5; zero for a fresh first search or baseline row. |
| `reduced_configuration_count` | Integer / configurations | Number of levels actually reduced before this search. | No employment rescaling is applied. |
| `objective_value` | Float / objective units | Returned objective in the optimizer's units, currently average wealth. | GDP-based objectives, if configured, use weekly units. |
| `objective_change` | Float / objective units | Objective minus the preceding search's value, or saved baseline for a first resumed search. | Empty without a predecessor; a strict negative value ends iteration. |
| `gdp_weekly_change` | Float / £ per week | GDP minus the preceding search's GDP, or saved baseline on first resume. | Diagnostic only when maximizing wealth; empty without a predecessor. |
| `started_at_utc` | String / ISO timestamp | UTC start time for this search. | Baseline rows record invocation setup start. |
| `elapsed_seconds` | Float / seconds | Search duration including starting-point evaluation. | Baseline rows cover setup through saved-state evaluation and adjustment. |
| `is_best` | Boolean | True only for the earliest highest-objective row. | All solution reports use that row's state. |
| `completed_iterations` | Integer / searches | Total completed local searches in the invocation. | Excludes the saved baseline; repeated on all rows. |
| `total_trial_evaluations` | Integer / trials | Sum of local-search trial counts. | Excludes separate baseline/starting evaluations and final verification; repeated on all rows. |
| `total_elapsed_seconds` | Float / seconds | Invocation elapsed time through summary preparation. | Excludes CSV writes; repeated on all rows. |
| `best_iteration` | Integer / searches | Selected best row's iteration number. | Zero when the saved baseline wins; repeated on all rows. |
| `max_iterations` | Integer or empty / searches | Optional cap on completed local searches. | Empty means unlimited. |
| `stop_reason` | String / category | `objective_worsened` or `max_iterations`. | A strict decrease takes precedence if both conditions apply. |

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

## Supply-chain equilibrium exports

The separate `examples/optimize_supply_chain_equilibrium.py` example exports:

Its input recipes come from `era_5_automation/building_levels.csv`, exported by
the supply-chain comparison example. Rows are aligned to the full production
table before units unused by all selected recipes are removed. Each retained
coefficient is used without normalization. The example trusts the saved input
and selects its hard-coded `ALLOWED_CHAIN_GOODS` without reading the adjacent
`summary.csv`. Target metadata assumes £100,000 per recipe and derives target
quantities from goods base prices. Chain metadata follows the optimizer's
column order.

| File / column | Meaning |
| --- | --- |
| `chain_matrix.csv`: `config` | Building plus production-method key; rows follow the selected production table. |
| `chain_matrix.csv`: terminal-good columns | Building-level coefficients for one saved chain recipe. Columns follow the example's `ALLOWED_CHAIN_GOODS` order. |
| `chains.csv`: `good` | Terminal good identifying a matrix column. |
| `chains.csv`: `target_quantity` | Weekly terminal export orders used to generate one recipe. Imports and coproducts affect the required domestic output. |
| `chains.csv`: `target_base_value` | Terminal target quantity times base price; £100,000 per saved recipe. |
| `chains.csv`: `initial_level` | Starting multiplier of the saved recipe for the invocation, after any resume reduction. |
| `chains.csv`: `level` | Best verified chain multiplier across local searches and the eligible saved baseline. |
| `chains.csv`: `previous_level` | Saved chain multiplier before reducing losses; present on resumed runs. |
| `chains.csv`: `previous_terminal_surplus` | Recipe-attributed weekly operating surplus of terminal-good producers at the re-evaluated saved solution, including coproduct revenue; present on resumed runs. |
| `summary.csv`: `recipe_configuration` | Source collection, `era_5_automation`. |
| `summary.csv`: `chain_count` | Number of chain decision variables. |
| `summary.csv`: `configuration_count` | Number of building-configuration rows in the basis. |
| `summary.csv`: `iteration` | One-based local-search number; zero identifies the re-evaluated saved baseline on resumed invocations. |
| `summary.csv`: `initial_average_wealth`, `initial_gdp_weekly`, `initial_annual_gdp` | Metrics at that local search's starting vector; baseline rows use their own state. |
| `summary.csv`: `initialization` | `equal_chains` for a fresh first search, `saved_solution` for a resume baseline/first search, or `previous_iteration` for subsequent searches. |
| `summary.csv`: `loss_reduction` | Fraction applied to loss-making chains before this search. Equal-chain initialization and baseline rows record zero. |
| `summary.csv`: `reduced_chain_count` | Number of chain levels actually reduced before this search. |
| `summary.csv`: `max_evaluations` | Hard trial budget for each local search. |
| `summary.csv`: `gdp_weekly_change` | Returned weekly GDP minus the preceding search's GDP, or the saved baseline's GDP for the first resumed search; empty without a predecessor. |
| `summary.csv`: `started_at_utc`, `elapsed_seconds` | UTC ISO timestamp and elapsed seconds for this search including its starting-point evaluation; baseline rows describe invocation setup through saved-state evaluation and adjustment. |
| `summary.csv`: `is_best` | True only for the earliest highest-GDP row, whose state is exported in the solution reports. |
| `summary.csv`: `completed_iterations` | Total completed local searches, excluding the saved baseline; repeated on every row. |
| `summary.csv`: `total_trial_evaluations` | Sum of local-search trial counts, excluding separate baseline/starting evaluations and final verification; repeated on every row. |
| `summary.csv`: `total_elapsed_seconds` | Invocation elapsed seconds through summary preparation, excluding CSV writes; repeated on every row. |
| `summary.csv`: `best_iteration` | Selected best row's iteration number, including zero when the saved baseline wins; repeated on every row. |
| `summary.csv`: `max_iterations` | Optional cap on completed local searches; empty means unlimited. |
| `summary.csv`: `stop_reason` | `objective_worsened` for a strict decrease from the preceding result, otherwise `max_iterations` when the configured cap is reached; repeated on every row. |

Each summary row describes its own returned state, including the worse search
that triggers stopping. Equal GDP continues iteration; ties select the earliest
best state. Baseline rows have empty search diagnostics, retaining their current
economic and household-equilibrium metrics. Other summary columns follow the
[equilibrium optimization summary](#equilibrium-optimization-summary).
`buildings.csv` follows the [building registry](#building-registry), including
only positive building levels and sorting by level. Reconstruct those levels
by multiplying the labeled matrix by `chains.csv`'s `level` column, then align
by `building + "+" + production_method`.

`market.csv`, `pop.csv`, and `goods_buy_packages.csv` use the same full report
exports as `examples/optimize_equilibrium.py`: `Economy.df_market(state)`,
`Economy.df_pop(state)`, and `Economy.df_goods_buy_packages(state)` with the
wealth index reset to a CSV column.
