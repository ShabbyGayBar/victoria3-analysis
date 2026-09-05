# Roadmap

> Ultimate goal (`AGENTS.md`): parse Victoria 3 game data into structured
> formats, simulate the economy mechanics, and provide a tool for optimising
> production chains.

## Project foundation & parsing layer

- [x] Initial scaffolding:
  - [x] `uv` toolchain
  - [x] `pyproject.toml`
  - [x] MkDocs Material docs
  - [x] GitHub Actions CI
  - [x] `examples/` scripts
  - [x] `tests/` suite
- Core parsers:
  - [x] `common/buildings`
  - [x] `common/building_groups`
  - [x] `common/goods`
  - [x] `common/production_methods`
  - [x] `common/production_method_groups`
  - [x] `common/technology`
  - [x] `common/buy_packages`
  - [x] `common/pop_needs`
  - [x] `map_data/state_regions`.
- [x] `parse_merge` utility: UTF-8-SIG read, `?=`/`!=` neutralisation, multi-file
  merge into a `pyradox.Tree`.
- [x] `get_vic3_directory()` auto-detection across Steam library paths on
  Windows / Linux / macOS.

## Production optimisation (LP-based)

- [x] `ProductionUnit`, `production_table()` for production-chain modelling.
- [x] `Economy`, `EconomyState` for general-equilibrium economy modelling.
- [x] `NominalOptimizer` for `scipy.optimize.linprog` optimisation over
  building levels with named objectives, throughput bonuses, and fluent
  constraint builders.
- [x] Architecture refactor: all problem definition moved from
  `NominalOptimizer` (fluent constraint builders deleted) to the `Scenario`
  formulation in `optimize/scenario.py` — a frozen dataclass with pure,
  economy-parameterised translation methods (throughput-adjusted matrices,
  objective vectors, constraints in fixed order, `import_marginals`).
  `NominalOptimizer` is now solely a solver (`solve(scenario)`), retaining
  `result` / `scenario` from the last solve for duals. This removes the
  bonus/objective ordering trap and makes flows bonus-consistent across the
  analysis functions.

## Documentation & agent infrastructure

- [x] MkDocs Material site with auto-generated API reference (`mkdocstrings`) and
  `usage/parse.md`, `usage/analysis.md` guides.
- [x] `AGENTS.md` agent instructions with external file-loading protocol.
- [x] `docs/project_structure.md` per-folder map.

## Vanilla sync cadence

- Adapted `tables/*.csv` to vanilla versions:
  - [x] `1.13.1`
  - [x] `1.13.8`
  - [x] `1.13.9`
  - [x] `1.13.11`

## General-equilibrium economy model

- [x] Implement the `Economy` class as a solver state for iterative equilibrium computation.

## Supply chain analysis (nominal)

Extend the LP optimiser into a full supply-chain analysis toolkit. Delivery:
a reusable `src/vic3_analysis/analysis/supply_chain.py` module (composable
functions + small dataclasses) paired with `examples/` scripts and tests,
mirroring the `production_table()` + `examples/production_analysis.py` pattern.

- [x] `Scenario` dataclass (now in `optimize/scenario.py`): an optimisation
  recipe as data (multi-good produce baskets, objective, import limit,
  banned PMs / buildings / building groups, per-building level limits,
  throughput bonuses, era / construction-cost / employment caps,
  infrastructure floor, urban-center tie).
- [x] `SupplyChainNode` / `ProducerNode` dataclasses: recursive upstream
  dependency tree (goods → producer configs → input goods → raw resources).
- [x] Upstream trace: `upstream_tree(economy, good, state=None, scenario=None)`
  using the separate input/output matrices (not the net matrix) to separate
  producers from consumers; *recipe* mode (all producers) when `state is None`,
  *realised* mode (non-zero configs scaled by level) when a solved
  `EconomyState` is given; scenario-aware for throughput-adjusted flows.
- [x] LP scenario runner: `optimize_chain(economy, scenario) -> EconomyState`,
  a thin convenience over the solver-only `NominalOptimizer`.
- [x] Value-added breakdown: `value_added_breakdown(economy, state, good=None)`
  attributing GDP, employment, and construction cost to each good/stage (chain
  vs. whole-economy) using the upstream tree.
- [x] Bottleneck identification via `scipy.linprog` constraint marginals (shadow
  prices), with cost-share ranking as a fallback.
- [x] Comparative what-if: `compare_scenarios(economy, scenarios) -> DataFrame`
  running multiple `Scenario`s and tabulating GDP, employment, construction
  cost, GDP/capita, GDP-per-construction-cost.
- [x] `examples/supply_chain_trace.py`, `examples/supply_chain_optimize.py`,
  `examples/supply_chain_compare.py`.
- [x] `tests/test_supply_chain.py` (end-to-end, following
  `test_nominal_optimizer.py` style; requires local game install).
- [x] Re-export public symbols from `src/vic3_analysis/__init__.py`; update
  `docs/usage/analysis.md` and `docs/project_structure.md`.

## Pop consumption & wealth loop

- [ ] Integrate `buy_packages` (per-wealth pop-need baskets), `pop_needs`
  (per-need goods baskets), and `pop_types` (per-profession wealth) into the
  economy model so demand reflects population composition and wealth levels
  rather than exogenous inputs.

## State-region resource constraints

- [x] Use `StateRegionsParser` total-potential `resource_*` columns to cap
  building levels for resource-limited buildings (gold, oil, iron, ...) in
  `NominalOptimizer`.
