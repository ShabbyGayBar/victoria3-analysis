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
- `.gitmodules` — Mounts the separately licensed artifact repository at
  `artifacts/`; the parent repository pins an exact artifact commit.
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
  (`production_table`, `Economy`, `EconomyContext`, `EconomyState`, `MarketState`,
  `PopState`), and the optimization API (`Scenario`,
  `BaseOptimizer`, `LinearProblem`, `NominalOptimizer`, `MarketProblem`,
  `MarketOptimizer`, `EquilibriumProblem`, and `EquilibriumOptimizer`).
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
- `economy/` — Economy model and frozen snapshot components. `__init__.py`
  preserves the public exports. `model.py` defines `Economy`, retaining its
  initialization, cached properties, and public delegating methods; private
  helpers are called directly from their calculation modules. Calculation
  functions live in `production.py` (coefficients, throughput, and resources),
  `consumption.py` (baskets, demand, and expenses), `income.py` (household
  earnings), `market.py` (prices and nominal/market solves), `equilibrium.py`
  (wealth evaluation, iteration, and equilibrium solves), and `reports.py`
  (DataFrame exports, including `df_goods_buy_packages()` for calculated goods
  baskets). `_utils.py` shares array ownership, index-key, worker-count,
  and goods validation helpers. Consumption calculations share array-based wealth
  grouping, basket selection, demand aggregation, and expense allocation with the
  equilibrium evaluator; final verification still uses the public calculators.
  `states.py` defines the snapshot components, diagnostics, errors, and immutable
  `GoodsBuyPackages` objects holding aligned wealth labels and goods quantities.
  Basket calculations and consumption inputs use `GoodsBuyPackages` throughout;
  raw parser tables remain DataFrames.
  `EconomyContext` owns fixed production, gross import and export orders, worker counts, workforce ratio,
  and optional prepared baskets/scales. `MarketState` references that context
  and owns prices, deriving building finances and GDP. `PopState` owns wealth,
  demand, and optional income/expenses, deriving balance when evaluated.
  `EconomyState` composes them, preserves flat attribute reads, and derives
  combined reports. `Economy` provides nominal/market/equilibrium solving,
  explicit preparation, fixed-wealth evaluation, and simultaneous one-tier
  iteration. Immutable `EquilibriumDiagnostics` records numerical outcomes
  and financial flags; `EquilibriumError` retains consistent failure snapshots.
