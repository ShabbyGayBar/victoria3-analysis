---
title: Supply-chain reports
description: Every summary and detailed supply-chain report column, sweep field, and example addition.
---

# Supply-chain reports

`SupplyChainAnalyzer` solves a nominal scenario for exactly one positive target
good. Its immutable result exposes the reports below. All schemas remain
present when a report is empty. See [shared conventions](index.md) and the
[supply-chain guide](../guides/supply-chain.md).

## Scope, prices, and graph views

- **System** means every configuration in the solved state, including any
  production outside the terminal good's upstream chain.
- **Chain** means processes in the realized terminal graph: active upstream
  producers, with their input goods and **all** coproduct outputs retained.
  Each included process contributes its whole employment, cost, and value
  added; nothing is allocated to individual coproducts.
- `realized` graphs start from configurations whose level exceeds `tolerance`
  (default `1e-9`). `allowed` graphs start from configurations not disabled by
  the era cap, PM bans, exact building-group bans, or building limits at or
  below tolerance. Both are restricted to the terminal's upstream graph and
  attached coproducts. Allowed membership does not prove LP feasibility.
- `processes(view)`, `goods(view)`, and `flows(view)` use the requested graph,
  defaulting to `realized`. Even in `allowed`, quantities use the **same solved
  levels**; inactive alternatives do not get hypothetical production.
- Input/output coefficients include the compiled fixed throughput multiplier.
  It scales goods, not employment, construction, land, or infrastructure.
  Coefficients split production-table net flows into positive input/output
  magnitudes; flows already offset in that table cannot be recovered.
- Prices are state prices: base prices for the public nominal analyzer. The
  market automobile example at the end of this page has a separate schema.

## Summary

