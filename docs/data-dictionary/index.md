---
title: Data dictionary
description: Column meanings, formulas, units, and edge cases for package-defined tables.
---

# Data dictionary

This reference covers columns deliberately created, selected, or transformed by
the package. It applies to public DataFrame reports and example exports:

- [Parser outputs](parsers.md): identifiers, normalized fields, and generated families.
- [Production configurations](production.md): the analytical production table.
- [Economy reports](economy.md): solved building, market, and population tables and the Japan comparison.
- [Supply-chain reports](supply-chain.md): summary, detailed reports, sweeps, and example additions.

Arbitrary game-defined attributes copied through unchanged, such as `icon` in
`buildings.csv`, are outside this dictionary. A patch or mod can introduce such
fields without changing the parser. The parser page describes their general
representation and the transformations applied to them. Dynamic names with a
known meaning are documented once per family, such as `goods_<good>`; replace
the placeholder with the actual script key, for example `goods_steel`.

## Shared conventions

| Convention | Interpretation |
| --- | --- |
| Script identifiers | Strings such as `building_steel_mills`, `steel`, and `pm_bessemer_process`; use these for joins. Display translations are separate columns. |
| Configuration identifiers | `Economy.building_index` joins `building` and the complete `production_method` string with `+`. A configuration represents one combination of production methods, not all levels of a building type. |
| Compound strings | Many parser lists and production-method combinations use `+` as a separator. The parser keeps source order; these strings are not localized unless a separate localization column is requested. |
| Numeric types | “Number” means integer or floating point as appropriate to source data; solved levels and totals can be fractional because optimization is continuous. CSV has no stored dtype; pandas inference can change with missing values. |
| Goods quantities | Weekly goods units or orders, rather than physical SI units. Per-level coefficients describe a fully staffed level; solved totals multiply coefficients by levels and applicable throughput multipliers. |
| Money | Game currency (£). Nominal values use goods `cost` as base price; market values use the state's national prices. Output minus input value excludes payroll and other costs absent from the model. |
| Annualization | Annual GDP is weekly GDP multiplied by 52. Employment, building levels, construction points, land, prices, and dimensionless ratios are not annualized. |
| Construction | Construction points required to build the modeled levels, not a weekly expense or elapsed construction time. |
| Population / per capita | Model totals sum employed workers. These denominators exclude dependents and unemployed population; “per capita” here is per employed person. |
| Fractions and percentages | Shares and margins use fractions, so `0.2` means 20%. The economy market report's `market_prices_variance` instead uses percent units (`20` means +20%). Signed infrastructure shares need not lie between zero and one. |
| Infrastructure | Positive net usage consumes infrastructure; negative net usage provides it. Zero can mean no footprint or exactly offset consumption and provision. |
| Missing values | `pd.NA` / `NaN` mean missing or undefined; CSV generally writes them as blank cells. Empty strings also become blank CSV cells and may be read back as NaN. See each table for defaults. |
| Division | Production profit ratios use ordinary division: nonzero divided by zero gives signed infinity, and zero divided by zero gives NaN. Supply-chain safe ratios return `0.0` when the denominator is exactly zero; they do not clamp negative denominators. |
| Stable schemas | Supply-chain reports retain their named columns even when empty. Generic parser columns depend on the game data; optional enrichments can add or omit columns. |

## Model and source boundaries

The production table aggregates the selected methods' signed goods flows.
`Economy` splits those net coefficients into nonnegative input and output
matrices. They are often described as gross input/output matrices in the API,
but opposing flows already canceled in a production row cannot be recovered.
Profit and GDP measure the modeled goods-value difference, not accounting
profit after wages. A process producing multiple goods retains its entire
output value; the supply-chain API does not allocate its employment or value
added to one coproduct.

Nominal supply-chain optimization uses fixed prices and fixed throughput,
without economy-of-scale bonuses. Market solving changes national prices but
does not simulate shortages, local prices/MAPI, endogenous population demand,
or wealth feedback. Population report wealth starts from the pop-types table;
it is not a solved household-income distribution.

Column definitions follow the current source calculations, not a promise that
old CSV snapshots match every optional field. See the [parsing guide](../guides/parsing.md)
for game-version and localization behavior and the [API reference](../api/index.md)
for call signatures.