- `supply_chain/` — Single-terminal nominal supply-chain analysis. The package
  separates analyzer/result orchestration, cyclic bipartite NetworkX graph
  construction, metrics, Matplotlib/Mermaid visualization, and sequential
  all-goods sweeps. `SupplyChainResult` exposes stable goods, process, flow,
  workforce, constraint, bottleneck, and alternative-producer tables while
  retaining exact process-level coproduct attribution. `Economy.producible_goods`
  lists goods with at least one producer configuration.
  The [supply-chain guide](guides/supply-chain.md#why-the-graph-uses-processes)
  explains the process/configuration terminology. The
  [design references](design/supply-chain.md) compare graphs, optimization,
  accounting, and coproduct treatment with Brightway, PyPSA, Calliope, pymrio,
  and openLCA.

### `src/vic3_analysis/optimize/` — Optimisation

- `scenario.py` — `Scenario`, a frozen dataclass that captures an
  optimisation recipe as data (goods-balance floor, fixed import/export orders, objective,
  banned PMs / buildings / building groups, per-building level caps, throughput
  multipliers, era / construction-cost / employment caps, minimum net
  infrastructure surplus, urban-center tie). It has no economy- or
  solver-dependent methods.
- `_orders.py` — Shared validation and goods-aligned aggregation of fixed
  import and export orders for optimizers and supply-chain helpers.
- `base.py` — public abstract `BaseOptimizer` plus immutable `LinearProblem`
  and `MarketProblem` compiled types. The base compiles fixed market context,
  throughput-adjusted matrices, shared constraints with named row slices,
  feasibility validation, and fixed-zero handling for the concrete optimizers.
- `nominal.py` — `NominalOptimizer.compile()` attaches the fixed-price linear
  objective; `solve()` and `solve_problem()` call HiGHS through
  `scipy.optimize.linprog`. `import_marginals()` maps LP duals through the
  compiled problem's named goods-balance constraint slice, returning
  goods-aligned objective sensitivities to additional imports.
- `market.py` — `MarketOptimizer.compile()` builds the nonlinear objective,
  Jacobian, linear feasible region, bounds, and nominal warm-start problem;
  `solve()` and `solve_problem()` use SLSQP for endogenous-price GDP or GDP per
  capita.
- `equilibrium.py` — immutable `EquilibriumProblem` freezes household solver
  controls and wealth seeds; `EquilibriumOptimizer` uses bounded COBYLA local
  search over building levels for GDP, GDP per capita, or average wealth.
  Trial equilibrium failures are counted and skipped. Hard evaluation budgets
  return the best feasible, freshly verified state with explicit search status.

## `examples/` — Artifact-generation Scripts

Standalone examples write into the separate `artifacts/` checkout. Shared
dataset and analysis paths are defined in `examples/__init__.py`; importing
them does not create output directories. Initialize the pinned submodule first:

```bash
git submodule update --init --recursive
```

Run `uv run python examples/parse.py`, then
`uv run python examples/production_analysis.py`, then the desired analysis
scripts. Parsed inputs are read from `artifacts/datasets/parsed/`; downstream
studies also read `artifacts/datasets/production/production_table.csv`.
The `buy_packages.py` example reads the game installation directly and needs
no previously generated tables.

| Script | Output collection relative to `artifacts/` |
|---|---|
| `parse.py` | `datasets/parsed/*.csv`; `datasets/parsed/buy_packages/buy_packages.csv` and `figures/*.svg` within that buy-package collection |
| `production_analysis.py` | `datasets/production/production_table.csv` |
| `buy_packages.py` | `analyses/buy_packages/default.csv`: goods packages per 10,000 standard workers at every wealth tier, using a state with zero building levels |
| `optimize_jap.py` | `analyses/optimization/japan/employment_sweep.csv` |
| `optimize_equilibrium.py` | `analyses/optimization/equilibrium/`: best verified average-wealth solution in `buildings.csv`, `market.csv`, `pop.csv`, and `goods_buy_packages.csv`; iteration history and run metadata in `summary.csv`. Profitability-based restarts use a fresh `--max-evaluations` budget, with optional `--max-iterations`, `--loss-reduction`, and `--resume` controls. |
| `supply_chain_compare.py` | `analyses/supply_chains/<configuration>/<good>/` reports, plots, and diagrams; each configuration's `summary.csv`; combined `comparison/summary.csv` with `pop.svg`, `construction_points.svg`, and `gdp_per_capita.svg` grouped by good and configuration |
| `supply_chain_cangshulun.py` | `analyses/supply_chains/cangshulun_video/summary.csv`, containing all goods and variants |

## `artifacts/` — Separate Artifact Repository

This path is a Git submodule pinned to an exact artifact-repository commit.
Recursive clones reproduce the documented snapshot; updates to the pointer are
reviewed and committed manually in the parent repository. The artifact
repository and its contents are outside the main repository's GPL grant.

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
  (`solve` returns a state satisfying goods-balance / building-level-cap /
  urbanization constraints, unbounded and infeasible scenarios raise, the
  retained problem/result/scenario state, cross-economy rejection, and import
  marginals after solve).
- `test_market_optimizer.py` — exercises nonlinear market compilation,
  fixed-zero bounds, warm starts, objective/Jacobian behavior, solve entry
  points, market validation, and cross-economy rejection.
- `test_equilibrium_optimizer.py` — synthetic objective, accounting, constraint,
  fixed-seed, failure-recovery, budget, and validation tests, plus a full vanilla
  production-table integration test with a small hard evaluation budget.
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
- `design/` — Design notes with an index, color-coded economy calculation
  dependencies and storage owners, and supply-chain architectural references.
- `hooks.py` — Adds artifact-checkout collections to the site and expands CSV
  preview directives during builds.
- `stylesheets/extra.css` — Responsive gallery and table-preview styling, plus
  light/dark storage-owner colors for the economy dependency diagrams.
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
  submodule recursively at the commit pinned by the parent repository, installs
  development dependencies, checks types and documentation coverage, and builds
  and publishes the documentation site.

### Supply-chain equilibrium optimization

`optimize/supply_chain.py` adds `SupplyChainEquilibriumProblem` and
`SupplyChainEquilibriumOptimizer` as public exports. The optimizer validates
building-level DataFrames and snapshots coefficients that map chain levels
to building configurations. Compiled problems retain immutable mappings;
the optimizer transforms scenario constraints and reuses the existing
equilibrium search and physical solver.

`examples/optimize_supply_chain_equilibrium.py` directly loads the hard-coded
chains from trusted `era_5_automation/building_levels.csv`, filters unused
production units, and passes the labeled DataFrame to the optimizer. It derives
target metadata from the £100,000 target and goods base prices without reading
the source summary, and writes a separate
`analyses/optimization/supply_chain_equilibrium/` collection containing
`chain_matrix.csv`, `chains.csv`, `buildings.csv`, `market.csv`, `pop.csv`,
`goods_buy_packages.csv`, and `summary.csv`.
It repeats local searches, reducing loss-making terminal producers' chain
levels before each restart, until verified GDP decreases or an optional
`--max-iterations` cap is reached. Each search receives its own trial budget;
equal GDP continues iteration. Solution reports contain only the best retained
state, including the re-evaluated saved baseline when resuming. The summary
records each local search, a resume baseline row, and invocation totals.
