---
title: Parsing game data
description: Parse a Victoria 3 installation into pandas tables or work from the committed snapshots.
---

# Parsing game data

## Choose a data source

Use the committed CSVs when you want reproducible analysis or do not have a
local Victoria 3 installation. Use the parsers when you need data from your
currently installed game version.

=== "Committed snapshot"

    ```python
    import pandas as pd

    goods = pd.read_csv("tables/goods.csv")
    buildings = pd.read_csv("tables/buildings.csv")
    ```

    Every snapshot has a preview, download, and producing script in the
    [parsed-data showcase](../showcase/parsed-data.md).

=== "Installed game"

    ```python
    from vic3_analysis import BuildingsParser, goods

    goods_df = goods()
    buildings_df = BuildingsParser().to_dataframe()
    ```

    The package searches common Steam library locations on Windows, Linux, and
    macOS. Pass `game_dir="/path/to/Victoria 3/game"` if detection fails.

## Generate the tables

Each parser has a small script under `examples/`. Run a module from the project
root, for example:

```bash
uv run python -m examples.goods
uv run python -m examples.buildings
uv run python -m examples.production_analysis
```

!!! warning "Generated data follows your installed game version"

    Regenerating a CSV may change many rows when the installed Victoria 3
    version differs from the committed snapshot. Review those changes before
    replacing tracked data.

## Build the production table

`production_table()` combines buildings, goods, production methods, and
technology data into one row per building/production-method configuration. Its
`goods_<key>` columns use positive values for outputs and negative values for
inputs.

```python
from vic3_analysis import production_table

production = production_table()
print(production[["building", "production_method", "profit_nominal"]].head())
```

See the [parsing API](../api/parsing.md) for constructor parameters, return
values, and exceptions.