`result.summary()` is a Series with these fixed fields and the resource-building
column families below, named after the terminal good. Sweeps turn them into columns.
On a successful analyzer result, all fields
are present. Let `Q` denote **whole-system** terminal net output, `G_chain` chain
weekly value added, and `L_chain` chain employment. Safe division returns zero
only for an exactly zero denominator.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `scenario` | String / label | `Scenario.display_name()`. | Uses explicit scenario name or the generated display name. |
| `terminal_good` | String / identifier | The single good being analyzed. | Matches the scenario's production target. |
| `objective` | String / category | Nominal objective: `gdp`, `employment`, `automation`, or `construction_cost`. | `gdp_per_capita` is rejected by the analyzer. |
| `solver_status` | Integer / status code | HiGHS result status. | Successful solves normally report 0; sweep failures use synthetic -1. |
| `solver_message` | String / diagnostic text | HiGHS message retained from the solve. | Sweep failures instead retain the exception message. |
| `objective_value` | Float / objective units | Whole-system attained objective: weekly GDP (£/week), employment (workers), automation (workers), or construction points. | Sign restored for maximized GDP/employment; not necessarily a chain-only metric. |
| `target_quantity` | Float / goods units per week | Requested production target. | Strictly positive; a lower bound on net production, not realized gross output. |
| `target_base_value` | Float / £ per week | Target quantity times terminal state price. | Equals base value in nominal analysis; sweep preserves requested value on failure. |
| `terminal_base_price` | Float / £ per goods unit | Terminal price from the state. | Base price in nominal analysis; not an annual rate. |
| `terminal_gross_output` | Float / goods units per week | Whole-system terminal `building_goods_output`. | Before subtracting terminal consumption by processes. |
| `terminal_net_output` | Float / goods units per week | `Q = levels @ net_matrix[:, terminal]`. | Whole-system output minus process inputs; not reduced by exports or population orders. |
| `terminal_surplus` | Float / goods units per week | `terminal_net_output - target_quantity`. | Can be slightly negative within solver tolerance; not a market order balance. |
| `system_gdp_weekly` | Float / £ per week | Sum of system output minus input quantities valued at state prices. | Excludes payroll; imports/exports are not separately added to GDP. |
| `system_gdp_annual` | Float / £ per year | `52 * system_gdp_weekly`. | Annualization only, not a second solve. |
| `chain_gdp_weekly` | Float / £ per week | `G_chain = sum(realized process value_added)`. | Includes entire coproduct values of included processes. |
| `chain_gdp_annual` | Float / £ per year | `52 * chain_gdp_weekly`. | Same process scope as weekly chain GDP. |
| `system_employment` | Float / workers | Sum of all state employment. | Model population means employed workers. |
| `chain_employment` | Float / workers | `L_chain = sum(realized process employment)`. | No allocation to individual output goods. |
| `system_construction_cost` | Float / construction points | Whole-system levels dotted with construction coefficients. | A stock of required construction, not a weekly cost. |
| `chain_construction_cost` | Float / construction points | Sum of realized process construction costs. | Can be zero for zero-cost configurations. |
| `system_arable_land` | Float / arable-land units | Whole-system levels dotted with land coefficients. | Uses the immediate agricultural group rule on the economy dictionary page. |
| `chain_arable_land` | Float / arable-land units | Sum of realized process arable land. | Zero when no included process consumes modeled arable land. |
| `system_net_infrastructure_usage` | Float / infrastructure points | Whole-system levels dotted with net infrastructure coefficients. | Negative means net infrastructure provision. |
| `chain_net_infrastructure_usage` | Float / infrastructure points | Sum of realized process net infrastructure usage. | Also signed; not an absolute consumption total. |
| `employment_per_terminal_unit` | Float / workers per unit/week of output capacity | `L_chain / Q`. | Safe division; denominator is net **system** output, not the target or gross output. |
| `construction_per_terminal_unit` | Float / construction points per unit/week of output capacity | `chain_construction_cost / Q`. | Safe division; construction is not annualized. |
| `gdp_per_terminal_unit` | Float / £ per terminal goods unit | `G_chain / Q`. | Both GDP and net production are weekly; their time factors cancel. |
| `output_per_10k_workers` | Float / goods units per week per 10,000 workers | `Q * 10000 / L_chain`. | Safe division; zero if chain employment is exactly zero. |
| `realized_process_count` | Integer / nodes | Number of configurations in the realized graph. | Counts configurations, not summed building levels. |
| `realized_good_count` | Integer / nodes | Number of good nodes in the realized graph. | Includes terminal and attached coproduct goods. |
| `realized_edge_count` | Integer / edges | Number of directed goods/process edges in the realized graph. | Input and output edges count separately. |
| `allowed_process_count` | Integer / nodes | Number of configurations in the allowed graph. | Includes inactive alternatives upstream of the terminal. |
| `allowed_good_count` | Integer / nodes | Number of good nodes in the allowed graph. | Does not count every good in the economy. |
| `allowed_edge_count` | Integer / edges | Number of directed edges in the allowed graph. | Not the number of diagram edges after visualization pruning. |
| `cyclic_component_count` | Integer / components | Realized strongly connected components with more than one node, or a self-loop. | Zero for an acyclic graph. |
| `cyclic_node_count` | Integer / nodes | Number of realized nodes participating in a directed cycle. | Counts both goods and process nodes. |
| `condensation_depth` | Integer / edges | Longest directed-path length after each realized strongly connected component becomes one node. | Zero for an empty or single-component condensation; counts bipartite graph edges. |
| `extractive_process_count` | Integer / configurations | Count of realized processes marked `is_extractive`. | Uses immediate parent `bg_extraction` or either resource flag. |
| `resource_process_count` | Integer / configurations | Count with `discoverable_resource` **or** `depletable_resource`. | A process with both flags counts once; not resource capacity or remaining stock. |
| `chain_gdp_share` | Float / signed ratio | `chain_gdp_weekly / system_gdp_weekly`. | Safe division; negative or offsetting contributions can put the ratio outside [0, 1]. |
| `chain_employment_share` | Float / fraction | `chain_employment / system_employment`. | Safe division. |
| `chain_construction_share` | Float / fraction | `chain_construction_cost / system_construction_cost`. | Safe division. |
| `chain_arable_land_share` | Float / fraction | `chain_arable_land / system_arable_land`. | Safe division. |
| `chain_infrastructure_share` | Float / signed ratio | `chain_net_infrastructure_usage / system_net_infrastructure_usage`. | Safe division; cancellation and negative values mean it need not lie in [0, 1]. |
| `system_gdp_per_capita_weekly` | Float / £ per worker per week | `system_gdp_weekly / system_employment`. | Safe division; population means employed workers. |
| `system_gdp_per_capita_annual` | Float / £ per worker per year | `52 * system_gdp_per_capita_weekly`. | Included in every summary and sweep, including the video export. |
| `chain_gdp_per_capita_weekly` | Float / £ per worker per week | `chain_gdp_weekly / chain_employment`. | Safe division; includes whole-process coproduct contributions. |
| `chain_gdp_per_capita_annual` | Float / £ per worker per year | `52 * chain_gdp_per_capita_weekly`. | Same realized-chain scope. |
| `system_wage_normalized_employment` | Float / private-wage-equivalent workers | Sum of system levels times production-table `wage_normalized_employment`. | NaN if the column or any contributing coefficient is unavailable/nonfinite; inactive missing coefficients are ignored. |
| `chain_wage_normalized_employment` | Float / private-wage-equivalent workers | Sum of realized-chain levels times production-table `wage_normalized_employment`. | Same missing-data policy, restricted to contributing chain processes. |
| `system_gdp_per_wage_normalized_employment_weekly` | Float / £ per wage-equivalent worker per week | `system_gdp_weekly / system_wage_normalized_employment`. | Safe division; NaN when wage coefficients are unavailable. |
| `system_gdp_per_wage_normalized_employment_annual` | Float / £ per wage-equivalent worker per year | `52 * system_gdp_per_wage_normalized_employment_weekly`. | NaN when wage coefficients are unavailable. |
| `chain_gdp_per_wage_normalized_employment_weekly` | Float / £ per wage-equivalent worker per week | `chain_gdp_weekly / chain_wage_normalized_employment`. | Safe division; NaN when contributing chain wage coefficients are unavailable. |
| `chain_gdp_per_wage_normalized_employment_annual` | Float / £ per wage-equivalent worker per year | `52 * chain_gdp_per_wage_normalized_employment_weekly`. | Same realized-chain scope. |
| `system_gdp_per_construction_cost_weekly` | Float / £ per construction point per week | `system_gdp_weekly / system_construction_cost`. | Safe division; construction is a stock, not a weekly expense. |
| `system_gdp_per_construction_cost_annual` | Float / £ per construction point per year | `52 * system_gdp_per_construction_cost_weekly`. | Annualizes GDP only. |
| `chain_gdp_per_construction_cost_weekly` | Float / £ per construction point per week | `chain_gdp_weekly / chain_construction_cost`. | Safe division; includes all construction of realized-chain processes. |
| `chain_gdp_per_construction_cost_annual` | Float / £ per construction point per year | `52 * chain_gdp_per_construction_cost_weekly`. | Annualizes GDP only. |

