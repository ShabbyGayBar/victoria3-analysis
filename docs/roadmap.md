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
  - [x] `common/goods`
  - [x] `common/production_methods`
  - [x] `common/production_method_groups`
  - [x] `common/technology`
  - [x] `common/buy_packages`
  - [x] `map_data/state_regions`.
- [x] `parse_merge` utility: UTF-8-SIG read, `?=`/`!=` neutralisation, multi-file
  merge into a `pyradox.Tree`.
- [x] `get_vic3_directory()` auto-detection across Steam library paths on
  Windows / Linux / macOS.

## Production optimisation (LP-based)

- [x] `ProductionUnit`, `production_table()`, `ProductionAnalyzer`,
  `OptimizeResult` for production-chain modelling and
  `scipy.optimize.linprog` optimisation.

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

## Pop consumption & wealth loop

- [ ] Integrate `buy_packages` (per-wealth pop-need baskets) and `pop_types`
  (per-profession wealth) into the economy model so demand reflects population
  composition and wealth levels rather than exogenous inputs.

## State-region resource constraints

- [ ] Use `StateRegionsParser` resource columns (`resource_*`,
  `discovered_amount_resource_*`) to cap building levels for resource-limited
  buildings (gold, oil, iron, ...) in `ProductionAnalyzer`.
