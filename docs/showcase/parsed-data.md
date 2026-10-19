---
title: Parsed data
description: Preview and download the generated Victoria 3 parser and production tables.
---

# Parsed data

These tables turn Victoria 3 definitions into analysis-ready CSV files. See the
[parsing guide](../guides/parsing.md) before regenerating them from an installed
game.

`examples/parse.py` regenerates all eight parsed tables and the buy-package
charts in one run. The production-configuration table uses the separate
`examples/production_analysis.py` script.

Use the [parser dictionary](../data-dictionary/parsers.md) for generated parser
fields and the [production dictionary](../data-dictionary/production.md) for
every analytical production-table column.

## Buildings

One row per building, including construction cost, group membership, unlocks,
land use, and resolved inherited building-group attributes. Important columns:
`key`, `building_group`, `required_construction_points`, `land_usage`, and
`economy_of_scale`.

<!-- table-preview: artifacts/datasets/parsed/buildings.csv | columns=key,building_group,required_construction_points,land_usage,economy_of_scale | rows=5 -->

[:material-download: Download `artifacts/datasets/parsed/buildings.csv`](../artifacts/datasets/parsed/buildings.csv)
· [:fontawesome-brands-github: View `examples/parse.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/parse.py)

```bash
uv run python -m examples.parse
```

## Goods

One row per tradeable good with its base cost, category, and trade or consumption
properties. Important columns: `key`, `cost`, `category`, `tradeable`, and
`local`.

<!-- table-preview: artifacts/datasets/parsed/goods.csv | columns=key,cost,category,tradeable,local | rows=5 -->

[:material-download: Download `artifacts/datasets/parsed/goods.csv`](../artifacts/datasets/parsed/goods.csv)
· [:fontawesome-brands-github: View `examples/parse.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/parse.py)

```bash
uv run python -m examples.parse
```

## Population needs

Maps each population need to eligible goods and substitution constraints.
Important columns: `key`, `goods`, `weight`, `min_supply_share`, and
`max_supply_share`.

<!-- table-preview: artifacts/datasets/parsed/pop_needs.csv | columns=key,goods,weight,min_supply_share,max_supply_share | rows=5 -->

[:material-download: Download `artifacts/datasets/parsed/pop_needs.csv`](../artifacts/datasets/parsed/pop_needs.csv)
· [:fontawesome-brands-github: View `examples/parse.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/parse.py)

```bash
uv run python -m examples.parse
```

## Population types

One row per profession or dependent type, including starting wealth, wage
weights, employment flags, and consumption multipliers.

<!-- table-preview: artifacts/datasets/parsed/pop_types.csv | columns=key,start_quality_of_life,wage_weight,working_adult_ratio,consumption_mult | rows=5 -->

[:material-download: Download `artifacts/datasets/parsed/pop_types.csv`](../artifacts/datasets/parsed/pop_types.csv)
· [:fontawesome-brands-github: View `examples/parse.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/parse.py)

```bash
uv run python -m examples.parse
```

## Production methods

Flattened production methods with employment, goods flows, state modifiers,
unlock conditions, and production-method-group context.

<!-- table-preview: artifacts/datasets/parsed/production_methods.csv | columns=building,production_method_group,production_method,employment,goods_tools,goods_steel | rows=5 -->

[:material-download: Download `artifacts/datasets/parsed/production_methods.csv`](../artifacts/datasets/parsed/production_methods.csv)
· [:fontawesome-brands-github: View `examples/parse.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/parse.py)

```bash
uv run python -m examples.parse
```

## Production configurations

The main analytical table has one row per valid combination of production
methods for a building. It contains input/output flows, employment,
private-wage-normalized employment, construction cost, unlock era, and nominal
profitability.

<!-- table-preview: artifacts/datasets/production/production_table.csv | columns=building,production_method,building_group,era,employment,wage_normalized_employment,profit_per_wage_normalized_employment_nominal | rows=5 -->

[:material-download: Download `artifacts/datasets/production/production_table.csv`](../artifacts/datasets/production/production_table.csv)
· [:fontawesome-brands-github: View `examples/production_analysis.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/production_analysis.py)

```bash
uv run python -m examples.production_analysis
```

## State regions

One row per state region with arable land and total resource potential. Resource
columns feed directly into scenario building limits.

<!-- table-preview: artifacts/datasets/parsed/state_regions.csv | columns=key,province_count,arable_land,resource_building_coal_mine,resource_building_iron_mine,resource_building_oil_rig | rows=5 -->

[:material-download: Download `artifacts/datasets/parsed/state_regions.csv`](../artifacts/datasets/parsed/state_regions.csv)
· [:fontawesome-brands-github: View `examples/parse.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/parse.py)

```bash
uv run python -m examples.parse
```

## Technologies

Technology keys, eras, categories, prerequisites, and map-update behavior.

<!-- table-preview: artifacts/datasets/parsed/technology.csv | columns=key,era,category,unlocking_technologies,should_update_map | rows=5 -->

[:material-download: Download `artifacts/datasets/parsed/technology.csv`](../artifacts/datasets/parsed/technology.csv)
· [:fontawesome-brands-github: View `examples/parse.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/parse.py)

```bash
uv run python -m examples.parse
```
