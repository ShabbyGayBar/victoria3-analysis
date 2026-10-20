---
title: Production configurations
description: Every fixed production-table column, optional enrichment, and dynamic family.
---

# Production configurations

`production_table()` and `production_table.csv` contain one row per enumerated
building configuration: one method from each of the building's method groups.
The `building` and complete `production_method` string identify the row. The
table does not filter combinations by a particular scenario or all gameplay
conditions. Values describe one fully staffed building level, before throughput
bonuses, and use goods base prices. See [shared conventions](index.md).

## Identity, metadata, and requirements

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `building` | String / identifier | Source building key. | Always included. |
| `building_localization` | Nullable string / display text | Building label propagated from the buildings input. | Only if its input localization column exists; unknown labels are `pd.NA`. |
| `production_method` | String / identifiers | Selected method keys joined by `+`, in building method-group order. | Always included; identifies a complete combination. |
| `production_method_localization` | Nullable string / display text | Selected method labels joined by `+`. | Only if method localization input exists; any missing label makes the whole result `pd.NA`. |
| `building_group` | String / identifier | Building's immediate group. | Always included from buildings input. |
| `building_group_localization` | Nullable string / display text | Propagated label for that group. | Only with the buildings input's group localization column. |
| `parent_group` | Nullable string / identifier | Parent group metadata joined onto the source building. | Defaults to `pd.NA` when the source column is absent; not the entire ancestor chain. |
| `land_usage` | Nullable string / category | Source building's resolved land-use category. | Defaults to `pd.NA` if absent; see parser inheritance rules. |
| `is_subsistence` | Boolean / flag | Source subsistence-building flag. | Missing values/column become false. |
| `discoverable_resource` | Boolean / flag | Source discoverable-resource flag. | Missing values/column become false; not a numerical resource cap. |
| `depletable_resource` | Boolean / flag | Source depletable-resource flag. | Missing values/column become false; no depletion is simulated. |
| `economy_of_scale` | Boolean / eligibility flag | Source `economy_of_scale` is true **and** source `is_subsistence` is false. | Missing flags become false; eligibility does not apply a throughput bonus to this table. |
| `urbanization` | Number / urbanization points per level | Source building's urbanization contribution. | Missing value becomes zero. |
| `infrastructure_usage_per_level` | Number / infrastructure points per level | Source infrastructure usage minus the sum of chosen methods' `state_infrastructure_add`. | Missing usage becomes zero; absent modifier column warns and is zero-filled. Negative means provision. |
| `era` | Integer / era number | Maximum era of the building's and chosen methods' unlocking technologies. | Only with `df_tech`; zero if no required technologies; unknown required technologies raise an error. |
| `unlocking_tech` | String / identifiers | Building requirements followed by chosen method requirements, deduplicated in first-seen order and joined by `+`. | Always included; empty string for no requirements. |
| `unlocking_tech_localization` | Nullable string / display text | Required technology labels joined by `+`. | Only with a localized technology input; empty requirements or any missing label yield `pd.NA`. |
| `construction_cost` | Integer / construction points per level | Building's resolved `required_construction_points`. | Missing cost becomes zero; construction cost is not subtracted from weekly profit. |

## Employment and goods flows

| Column or family | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `employment` | Number / workers per level | Sum of chosen methods' total employment. | Always included; includes automation adjustments. |
| `employment_<profession>` | Number / workers per level | Sum of chosen methods' profession-specific employment; e.g. `employment_engineers`. | One column per profession present in the methods input. |
| `wage_normalized_employment` | Number / private-wage-equivalent workers per level | Sum of profession employment times `wage_weight`, counting only professions whose `paid_private_wage` flag is true. | Only with `df_pop_types`; missing private-wage flags default to true, including when the column is absent in older game data. Invalid or missing required profession weights raise an error. |
| `goods_<good>` | Number / goods units per week per level | Sum of the chosen methods' signed flow for the good: positive output, negative input. | One per goods-table key, in goods-table row order; missing methods input columns warn and are zero-filled. Unpriced goods columns are ignored with a warning. |
| `input_ratio_goods_<good>` | Float / fraction | `max(-goods_<good>, 0) / sum(max(-goods_<all goods>, 0))`. | Immediately follows its goods column. Zero for outputs, zero flows, and configurations without net inputs. |

The input ratios use physical **net-input quantities**, not base-value shares.
They sum to one when net inputs exist, otherwise zero. They cannot recover
inputs offset by outputs of the same good. Prestige variants share the base
good's column. Victoria 3's prestige-goods throughput bonus uses gross input
base value; multiplying these ratios by the game's 20% maximum gives only a
quantity-based analytical proxy.

For example, net inputs of 10 tools and 30 coal have quantity shares 0.25 and
0.75 regardless of their different prices. A net output contributes zero.

## Nominal economic metrics

Let `q_g` be the row's signed goods flow, `p_g` the goods base price,
`I = sum(max(-q_g, 0) * p_g)`, and `O = sum(max(q_g, 0) * p_g)`.
Let `L` be employment, `W` wage-normalized employment, and `C` construction
cost. These input/output valuations split **net** flows; payroll is not
subtracted. All monetary flows are weekly.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `value_goods_inputs_nominal` | Float / £ per week per level | `I`: base-price value of negative net goods flows. | Zero when no net inputs. |
| `value_goods_outputs_nominal` | Float / £ per week per level | `O`: base-price value of positive net goods flows. | Zero when no net outputs. |
| `profit_nominal` | Float / £ per week per level | `O - I`, modeled goods-value surplus. | Can be negative; excludes wages and construction expenditure. |
| `profit_margin_nominal` | Float / fraction | `(O - I) / O`. | Ordinary division; negative infinity if output value is zero and profit is negative, NaN for zero/zero. |
| `profit_per_capita_nominal` | Float / £ per worker per week | `(O - I) / L`. | Per employed worker; zero denominator can yield signed infinity or NaN. |
| `profit_per_wage_normalized_employment_nominal` | Float / £ per wage-equivalent worker per week | `(O - I) / W`. | Only with `df_pop_types`; ordinary division, with no payroll subtraction. |
| `profit_per_construction_cost_nominal` | Float / £ per week per construction point | `(O - I) / C`. | Ordinary division; zero construction cost can yield signed infinity or NaN. |

Weekly profit and the per-worker/per-construction profit rates can be
multiplied by 52 for annual equivalents. Do not annualize `profit_margin_nominal`
or input shares. Missing localized text and undefined numeric ratios can both
appear as blank CSV cells, but have different meanings.

See the [economy and production API](../api/economy.md) and
[parsing guide](../guides/parsing.md#build-the-production-table).