Graph counts use the complete retained graphs. They are independent of the
top-producer pruning used by a plotted or Mermaid allowed view.

## Resource building levels

These summary column families use full building identifiers, for example
`chain_levels_building_coal_mine` and
`chain_levels_per_10k_pop_building_coal_mine`. Extraction membership uses the
same rule as `is_extractive`: immediate parent `bg_extraction`, or a discoverable
or depletable resource flag. This includes ordinary mines, logging camps,
fishing wharves, whaling stations, rubber plantations, and oil rigs. Farms,
ranches, and other arable-land plantations remain represented by arable land.

Types come from the full economy production table, including banned and unused
types. Columns follow the fixed summary fields, sorted by building identifier;
within each type, system raw/normalized levels precede chain raw/normalized
levels. All summaries from one economy share this schema, even empty sweeps
and all-failure sweeps. Successful unused types are zero; failed solves are NaN.

| Column family | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `system_levels_<building>` | Float / building levels | Sum of all solved configuration levels for this extraction building type. | Fractional levels are retained; no aggregate resource-level total is added. |
| `system_levels_per_10k_pop_<building>` | Float / levels per 10,000 workers | `system_levels_<building> * 10000 / system_employment`. | Safe division; excludes dependents and unemployed people. |
| `chain_levels_<building>` | Float / building levels | Sum of realized-chain configuration levels for this extraction building type. | Multiple PM configurations of one building type are combined. |
| `chain_levels_per_10k_pop_<building>` | Float / levels per 10,000 workers | `chain_levels_<building> * 10000 / chain_employment`. | Safe division; 5 levels and 2,000 chain workers give 25 levels per 10,000 workers. |

