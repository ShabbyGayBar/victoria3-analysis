# Project Structure

This document describes the layout of the `victoria3-analysis` repository, the
purpose of each directory, and the key modules/files within them.

## Top-level Files

- `AGENTS.md` — Mandatory instructions for AI coding agents: setup, commands,
  external file-loading protocol, and development rules. Referenced by
  opencode as the entry point for agent behaviour.
- `pyproject.toml` — Project metadata and tool configuration. Declares the
  `vic3-analysis` package, requires Python `>=3.13`, and pins runtime
  dependencies (`numpy`, `pandas`, `pillow`, `pyradox-txt-parser`, `scipy`) and
  dev dependencies (`mkdocs-material`, `mkdocstrings[python]`, `pytest`,
  `pytest-cov`, `ruff`). Configures pytest test paths and coverage.
- `uv.lock` — Lockfile for the `uv` toolchain, pinning transitive dependencies.
- `.python-version` — Pins the project Python version (3.13) for `uv`/`pyenv`.
- `mkdocs.yml` — MkDocs Material configuration. Builds the API reference from
  docstrings via `mkdocstrings` (Google style) and wires up the `usage/` and
  `api.md` nav. Watched paths include `src/vic3_analysis` for live reload.
- `LICENSE` — MIT license.
- `README.md` — Project overview, features, and install instructions. Included
  verbatim on the docs home page via `docs/index.md`.
- `.gitattribute` / `.gitignore` — Git metadata and ignore rules.

## `src/vic3_analysis/` — Package Source

The importable `vic3_analysis` package. All public symbols are re-exported from
`__init__.py`, so users can do `from vic3_analysis import BuildingsParser,
production_table, ...` directly.

- `__init__.py` — Re-exports the public API: `get_vic3_directory`,
  `parse_merge` (from `utils`), the parsers (`buy_packages`,
  `BuildingsParser`, `goods`, `PopTypesParser`, `production_method_groups`,
  `ProductionMethodParser`, `StateRegionsParser`, `technology`), and the
  analysis helpers (`production_table`, `ProductionAnalyzer`).
- `utils.py` — Shared helpers:
  - `get_vic3_directory()` auto-detects the `Victoria 3/game` install across
    common Steam library paths on Windows/Linux/macOS.
  - `parse_merge(path, merge_levels=0)` reads all `.txt` files in a directory
    (UTF-8-SIG), neutralises `?=`/`!=` strings that pyradox would misread as
    merge directives, and merges them into a single `pyradox.Tree`.

### `src/vic3_analysis/parse/` — Game Data Parsers

Each parser reads from a specific `common/` (or `map_data/`) subdirectory of
the Victoria 3 game files. Parsers either return a `pandas.DataFrame` directly
or expose a `pyradox.Tree` subclass with helper methods.

- `buildings.py` — `BuildingsParser` (`Tree` subclass). Loads
  `common/buildings`, resolves `required_construction` script values from
  `common/script_values` into numeric `required_construction_points`, and
  provides `to_dataframe()`, `production_method_groups()`, and
  `building_groups()`.
- `goods.py` — `goods()` function. Loads `common/goods` into a DataFrame with
  one row per tradeable good (`key`, `cost`, etc.).
- `production_methods.py` — `ProductionMethodParser` (`Tree` subclass). Loads
  `common/production_methods`. `employment()` returns per-method total and
  per-profession employment from `level_scaled` modifiers; `to_dataframe()`
  builds a flat per-configuration table combining building and
  production-method-group data with employment and net goods-flow columns.
- `production_method_groups.py` — `production_method_groups()` function. Loads
  `common/production_method_groups` into a dict mapping each group key to its
  ordered list of production-method keys.
- `technology.py` — `technology()` function. Loads
  `common/technology/technologies` into a DataFrame; parses `era_N` strings
  into integer eras and skips non-analytical keys.
- `buy_packages.py` — `buy_packages()` function. Parses
  `common/buy_packages/00_buy_packages.txt` into a DataFrame with one row per
  wealth level (`wealth`, `political_strength`, one `popneed_*` column per
  good, missing values zero-filled).
- `pop_types.py` — `PopTypesParser` (`Tree` subclass). Loads
  `common/pop_types`. Provides `to_dataframe()` and `flags()` (boolean
  attributes grouped by pop type).
- `state_regions.py` — `StateRegionsParser` (`Tree` subclass). Loads
  `map_data/state_regions`. `to_dataframe()` flattens scalar attributes and
  expands `resource`/`capped_resources` into `resource_*`,
  `undiscovered_amount_resource_*`, and `discovered_amount_resource_*`
  columns.

### `src/vic3_analysis/analysis/` — Economic Analysis

