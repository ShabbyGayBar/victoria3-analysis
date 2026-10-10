---
title: Parser outputs
description: Package-defined parser columns and predictable dynamic column families.
---

# Parser outputs

These entries describe package-defined columns. Other attributes, such as an
icon path or an AI weight, are passed through from the game and are not an
enumerated schema. Values and concrete family members depend on game version
and mods. See [shared conventions](index.md#shared-conventions).

## Identifiers and localization

Buildings, building groups, goods, population types, state regions, and
technologies normally have one row per script definition, identified by `key`.
Population needs instead have one row per need/good entry, so `key` repeats.
Production-method rows use the three identifiers described below. Buy packages
use numeric `wealth`.

| Column | Type / unit | Meaning / source | Presence / edge cases |
| --- | --- | --- | --- |
| `key` | String / identifier | Definition key from its source file; in population needs, the need key rather than a unique row key. | Included by these parsers, even when other attributes vary. |
| `key_localization` | Nullable string / display text | Lookup of `key` in the requested language. | Only with `language`; missing lookup is `pd.NA`, with no language fallback. |
| `building_localization` | Nullable string / display text | Localized production-method row's `building`. | Only with `language` on a nonempty production-method table. |
| `building_group_localization` | Nullable string / display text | Localized building's `building_group`. | With `language` if its source column exists. |
| `production_method_group_localization` | Nullable string / display text | Localized production-method row's group key. | Only with `language` on a nonempty production-method table. |
| `production_method_localization` | Nullable string / display text | Localized production-method row's method key. | Only with `language` on a nonempty production-method table. |

Localized text preserves raw game references, formatting, icons, and functions;
the parser does not evaluate them. Localization columns are placed beside
their identifier. Raw script identifiers remain the join keys.

## Buildings and building groups

`BuildingsParser.to_dataframe()` has one row per building.
`BuildingGroupParser.to_dataframe()` has one row per group and does **not**
resolve inheritance. The building export joins the group's resolved scalar
attributes. Nested dict/Tree attributes are omitted; lists are `+`-joined.

| Column or family | Type / unit | Meaning / transformation | Presence / edge cases |
| --- | --- | --- | --- |
| `required_construction_points` | Integer / construction points per level | Resolves a building's `required_construction` script-value name through `common/script_values` (`construction_cost_*`). | Absent when no reference exists; unknown references warn and skip the value. Other rows can then have NaN in this column. |
| `land_usage` | String / category | Joined group value: `urban` or `rural`, inherited from the first ancestor that specifies it when missing locally. | Unresolved values remain absent/missing; raw group export does not apply inheritance. |
| `cash_reserves_max` | Number / £ per level | Joined group cash-reserve ceiling, inherited when missing **or zero**. | An ancestor's zero is also skipped; no reachable value leaves the original value unchanged. |
| `economy_of_scale` | Boolean / flag | Joined group eligibility, inherited when missing from the child group. | Explicit false is retained; the production table additionally excludes subsistence buildings. |
| `building_group_<attribute>` | Source-dependent / inherited source unit | Collision-prefixed joined group attribute when its name already exists in the building row. For example, `building_group_land_usage`. | Collision handling is per row; the concrete attributes are game-defined. Building values are preserved. |

Other joined scalar group attributes remain group-local rather than inherited.
Parent-chain traversal stops at unknown parents or cycles. A missing group
reference warns and skips the join. These are transformations, not a claim
that every named field exists in every input definition.

## Production methods

`ProductionMethodParser.to_dataframe()` has one row per
building/production-method-group/production-method membership, not one row per
complete building configuration. The same method can occur in multiple rows.
Scalar method attributes are passed through, lists are `+`-joined, and nested
containers are omitted. The computed families below are zero-filled.

| Column or family | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `building` | String / identifier | Building whose production-method group contains this method. | Fixed row identifier. |
| `production_method_group` | String / identifier | Group providing the method choice. | Fixed row identifier; unknown referenced groups raise an error. |
| `production_method` | String / identifier | Single chosen method in that group. | Fixed row identifier; complete combinations are formed by `production_table()`. |
| `employment` | Number / workers per level | Sum of `building_employment_*` values in the method's `level_scaled` building modifiers. | Zero when absent; negative automation adjustments are retained. |
| `employment_<profession>` | Number / workers per level | Value of `building_employment_<profession>_add`; e.g. `employment_laborers`. | Family discovered from employment modifiers; absent method/profession values are zero. |
| `goods_<good>` | Number / goods units per week per level | Signed `workforce_scaled` goods modifier: output positive, input negative; e.g. `goods_tools`. | One column per supplied/parsed good; absent flows zero. The parser assigns matched modifiers rather than resolving arbitrary game effects. |

State-modifier keys are also flattened from `unscaled`, `level_scaled`, and
`workforce_scaled` blocks and zero-filled across rows. Their concrete names and
units are game-defined and excluded from the enumerated dictionary. Flattening
drops the scaling-block distinction; duplicate keys across blocks of a method
raise `ValueError`. One explicitly consumed modifier,
`state_infrastructure_add`, represents infrastructure generation in the
production table's net-footprint calculation; it is present in the method
table only if discovered in the inputs.

## Technologies

One row per technology. Nested dict/Tree blocks are omitted and lists are
`+`-joined; remaining scalar attributes are passed through.

| Column | Type / unit | Meaning / transformation | Presence / edge cases |
| --- | --- | --- | --- |
| `era` | Integer / era number | Converts source `era_N` to numeric `N`. | Converted when present; an unparsable era raises `ValueError`. The parser does not synthesize a missing era. |

## Population needs

`PopNeedsParser.to_dataframe()` emits one row per need/good substitution entry.
Rows are identified by the need key and eligible good. These six columns
remain present in an empty result; localization is optional.

| Column | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `key` | String / identifier | Population need to which the entry belongs. | Repeats across eligible goods. |
| `goods` | String / identifier | Good allowed to satisfy the need, from the entry's `goods`. | Missing entry field remains missing. |
| `weight` | Number / relative weight | Base substitution weight applied to the good based on market sell-order share, preserved without normalization. | Defaults to 1 when absent. |
| `max_supply_share` | Number / fraction | Sell-order share ceiling above which additional relative supply no longer increases the applied base weight. | Defaults to 1; stored rather than enforced by the parser. |
| `min_supply_share` | Number / fraction | Minimum multiplier of base weight applied regardless of the good's sell-order share. | Defaults to 0; stored rather than enforced by the parser. |
| `is_default` | Boolean / flag | Whether the entry's good equals the need's `default` good. | Computed by equality; a need without entries raises an error. |

## Buy packages

`buy_packages()` emits one row per matching `wealth_N` definition, sorted by
numeric wealth. `popneed_*` entries represent population **needs**, not individual
tradeable goods. Game buy packages express base-value budgets for 10,000 working
adults. The values below retain those source amounts, not converted
physical goods quantities or realized demand from `Economy`.

| Column or family | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `wealth` | Integer / wealth level | Numeric `N` extracted from the `wealth_N` key. | Nonmatching definitions are skipped. |
| `political_strength` | Number / source political-strength factor | The wealth definition's `political_strength`. | Missing source value remains missing; not included in the needs total. |
| `total_popneeds` | Number / £ base-value budget per 10,000 working adults | Sum of all `popneed_*` values in this wealth row. | Zero when no matching needs exist; no population scaling is performed. |
| `popneed_<need>` | Number / £ base-value budget per 10,000 working adults | Need amount from the definition's `goods` block; e.g. `popneed_basic_food`. | Columns follow first-seen order; absence at a wealth level is zero-filled. |

## State regions

One row per state region. Arbitrary scalar attributes are passed through;
nested attributes and province/trait/arable-resource lists are omitted, apart
from the transformations below.

| Column or family | Type / unit | Meaning / calculation | Presence / edge cases |
| --- | --- | --- | --- |
| `province_count` | Integer / provinces | Counts all `provinces` entries in the parsed region tree. | Zero when none are found; does not subtract impassable provinces. |
| `resource_<building>` | Integer / potential building levels | Capacity from `capped_resources`, or `undiscovered_amount + discovered_amount` from a `resource` block. Example: `resource_building_oil_rig`. | Only encountered resource types become columns; missing/non-numeric cells are coerced to zero and converted to integers. |
| `undiscovered_amount_resource_<building>` | Integer / building levels | Undiscovered component of a `resource` block. | Defaults to zero within the block; exists only for encountered resource-block types. |
| `discovered_amount_resource_<building>` | Integer / building levels | Discovered component of a `resource` block. | Defaults to zero within the block; not synthesized for capped-resource entries. |

These capacities describe definitions, not a save game's current discoveries
or exploitation. `state_region_resource_limits()` uses total-potential
`resource_*` columns only. It sums selected regions once each, treats
missing/non-numeric values as zero, adds gold-field potential to gold-mine
capacity, and sets gold-field capacity to zero. The separate arable-land helper
sums the source `arable_land` field; that raw attribute is not synthesized by
the parser.

## Goods and population types

Beyond the shared `key` and optional `key_localization`, these tables preserve
game-defined attributes and do not add analytical columns. Population types
omit nested containers and `+`-join lists. Goods preserve the source attribute
values directly, including any nested values. The model consumes goods `cost`
as base price and population-type `start_quality_of_life`, `wage_weight`, and
`paid_private_wage`; their role in derived metrics is documented on the
[production](production.md) and [economy](economy.md) pages.

See the [parsing API](../api/parsing.md) for constructors and source directories.