## Processes

`result.processes(view)` has one row per configuration in the requested graph,
in production-table row order. Let `x` be its solved level, `m` its throughput
multiplier, `I` its adjusted input value per level, and `O` its adjusted output
value per level. Unit economics retain all output goods.

Here, **process** means a building with its complete PM combination, rather
than the building type alone. The guide explains the
[naming rationale and parallels with Brightway](../guides/supply-chain.md#why-the-graph-uses-processes).

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `config` | String / configuration identifier | `Economy.building_index` key for the row. | Joins to `flows.process` and workforce/alternatives `config`. |
| `building` | String / identifier | Source building key. | Multiple configurations may share it. |
| `production_method` | String / compound identifiers | Complete chosen method combination. | Methods are joined by `+`. |
| `building_group` | String / identifier | Immediate source building group. | Missing metadata defaults to empty string. |
| `parent_group` | String / identifier | Immediate parent metadata of that group. | Missing metadata defaults to empty string. |
| `land_usage` | String / category | Source resolved land-use metadata. | Missing metadata defaults to empty string; not the land coefficient itself. |
| `era` | Integer / era number | Source configuration era. | Required by the reporting implementation. |
| `allowed` | Boolean / membership flag | Process node is in the terminal's allowed graph. | Graph membership, not independent LP feasibility. |
| `active` | Boolean / solved flag | `x > tolerance`. | May be false in the allowed view. |
| `in_terminal_chain` | Boolean / membership flag | Configuration appears in the realized terminal graph. | An active process elsewhere in the system can still be false. |
| `level` | Float / building levels | `x`, from the whole solved state. | Fractional or zero levels are valid. |
| `throughput_multiplier` | Float / multiplier | Compiled fixed goods multiplier `m`. | `1` means unchanged; excludes level-dependent economy of scale. |
| `unit_input_cost` | Float / £ per week per level | `I = adjusted input row @ state prices`. | Includes throughput; zero with no modeled inputs. |
| `unit_output_value` | Float / £ per week per level | `O = adjusted output row @ state prices`. | Includes every coproduct. |
| `unit_value_added` | Float / £ per week per level | `O - I`. | Can be negative; excludes wages. |
| `input_cost` | Float / £ per week | `I * x`. | Zero for a zero-level allowed alternative. |
| `output_value` | Float / £ per week | `O * x`. | Zero for a zero-level allowed alternative. |
| `value_added` | Float / £ per week | `(O - I) * x`. | Entire process contribution, not allocated to one good. |
| `employment` | Float / workers | Per-level employment coefficient times `x`. | Not multiplied by `m`. |
| `construction_cost` | Float / construction points | Per-level construction coefficient times `x`. | Not multiplied by `m`. |
| `arable_land` | Float / arable-land units | Per-level land coefficient times `x`. | Uses immediate group membership; not multiplied by `m`. |
| `net_infrastructure_usage` | Float / infrastructure points | Per-level net infrastructure coefficient times `x`. | Signed; not multiplied by `m`. |
| `is_extractive` | Boolean / classification flag | Immediate `parent_group == "bg_extraction"` or either resource flag in allowed-graph metadata. | Defaults false if no matching metadata; does not traverse ancestors. |
| `is_subsistence` | Boolean / source flag | Source subsistence metadata. | Missing metadata defaults false. |
| `discoverable_resource` | Boolean / source flag | Source discoverable-resource metadata. | Missing metadata defaults false. |
| `depletable_resource` | Boolean / source flag | Source depletable-resource metadata. | Missing metadata defaults false; depletion is not simulated. |

## Goods

`result.goods(view)` has one row per good node in the requested graph, in
economy goods order. Production and consumption sum only processes in that
view, while imports, exports, and population orders come from the **whole
state**. This mix of scopes means these balances need not equal whole-system
market balances. Producer counts use the two retained graphs irrespective of
the requested view.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `good` | String / identifier | Good key. | Includes attached coproduct goods. |
| `terminal` | Boolean / flag | Whether this is the analyzed terminal good. | True only for the terminal key. |
| `price` | Float / £ per goods unit | State price for this good. | Base price in nominal analysis. |
| `production` | Float / goods units per week | View-process levels times adjusted output coefficients. | Zero is valid for an input-only good or inactive allowed production. |
| `consumption` | Float / goods units per week | View-process levels times adjusted input coefficients. | Positive magnitude, not a negative signed flow. |
| `imports` | Float / goods units per week | Whole-state imported orders. | Zero when no imports supplied. |
| `exports` | Float / goods units per week | Whole-state exported orders. | Zero when no exports supplied. |
| `pop_needs` | Float / goods units per week | Whole-state exogenous population orders. | Zero when no population orders supplied. |
| `sell_orders` | Float / goods units per week | View `production + imports`. | Combines view and state scope. |
| `buy_orders` | Float / goods units per week | View `consumption + exports + pop_needs`. | Combines view and state scope. |
| `net_balance` | Float / goods units per week | `sell_orders - buy_orders`. | Signed; differs from terminal net production. |
| `output_value` | Float / £ per week | View `production * price`. | Imports are not included. |
| `input_value` | Float / £ per week | View `consumption * price`. | Exports/population orders are not included. |
| `input_cost_share` | Float / fraction | `input_value / total input value of all view processes`. | Safe division; zero when total input value is zero. |
| `allowed_producers` | Integer / configurations | Process predecessors of this good in the allowed graph. | Restricted graph count, not every producer in the economy. |
| `active_producers` | Integer / configurations | Process predecessors of this good in the realized graph. | Count unaffected by `view`; does not sum their levels. |

## Flows

`result.flows(view)` has one row per directed graph edge, sorted by the source
and target node strings. Inputs point from goods to processes; outputs point
from processes to goods. Rates and amounts are positive magnitudes.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `source` | String / node identifier | Edge source: `good:<key>` or `process:<config>`. | Direction depends on role. |
| `target` | String / node identifier | Edge target: `process:<config>` or `good:<key>`. | Direction depends on role. |
| `role` | String / category | `input` or `output`. | Distinguishes flow direction without a signed rate. |
| `good` | String / identifier | Good carried by this edge. | Same key as the goods report. |
| `process` | String / configuration identifier | Configuration key, without the `process:` prefix. | Same key as process `config`. |
| `unit_rate` | Float / goods units per week per level | Adjusted input or output coefficient. | Includes throughput; edges are created only for coefficients > 0. |
| `realized_amount` | Float / goods units per week | `unit_rate * solved process level`. | Can be zero for an allowed alternative. |
| `price` | Float / £ per goods unit | State price for the edge's good. | Base price in nominal analysis. |
| `realized_value` | Float / £ per week | `realized_amount * price`. | Zero for an inactive flow. |
| `active` | Boolean / flow flag | `realized_amount > tolerance`. | Amount threshold, distinct from process level threshold. |
| `in_cycle` | Boolean / endpoint flag | Both endpoints are cyclic nodes in the requested graph. | Does not require them to belong to the same cyclic component; do not interpret it as an exact cycle-edge test. |

## Workforce

`result.workforce()` uses only realized-chain configurations, in row order then
profession order. It omits process/profession employment at or below tolerance.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `config` | String / configuration identifier | Configuration employing the profession. | Joins to processes. |
| `building` | String / identifier | Configuration's source building. | Multiple rows can share it. |
| `profession` | String / identifier | Profession key from the economy's profession index. | No row for employment at or below tolerance. |
| `employment` | Float / workers | State employment cell for this configuration/profession. | Per-level profession coefficient times solved level; throughput does not change it. |

## Constraints and bottlenecks

`result.constraints()` exposes compiled LP rows, inequalities first and
equalities second, in their named slice order. Constraints apply to the whole
system. Inequalities are stored in canonical form `A_ub @ levels <= b_ub`;
for example a minimum production target is stored with negative coefficients
and a negative bound. Interpret the **compiled** sign before converting a
marginal to a gameplay change. Variable bounds are not rows in this report.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `kind` | String / category | `inequality` or `equality`. | Determines slack/residual interpretation. |
| `family` | String / constraint identifier | Named compiled constraint slice, such as `min_goods_output`, `default_min_goods_output`, or `building_level_caps`. | Only families present in the compiled problem appear. |
| `label` | String / row label | Good/building/group key for applicable families; PM bans use their `+`-joined keys; other rows use the family name. | If label count differs from row count, uses `family[i]`. |
| `realized_value` | Float / compiled row units | `A_row @ solved levels`. | Signed canonical left-hand side, not always the physical quantity named by the family. |
| `bound` | Float / compiled row units | Stored right-hand side `b_row`. | A lower-bound target can be represented as a negative bound. |
| `slack` | Float / compiled row units | For inequalities, `bound - realized_value`. | NaN for equalities; slightly negative values can occur within solver tolerance. |
| `residual` | Float / compiled row units | For equalities, `realized_value - bound`. | Exactly 0 in this column for inequalities. |
| `binding` | Boolean / threshold flag | Inequality `slack <= tolerance`; equality `abs(residual) <= tolerance`. | Numerical criterion, not proof that relaxing the row improves the objective. |
| `solver_marginal` | Float / solver objective units per compiled bound unit | Raw HiGHS derivative of its **minimized** objective with respect to this right-hand side. | NaN if diagnostics unavailable; GDP/employment objectives are negated for minimization. |
| `improvement_per_unit` | Float / solver objective units per compiled bound unit | For a finite inequality marginal, `max(0, -solver_marginal)`. | NaN for equalities or unavailable/nonfinite marginals; local sensitivity to increasing the canonical bound. |

For minimized construction/automation, positive improvement means lowering
the minimized cost. For maximized GDP/employment, it means increasing the
reported objective. It measures one unit of the compiled RHS, so relaxing a
negative production constraint means lowering its requested physical minimum.
It is local LP sensitivity and is not a guaranteed finite-change benefit.

`result.bottlenecks()` returns the **same columns**, restricted to binding
inequalities with `improvement_per_unit > tolerance`, sorted by improvement
descending, then family and label. It has no separate schema.

## Alternatives

`result.alternatives(good)` lists producer predecessors of the specified good
in the terminal's allowed graph. With no argument it covers all goods in that
graph. It sorts by good, selected first, unit output descending, then config.
Unit costs and values describe the **entire process**, not only the requested
good. “Selected” means membership in the realized chain, not simply a positive
level anywhere in the system.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `good` | String / identifier | Good for which this process is an alternative producer. | A coproduct process can appear once per output good. |
| `config` | String / configuration identifier | Allowed producer configuration key. | No row if the good has no producer in the allowed graph. |
| `building` | String / identifier | Source building key. | Same metadata as the process report. |
| `production_method` | String / compound identifiers | Complete method combination. | `+`-joined. |
| `era` | Integer / era number | Configuration's required era. | Same metadata as the process report. |
| `unit_output` | Float / goods units per week per level | Adjusted output coefficient for **this good**. | Includes throughput, unlike the all-goods monetary unit fields. |
| `unit_input_cost` | Float / £ per week per level | Whole adjusted process input row valued at state prices. | Includes all process inputs. |
| `unit_output_value` | Float / £ per week per level | Whole adjusted process output row valued at state prices. | Includes every coproduct. |
| `unit_value_added` | Float / £ per week per level | `unit_output_value - unit_input_cost`. | Excludes wages; can be negative. |
| `selected` | Boolean / membership flag | Configuration occurs in the realized terminal graph. | False for alternatives outside that chain, even if active elsewhere. |
| `level` | Float / building levels | Whole-state solved level of the configuration. | Zero allowed for an inactive alternative. |
| `parent_group` | String / identifier | Parent metadata from the allowed graph. | Missing metadata defaults to empty string. |
| `land_usage` | String / category | Land-use metadata from the allowed graph. | Missing metadata defaults to empty string. |
| `is_extractive` | Boolean / classification flag | Immediate parent `bg_extraction` or either resource flag. | No ancestor traversal. |
| `is_subsistence` | Boolean / source flag | Source subsistence flag. | Missing metadata defaults false. |
| `discoverable_resource` | Boolean / source flag | Source discoverable-resource flag. | Missing metadata defaults false. |
| `depletable_resource` | Boolean / source flag | Source depletable-resource flag. | Missing metadata defaults false. |

## Sweep summary and failures

`sweep_supply_chains()` generates one scenario per requested good, preserving
the requested order (by default `economy.producible_goods` order). Each quantity
is `target_value / base_price`; every requested base price must be finite and
positive. `sweep.summary` contains these fields followed by **all**
[summary fields](#summary). `sweep.failures` is the failed subset with the same
columns and a reset index, including when empty.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `good` | String / identifier | Good selected for this sweep row. | Matches `terminal_good`; retained on failures. |
| `status` | String / category | `success` or `failure`. | Failed solves do not stop subsequent goods. |
| `error_type` | String / exception name | Type of caught analysis exception. | Empty on success; currently `ValueError` on recorded failures. |
| `error_message` | String / diagnostic text | Caught exception message. | Empty on success; retained on failure. |

On failure, scenario, terminal good, objective, target quantity, requested base
value, and terminal base price remain populated. `solver_status` becomes `-1`
and `solver_message` becomes the exception text. All remaining summary fields
are NaN, including counts and `objective_value`; they do **not** mean zero.
Sweep input-validation errors raise before an applicable result rather than
becoming failure rows. A template's `min_goods_output` basket is ignored with a warning.

## Example CSV additions

The nominal example exports retain every sweep field, including its failure
policy, and add these labels. The comparison `summary.csv` has one row per
configuration/good pair; video `summary.csv` files have one row per
variant/good pair. Detailed results live under
`analyses/supply_chains/<configuration>/<good>/`; cross-good `summary.csv`
files live at configuration level. Cross-configuration comparisons live under
`analyses/supply_chains/comparison/summary.csv`, alongside the population,
construction, and annual GDP per capita charts `pop.svg`,
`construction_points.svg`, and `gdp_per_capita.svg`.
Labels describe presets, not additional economic metrics.

| Column | Type / unit | Meaning / source | Presence / edge cases |
| --- | --- | --- | --- |
| `configuration` | String / preset label | Scenario preset in `examples/supply_chain_compare.py`. | In comparison and preset summary CSVs; rows retain it on failure. |
| `variant` | String / preset label | `base` or a named product-specific variant in `examples/supply_chain_cangshulun.py`. | Only in video summary CSVs; base covers all producible goods, named variants selected goods. |
| `ban_config` | String / preset label | Ban-policy label supplied by the example. | Retained on failure; an empty label in the comparison export does not mean no default building-group bans. |

See the [supply-chain API](../api/supply-chain.md) for report calls and the
[showcase](../showcase/supply-chains.md) for example downloads and commands.