- `production.py` — Production-chain modelling and linear-programming
  optimisation:
  - `ProductionUnit` — dict-like snapshot of one building level's goods flows,
    employment, and era; supports `+` aggregation, `profit()`, and
    `profit_per_employment()`.
  - `production_table(game_dir=None)` — enumerates every building
    configuration (one production method per group) and returns a DataFrame
    with `building`, `production_method`, `building_group`, `era`,
    `construction_cost`, `profit`, `employment`, per-profession employment,
    and `goods_<good>` columns.
  - `ProductionAnalyzer` — wraps a production table and exposes
    `*_vector()` accessors (profit, employment, construction cost, era),
    filter methods (`filter_by_era`, `filter_by_building_group`,
    `filter_by_production_method`, `restore`), throughput bonuses
    (`add_throughput_bonus`), constraint builders (`constraint_limit_import`,
    `constraint_limit_employment`, `constraint_limit_construction_cost`,
    `constraint_limit_building`, `constraint_produce`), and `linprog()` for
    solving the LP via `scipy.optimize.linprog`.
  - `OptimizeResult` — structured optimisation result with `gdp`,
    `gdp_per_capita()`, and `level_to_df()` / `net_goods_to_df()` exports.
- `economy.py` — Work-in-progress general-equilibrium scaffold. Defines the
  `Economy` dataclass and a placeholder `EconomyModel` with a `_solve_nominal`
  stub returning random values. Not yet wired into the public API.

## `examples/` — Table-generation Scripts

Standalone scripts that exercise the parsers and write CSVs into `tables/`.
`__init__.py` defines `THIS_DIR` so each script can resolve the output path.
The script name maps 1:1 to the output table:

| Script | Output |
|---|---|
| `buildings.py` | `tables/buildings.csv` |
| `goods.py` | `tables/goods.csv` |
| `production_method.py` | `tables/production_methods.csv` |
| `production_analysis.py` | `tables/production_table.csv` |
| `technology.py` | `tables/technology.csv` |
| `state_regions.py` | `tables/state_regions.csv` |
| `buy_packages.py` | `tables/buy_packages.csv` |
| `pop_types.py` | `tables/pop_types.csv` |

Run any script with `uv run python -m examples.<name>` or directly. They are
the canonical "how do I use this package" reference for non-developers.

## `tables/` — Generated CSV Output

Committed CSV exports produced by the `examples/` scripts. Consumed by the
documentation (`docs/usage/parse.md` links to them on GitHub) and usable for
downstream analysis without a local game install. The flagship
`production_table.csv` feeds the optimisation workflow.

## `tests/` — Test Suite

Run with `uv run pytest` (coverage enforced via `pyproject.toml`).
Requires a local Victoria 3 installation because the parsers auto-detect the
game directory.

- `__init__.py` — empty package marker.
- `test_buildings.py`, `test_goods.py`, `test_production_method.py`,
  `test_production_method_groups.py`, `test_technology.py`,
  `test_buy_packages.py`, `test_pop_types.py`, `test_state_regions.py` —
  smoke tests that instantiate each parser and call its primary method.
- `test_production_analysis.py` — exercises `ProductionAnalyzer` end-to-end
  (vectors, finders, constraints, and `linprog`).
- `cangshulun_1.py`, `cangshulun_2.py` — optimisation scenario scripts
  ("仓鼠轮" experiments) exploring minimum-population and throughput-bonus
  production strategies. Runnable as `__main__` scripts; not collected by
  pytest's `test_*` pattern.

## `docs/` — MkDocs Documentation

Source for the MkDocs Material site (`uv run mkdocs serve`).

- `index.md` — Home page; embeds `README.md` via a snippet include.
- `api.md` — Auto-generated API reference rendered by `mkdocstrings` from the
  package docstrings (`# ::: vic3_analysis`).
- `license.md` — License page.
- `project_structure.md` — This document.
- `roadmap.md` — Roadmap placeholder (currently empty; see `AGENTS.md` for
  priority guidance).
- `usage/parse.md` — Guide to the pre-generated `tables/*.csv` and how to run
  the `examples/` scripts.
- `usage/analysis.md` — Guide to production optimisation with
  `ProductionAnalyzer`, including the objective-vector / constraint model and
  a worked steel example.

## `agents/` — Agent Instructions

- `rules/python.md` — Mandatory Python rules for agents: type safety (no
  `# type: ignore`, `cast()`, or `Any`), `assert`-based narrowing for untyped
  `pyradox`, exclusive use of `uv`, pyradox usage and `Tree` API reference,
  and serialisation conventions. Loaded on demand per `AGENTS.md`.

## `.vscode/` — Editor Configuration

- `settings.json` — Enables pytest as the test runner with `tests` as the
  argument root.
- `launch.json` — "Python Debugger: Current File" configuration for running
  the active script in the integrated terminal.

## `.github/workflows/` — CI

- `ci.yml` — On push to `master`/`main`, installs the `dev` dependency group
  and runs `mkdocs gh-deploy --force` to publish the documentation site.
