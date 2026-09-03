# Project Structure

This document describes the layout of the `victoria3-analysis` repository, the
purpose of each directory, and the key modules/files within them.

## Top-level Files

- `AGENTS.md` — Mandatory instructions for AI coding agents: setup, commands,
  external file-loading protocol, and development rules. Referenced by
  opencode as the entry point for agent behaviour.
- `pyproject.toml` — Project metadata and tool configuration. Declares the
  `vic3-analysis` package, requires Python `>=3.13`, and pins runtime
  dependencies (`numpy`, `pandas`,   `pillow`, `pyradox-txt-parser`, `scipy`, `matplotlib`) and
  dev dependencies (`mkdocs-material`, `mkdocstrings[python]`, `pytest`,
  `pytest-cov`, `ruff`, `pyright`). Configures pytest test paths and coverage,
  and `[tool.pyright]` (basic mode, covering `src` and `tests`).
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
  `BuildingsParser`, `BuildingGroupParser`, `goods`, `PopNeedsParser`,
  `PopTypesParser`, `production_method_groups`, `ProductionMethodParser`,
  `StateRegionsParser`, `technology`), the analysis helpers
  (`production_table`, `Economy`), and the optimiser (`NominalOptimizer`).
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
  `building_groups()`. `to_dataframe()` also joins resolved building-group
  attributes (from :mod:`building_groups`) onto each building row.
- `building_groups.py` — `BuildingGroupParser` (`Tree` subclass). Loads
  `common/building_groups`. `to_dataframe()` flattens each group's scalar
  attributes; `resolved_attributes()` returns per-group attribute dicts with
  `land_usage` and `cash_reserves_max` resolved along the `parent_group`
  chain. The module-level `_join_group_attrs()` helper merges resolved group
  attributes onto building row dicts (collision-prefixed as needed).
- `goods.py` — `goods()` function. Loads `common/goods` into a DataFrame with
  one row per tradeable good (`key`, `cost`, etc.).
- `production_methods.py` — `ProductionMethodParser` (`Tree` subclass). Loads
  `common/production_methods`. `employment()` returns per-method total and
  per-profession employment from `level_scaled` modifiers; `state_modifiers()`
  returns per-method state modifiers flattened across the
  `state_modifiers` scaling blocks; `to_dataframe()` builds a flat
  per-configuration table combining building and production-method-group data
  with employment, net goods-flow and state-modifier columns.
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

- `production.py` — Production-chain modelling:
  - `ProductionUnit` — dict-like snapshot of one building level's goods flows,
    employment, and era; supports `+` aggregation, `profit()`, and
    `profit_per_employment()`.
  - `production_table(game_dir=None)` — enumerates every building
    configuration (one production method per group) and returns a DataFrame
    with `building`, `production_method`, `building_group`, `era`,
    `construction_cost`, `profit`, `employment`, per-profession employment,
    and `goods_<good>` columns.
- `economy.py` — General-equilibrium economy model. Defines `EconomyState`
  (frozen dataclass with building levels, prices, supply, demand, employment,
  and wealth) and `Economy` which derives a nominal `EconomyState` from a
  building-level vector using base goods prices and per-profession wealth from
  the pop-types table.
- `supply_chain.py` — Supply-chain analysis on the nominal economy. Provides
  the `SupplyChainNode` / `ProducerNode` dependency-graph dataclasses (with
  `iter_producers()`, `collect_producers()`, `collect_good_nodes()`,
  `chain_depth()`, `count_raw_inputs()`, and `to_mermaid()` methods), and
  composable functions: `optimize_chain` (solve a `Scenario` via
  `NominalOptimizer`), `upstream_tree` (memoised recipe/realised trace, with
  an optional `scenario` for throughput-adjusted flows),
  `value_added_breakdown` (per-config or per-good GDP/employment/
  construction-cost attribution, likewise `scenario`-aware), `bottleneck`
  (input cost-share ranking plus LP import-cap marginals read from the solved
  scenario), and `compare_scenarios` (multi-scenario metric table with chain
  characteristics). `Economy.producible_goods()` lists goods with at least one
  producer configuration.

### `src/vic3_analysis/optimize/` — Optimisation

- `scenario.py` — `Scenario`, a frozen dataclass that captures an
  optimisation recipe as data (produce basket, objective, import limit, banned
  PMs / buildings / building groups, per-building level limits, throughput
  bonuses, era / construction-cost / employment caps, infrastructure floor,
  urban-center tie). Its economy-parameterised translation methods are pure
  and deterministic: `goods_input_matrix` / `goods_output_matrix` /
  `goods_matrix` (throughput-adjusted flows), `gdp_vector`,
  `objective_vector`, `inequality_constraints` / `equality_constraints`
  (stacked linprog-ready `(A, b)` arrays in fixed block order, `None` when
  absent), `linprog_args` (the bundled `c` / `A_ub` / `b_ub` / `A_eq` / `b_eq`
  keyword `LinprogArgs` TypedDict for `scipy.optimize.linprog`), and
  `import_marginals` (interprets its own duals from a solved LP result).
