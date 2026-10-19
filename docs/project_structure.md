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
  and `[tool.pyright]` (standard mode, covering `src`, `tests`, `examples`, and
  `docs/hooks.py`).
- `uv.lock` — Lockfile for the `uv` toolchain, pinning transitive dependencies.
- `.python-version` — Pins the project Python version (3.13) for `uv`/`pyenv`.
- `mkdocs.yml` — MkDocs Material configuration. Builds the API reference from
  docstrings via `mkdocstrings` (Google style) and wires up the `usage/` and
  `api.md` nav. Watched paths include `src/vic3_analysis` for live reload.
- `LICENSE` — GNU General Public License version 3 text for original project
  material licensed under GPL-3.0-or-later.
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
  (`production_table`, `Economy`), and the optimization API (`Scenario`,
  `BaseOptimizer`, `LinearProblem`, `NominalOptimizer`, `MarketProblem`, and
  `MarketOptimizer`).
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
  columns. `state_region_resource_limits()` and
  `state_region_arable_land_limit()` aggregate selected rows into caps suitable
  for `Scenario`.

### `src/vic3_analysis/analysis/` — Economic Analysis

- `production.py` — Production-chain modelling:
  - `ProductionUnit` — dict-like snapshot of one building level's goods flows,
    employment, and era; supports `+` aggregation, `profit()`, and
    `profit_per_employment()`.
  - `production_table(df_buildings, df_goods, df_pm, df_tech=None,
    df_pop_types=None)` — enumerates every building configuration (one
    production method per group) and returns a DataFrame with building/group
    lineage, land and resource flags, production methods, construction cost,
    profit, employment, per-profession employment, and `goods_<good>` columns.
    Optional technology and pop-type tables add era/localization and
    private-wage-normalized metrics, respectively.
- `economy.py` — General-equilibrium economy model. Defines `EconomyState`
  (frozen dataclass with building levels, prices, supply, demand, employment,
  and wealth) and `Economy` which derives a nominal `EconomyState` from a
  building-level vector using base goods prices and per-profession wealth from
  the pop-types table.
