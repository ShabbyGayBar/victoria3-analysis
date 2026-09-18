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
- [x] Architecture refactor: `Scenario` is immutable configuration data;
  public sibling `NominalOptimizer` and `MarketOptimizer` classes inherit
  shared context and constraint compilation from `BaseOptimizer`. Their
  inspectable `LinearProblem` / `MarketProblem` objects keep formulation,
  solving, dual lookup, and optimizer-backed analysis consistent.

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
- [x] Implement the solver method for nominal price
- [x] Implement the solver method with market price mechanics
- [x] Implement `MarketOptimizer` for bounded endogenous-price GDP and GDP-per-capita scenarios
- [ ] Implement the solver method with population composition and wealth levels

## Supply chain analysis (nominal)

The nominal supply-chain toolkit is implemented as the
`analysis/supply_chain/` package and deliberately analyzes one terminal good
per solve.

- [x] `Scenario` dataclass (now in `optimize/scenario.py`): an optimisation
  recipe as data (multi-good produce baskets, objective, import limit,
  banned PMs / buildings / building groups, per-building level limits,
  throughput bonuses, era / construction-cost / employment caps,
  infrastructure floor, urban-center tie).
- [x] `SupplyChainAnalyzer` validates a single matching positive target and
  performs exactly one nominal solve.
- [x] Immutable `SupplyChainResult` snapshots matrices, state arrays,
  production metadata, graphs, and solver diagnostics.
- [x] Cyclic bipartite NetworkX graphs provide `realized` and scenario-static
  `allowed` views without treating cycle cutoffs as raw resources.
- [x] Stable DataFrame reports cover goods, processes, flows, workforce,
  constraints, bottlenecks, and alternative producers.
- [x] Process-level coproduct attribution is exact; no implicit good-level
  allocation policy is applied.
- [x] Mermaid and Matplotlib renderers return in-memory objects and prune large
  allowed views deterministically.
- [x] `sweep_supply_chains()` normalizes all producible goods to equal
  base-price value, retains economy order, and records failures while
  continuing sequentially.
- [x] Synthetic tests cover cycles, coproducts, alternatives, imports,
  resources, throughput bonuses, infeasible/unbounded cases, stable schemas,
  visualization objects, and sweeps without requiring a game installation.

## Pop consumption & wealth loop

- [ ] Integrate `buy_packages` (per-wealth pop-need baskets), `pop_needs`
  (per-need goods baskets), and `pop_types` (per-profession wealth) into the
  economy model so demand reflects population composition and wealth levels
  rather than exogenous inputs.

## State-region resource constraints

- [x] Use `StateRegionsParser` total-potential `resource_*` columns to cap
  building levels for resource-limited buildings (gold, oil, iron, ...) in
  `NominalOptimizer`.
