---
title: Parsed data
description: Preview and download the generated Victoria 3 parser and production tables.
---

# Parsed data

These tables turn Victoria 3 definitions into analysis-ready CSV files. See the
[parsing guide](../guides/parsing.md) before regenerating them from an installed
game.

## Buildings

One row per building, including construction cost, group membership, unlocks,
land use, and resolved inherited building-group attributes. Important columns:
`key`, `building_group`, `required_construction_points`, `land_usage`, and
`economy_of_scale`.

<!-- table-preview: tables/buildings.csv | columns=key,building_group,required_construction_points,land_usage,economy_of_scale | rows=5 -->

[:material-download: Download `tables/buildings.csv`](../tables/buildings.csv)
· [:fontawesome-brands-github: View `examples/buildings.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/buildings.py)

```bash
uv run python -m examples.buildings
```

## Goods

One row per tradeable good with its base cost, category, and trade or consumption
properties. Important columns: `key`, `cost`, `category`, `tradeable`, and
`local`.

<!-- table-preview: tables/goods.csv | columns=key,cost,category,tradeable,local | rows=5 -->

[:material-download: Download `tables/goods.csv`](../tables/goods.csv)
· [:fontawesome-brands-github: View `examples/goods.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/goods.py)

```bash
uv run python -m examples.goods
```

## Population needs

Maps each population need to eligible goods and substitution constraints.
Important columns: `key`, `goods`, `weight`, `min_supply_share`, and
`max_supply_share`.

<!-- table-preview: tables/pop_needs.csv | columns=key,goods,weight,min_supply_share,max_supply_share | rows=5 -->

[:material-download: Download `tables/pop_needs.csv`](../tables/pop_needs.csv)
· [:fontawesome-brands-github: View `examples/pop_needs.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/pop_needs.py)

```bash
uv run python -m examples.pop_needs
```

## Population types

One row per profession or dependent type, including starting wealth, wage
weights, employment flags, and consumption multipliers.

<!-- table-preview: tables/pop_types.csv | columns=key,start_quality_of_life,wage_weight,working_adult_ratio,consumption_mult | rows=5 -->

[:material-download: Download `tables/pop_types.csv`](../tables/pop_types.csv)
· [:fontawesome-brands-github: View `examples/pop_types.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/pop_types.py)

```bash
uv run python -m examples.pop_types
```

## Production methods

Flattened production methods with employment, goods flows, state modifiers,
unlock conditions, and production-method-group context.

<!-- table-preview: tables/production_methods.csv | columns=building,production_method_group,production_method,employment,goods_tools,goods_steel | rows=5 -->

[:material-download: Download `tables/production_methods.csv`](../tables/production_methods.csv)
· [:fontawesome-brands-github: View `examples/production_method.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/production_method.py)

```bash
uv run python -m examples.production_method
```

## Production configurations

The main analytical table has one row per valid combination of production
methods for a building. It contains input/output flows, employment, construction
cost, unlock era, and nominal profitability.

<!-- table-preview: tables/production_table.csv | columns=building,production_method,building_group,era,employment,construction_cost,profit_nominal | rows=5 -->

[:material-download: Download `tables/production_table.csv`](../tables/production_table.csv)
· [:fontawesome-brands-github: View `examples/production_analysis.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/production_analysis.py)

```bash
uv run python -m examples.production_analysis
```

## State regions

One row per state region with arable land and total resource potential. Resource
columns feed directly into scenario building limits.

<!-- table-preview: tables/state_regions.csv | columns=key,province_count,arable_land,resource_building_coal_mine,resource_building_iron_mine,resource_building_oil_rig | rows=5 -->

[:material-download: Download `tables/state_regions.csv`](../tables/state_regions.csv)
· [:fontawesome-brands-github: View `examples/state_regions.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/state_regions.py)

```bash
uv run python -m examples.state_regions
```

## Technologies

Technology keys, eras, categories, prerequisites, and map-update behavior.

<!-- table-preview: tables/technology.csv | columns=key,era,category,unlocking_technologies,should_update_map | rows=5 -->

[:material-download: Download `tables/technology.csv`](../tables/technology.csv)
· [:fontawesome-brands-github: View `examples/technology.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/technology.py)

```bash
uv run python -m examples.technology
```