- `supply_chain/` — Single-terminal nominal supply-chain analysis. The package
  separates analyzer/result orchestration, cyclic bipartite NetworkX graph
  construction, metrics, Matplotlib/Mermaid visualization, and sequential
  all-goods sweeps. `SupplyChainResult` exposes stable goods, process, flow,
  workforce, constraint, bottleneck, and alternative-producer tables while
  retaining exact process-level coproduct attribution. `Economy.producible_goods`
  lists goods with at least one producer configuration.
  The [supply-chain guide](guides/supply-chain.md#why-the-graph-uses-processes)
  explains the process/configuration terminology. The
  [design references](supply-chain-design.md) compare graphs, optimization,
  accounting, and coproduct treatment with Brightway, PyPSA, Calliope, pymrio,
  and openLCA.

### `src/vic3_analysis/optimize/` — Optimisation

- `scenario.py` — `Scenario`, a frozen dataclass that captures an
  optimisation recipe as data (produce basket, objective, import limit, banned
  PMs / buildings / building groups, per-building level limits, throughput
  bonuses, era / construction-cost / employment caps, infrastructure floor,
  urban-center tie). It has no economy- or solver-dependent methods.
- `base.py` — public abstract `BaseOptimizer` plus immutable `LinearProblem`
  and `MarketProblem` compiled types. The base compiles fixed market context,
  throughput-adjusted matrices, shared constraints with named row slices, and
  solution-state context for both concrete optimizers.
- `nominal.py` — `NominalOptimizer.compile()` attaches the fixed-price linear
  objective; `solve()` and `solve_problem()` call HiGHS through
  `scipy.optimize.linprog`. `import_marginals()` maps LP duals through the
  compiled problem's named import constraint slice.
- `market.py` — `MarketOptimizer.compile()` builds the nonlinear objective,
  Jacobian, linear feasible region, bounds, and nominal warm-start problem;
  `solve()` and `solve_problem()` use SLSQP for endogenous-price GDP or GDP per
  capita.

## `examples/` — Artifact-generation Scripts

Standalone examples write into the separate `artifacts/` checkout. Shared
dataset and analysis paths are defined in `examples/__init__.py`; importing
them does not create output directories. Clone the artifact repository first:

```bash
git clone https://github.com/ShabbyGayBar/victoria3-analysis-artifacts.git artifacts
```

Run `uv run python examples/parse.py`, then
`uv run python examples/production_analysis.py`, then the desired analysis
scripts. Parsed inputs are read from `artifacts/datasets/parsed/`; downstream
studies also read `artifacts/datasets/production/production_table.csv`.

| Script | Output collection relative to `artifacts/` |
|---|---|
| `parse.py` | `datasets/parsed/*.csv`; `datasets/parsed/buy_packages/buy_packages.csv` and `figures/*.svg` within that buy-package collection |
| `production_analysis.py` | `datasets/production/production_table.csv` |
| `optimize_jap.py` | `analyses/optimization/japan/employment_sweep.csv` |
| `supply_chain_trace.py` | `analyses/supply_chains/automobiles/` scenario comparison and sensitivity, with `minimum_employment/` baseline reports and plots and `capital_budget/` diagnostics; optional `all_goods/era_5_automation/summary.csv` and `failures.csv` |
| `supply_chain_compare.py` | `analyses/supply_chains/all_goods/scenario_comparison.csv` |
| `supply_chain_cangshulun.py` | `analyses/supply_chains/cangshulun/supply_chain_cangshulun.csv` |
| `supply_chain_market_automobiles.py` | Prints automobile market metrics |

## `artifacts/` — Separate Artifact Repository

- `datasets/parsed/` contains parsed game datasets. Supporting visualizations
  stay with their dataset: the buy-package collection contains its CSV and
  a local `figures/` directory.
- `datasets/production/` contains the reusable production-configuration table.
- `analyses/` groups study-specific tables, plots, and diagrams by subject and
  scenario, with shared input datasets referenced from `datasets/`.

There are no main-repository table or figure snapshots. The showcase, tests,
and MkDocs hooks consume only the new artifact collection paths. These paths
must be populated by the generation scripts before snapshot checks and the
complete documentation build can pass; old artifact paths are not fallbacks.
Generated collections retain their repository-relative `artifacts/` prefix
when published on the documentation site.

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
- `test_scenario.py` — exercises the immutable `Scenario` configuration
  (defaults, objective validation, frozen behavior, and display names).
- `test_base.py` — exercises shared optimizer compilation (context vectors,
  throughput-adjusted matrices, constraint families and named row slices),
  lifecycle bookkeeping, and pre-compilation access guards.
- `test_nominal_optimizer.py` — exercises `NominalOptimizer` compilation and solving
  (`solve` returns a state satisfying produce / import / building-limit /
  urbanization constraints, unbounded and infeasible scenarios raise, the
  retained problem/result/scenario state, cross-economy rejection, and import
  marginals after solve).
- `test_market_optimizer.py` — exercises nonlinear market compilation,
  fixed-zero bounds, warm starts, objective/Jacobian behavior, solve entry
  points, market validation, and cross-economy rejection.
- `test_supply_chain.py` — uses a synthetic economy to exercise analyzer
  validation, immutable results, cyclic realized/allowed graphs, exact flows,
  coproduct attribution, resource metadata, constraints, Mermaid/Matplotlib
  rendering, and continue-on-error all-goods sweeps.

## `docs/` — MkDocs Documentation

Source for the MkDocs Material site (`uv run mkdocs serve`).

- `index.md` — Purpose-built landing page with separate paths for Python users
  and readers browsing generated results.
- `api/` — Public API reference grouped into parsing, economy, optimization,
  and supply-chain pages and rendered from source docstrings by `mkdocstrings`.
- `guides/` — Getting started tutorial (`getting-started.md`) for package setup
  and next steps, followed by
  task-focused parsing, economy modeling, optimization, and supply-chain
  explanations. Economy modeling and optimization have separate guide pages.
- `showcase/` — Curated previews and downloads for every tracked table and
  figure, plus the artifact-to-example registry used by documentation tests.
- `hooks.py` — Adds artifact-checkout collections to the site and expands CSV
  preview directives during builds.
- `stylesheets/extra.css` — Responsive gallery and table-preview styling.
- `license.md` — License page.
- `project_structure.md` — This document.
- `roadmap.md` — Roadmap placeholder (currently empty; see `AGENTS.md` for
  priority guidance).

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

- `deploy-docs.yml` — On push to `master`/`main`, checks out the artifact
  repository into `artifacts/`, installs development dependencies, checks types
  and documentation coverage, and builds and publishes the documentation site.
