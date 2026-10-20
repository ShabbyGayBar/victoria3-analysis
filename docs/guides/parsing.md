---
title: Parsing game data
description: Generate game-data tables and use individual Victoria 3 parsers in Python.
---

# Parsing game data

For column meanings, units, and defaults, see the
[parser dictionary](../data-dictionary/parsers.md) and the complete
[production-table dictionary](../data-dictionary/production.md).

## Generate the tables

Run the comprehensive `examples/parse.py` script from the project root to
generate all parsed game tables and the buy-package charts:

```bash
uv run python -m examples.parse
```

You can also run it directly with `uv run examples/parse.py`. Outputs
write to `artifacts/datasets/parsed/`. The buy-package CSV is stored at
`artifacts/datasets/parsed/buy_packages/buy_packages.csv`, with its linear and
log-scale charts in the adjacent `figures/` directory. These charts are views
of the parsed dataset.

Initialize the pinned artifact submodule before running the examples:

```bash
git submodule update --init --recursive
```

Regenerate in dependency order: run `examples/parse.py` first, then
`examples/production_analysis.py`, then the desired analysis scripts. Existing
files at old artifact paths are not used as fallback inputs.

!!! warning "Generated data follows your installed game version"

    Regenerating a CSV may change many rows when the installed Victoria 3
    version differs from the committed snapshot. Review those changes before
    replacing tracked data.

### Use individual parsers

Call individual parsers when you need tables in memory for a Python analysis.
The package searches common Steam library locations on Windows, Linux, and
macOS. If detection fails, pass `game_dir="/path/to/Victoria 3/game"` to the
parser constructor or function.

For example, `BuildingsParser` exposes `to_dataframe()`, while `goods()`
returns a DataFrame directly:

```python
from vic3_analysis import BuildingsParser, goods

buildings_df = BuildingsParser().to_dataframe()
goods_df = goods()

print(buildings_df.head())
print(goods_df.head())
```

For other parsers and their parameters, see the
[parsing API reference](../api/parsing.md).

## Build the production table

The production table remains a separate step using the generated CSVs:

```bash
uv run examples/production_analysis.py
```

`production_table()` iterates through every possible building and production method combination, then analyzes the resulting goods flows, employment, and other metrics. For further explanation of the columns, see the [production-table dictionary](../data-dictionary/production.md).

The above script reads `artifacts/datasets/parsed/` and writes
`artifacts/datasets/production/production_table.csv`. You can also build the production table directly from the parsers:

```python
from vic3_analysis import (
    BuildingsParser,
    PopTypesParser,
    ProductionMethodParser,
    goods,
    production_table,
    technology,
)

df_production = production_table(
    BuildingsParser().to_dataframe(),
    goods(),
    ProductionMethodParser().to_dataframe(),
    technology(),
    PopTypesParser().to_dataframe(),
)
df_production.to_csv("production_table.csv", index=False)
```

The technology and pop-types tables are optional enrichments. Without the
technology table, `production_table()` keeps the raw `unlocking_tech` keys but
omits `era` and `unlocking_tech_localization`. Without the pop-types table, it
omits `wage_normalized_employment` and
`profit_per_wage_normalized_employment_nominal`. For example, a base table needs
only the first three inputs:

```python
df_production = production_table(buildings_df, goods_df, production_methods_df)
```

To add wage-normalized metrics without technology enrichment, pass pop types by
keyword:

```python
df_production = production_table(
    buildings_df,
    goods_df,
    production_methods_df,
    df_pop_types=pop_types_df,
)
```

## Add localization

Localization is opt-in. Pass Victoria 3's internal language name to a parser to
add a nullable localization column beside each identifier, while retaining the
original script keys for joins and analysis:

```python
from vic3_analysis import BuildingsParser, goods

goods_df = goods(language="english")
buildings_df = BuildingsParser().to_dataframe(language="english")
```

The localized values are the raw strings from the game files: references,
formatting, icons, and localization functions are preserved. Missing entries
are `pd.NA`; no fallback language is applied. Use `localization("english")`
for the complete catalog, including related keys such as technology/building
descriptions and lens-option suffixes.

`production_table()` propagates localization columns when its input tables
contain them. `Economy(language="english")` applies the same option only to
tables it parses internally; explicitly supplied DataFrames remain unchanged.
Localization does not change the default no-language behavior.

See the [parsing API](../api/parsing.md) for constructor parameters, return
values, and exceptions.