- `nominal.py` — `NominalOptimizer`, solely a solver: `solve(scenario)`
  delegates to `scipy.optimize.linprog` with the scenario's `linprog_args`,
  returning an `EconomyState`. The underlying `OptimizeResult` and the solved
  scenario are retained on the `result` / `scenario` attributes so downstream
  tooling (e.g. `supply_chain.bottleneck`) can read constraint marginals
  (shadow prices).

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

- `supply_chain_optimize.py`, `supply_chain_trace.py`,
  `supply_chain_compare.py` — supply-chain analysis demos built on the
  `vic3_analysis.analysis.supply_chain` module: scenario-based optimisation
  (reproduces the historical `cangshulun_1` recipe via `Scenario` — the
  original `cangshulun_1.py` / `cangshulun_2.py` scripts were removed once the
  recipe became a `Scenario`), recipe/realised upstream tracing (writes
  Mermaid `.mmd` files), and a full sweep of all producible terminal goods
  with normalised target value and `construction_cost` objective (writes
  `tables/supply_chain_sweep.csv` and summary charts). The optimisation and
  comparison scripts also generate matplotlib bar charts saved as PNGs.
  Runnable as `__main__` scripts; not collected by pytest.

## `tables/` — Generated CSV Output

Committed CSV exports produced by the `examples/` scripts. Consumed by the
documentation (`docs/usage/parse.md` links to them on GitHub) and usable for
downstream analysis without a local game install. The flagship
`production_table.csv` feeds the optimisation workflow.
`supply_chain_sweep.csv` contains the full terminal-good sweep results.

## `figures/` — Generated Visualisation Output

Committed visualisation artefacts produced by the `examples/` scripts.
Includes Mermaid flowchart files (`.mmd`) from `supply_chain_trace.py` and
matplotlib PNG charts from `supply_chain_optimize.py` (building levels, net
goods, value-added by good, bottleneck) and `supply_chain_sweep.py`
(construction cost and GDP efficiency by terminal good). Tracked in git so
the docs and readme can reference them without a local game install.

## `tests/` — Test Suite

Run with `uv run pytest` (coverage enforced via `pyproject.toml`).
Requires a local Victoria 3 installation because the parsers auto-detect the
game directory.

- `__init__.py` — empty package marker.
- `test_buildings.py`, `test_building_groups.py`, `test_goods.py`, `test_production_method.py`,
  `test_production_method_groups.py`, `test_technology.py`,
  `test_buy_packages.py`, `test_pop_types.py`, `test_state_regions.py` —
  smoke tests that instantiate each parser and call its primary method.
- `test_economy.py` — exercises `Economy` and `EconomyState` end-to-end
  (matrices, derived vectors, solve, DataFrames, GDP/wealth).
- `test_scenario.py` — exercises the `Scenario` formulation (objective
  validation, throughput-adjusted matrices, objective-vector signs, constraint
  order and content per field, `import_marginals` guards).
- `test_nominal_optimizer.py` — exercises the solver-only `NominalOptimizer`
  (`solve` returns a state satisfying produce / import / building-limit /
  urbanization constraints, unbounded and infeasible scenarios raise, the
  `result` / `scenario` attributes, marginal access after solve).
- `test_supply_chain.py` — exercises the supply-chain toolkit end-to-end
  (`optimize_chain`, `upstream_tree` recipe/realised/bonus-consistent views,
  Mermaid serialisation, chain metrics, `value_added_breakdown`,
  `bottleneck`, `compare_scenarios`, `producible_goods`).

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
  `NominalOptimizer`, including the objective-vector / constraint model and
  a worked steel example.

## `agents/` — Agent Instructions

- `rules/python.md` — Mandatory Python rules for agents: type safety (no
  `# type: ignore`, `cast()`, or `Any`), `assert`-based narrowing for untyped
  `pyradox`, exclusive use of `uv`, pyradox usage and `Tree` API reference,
  and serialisation conventions. Loaded on demand per `AGENTS.md`.
- `rules/tests.md` — Mandatory test conventions for agents: location/naming,
  toolchain (`uv run pytest`, `ruff`, `pyright`), imports, game-data fixtures,
  function-based style, and the 100% coverage target. Loaded on demand per
  `AGENTS.md`.

## `.vscode/` — Editor Configuration

- `settings.json` — Enables pytest as the test runner with `tests` as the
  argument root.
- `launch.json` — "Python Debugger: Current File" configuration for running
  the active script in the integrated terminal.

## `.github/workflows/` — CI

- `ci.yml` — On push to `master`/`main`, installs the `dev` dependency group
  and runs `mkdocs gh-deploy --force` to publish the documentation site.
