---
title: Equilibrium optimization
description: Search equilibrium GDP with up to one million workers and a 40% workforce ratio.
---

# Million-worker equilibrium GDP search

`examples/optimize_equilibrium.py` uses `EquilibriumOptimizer` to search for
the highest GDP found while household wealth, consumption, prices, and finances
settle together. The search is deterministic and local; its result does not
establish a global maximum.

## Scenario and inputs

The worker cap is **1,000,000**, and the workforce ratio is **0.4**, allowing
up to **2,500,000** people including dependents. Actual employment may be lower.
The scenario excludes `DEFAULT_BANNED_BGS` from `examples/__init__.py`, sets
`min_net_infrastructure=0.0`, and uses
`default_min_goods_output=None`. Infrastructure generation must cover
consumption, so the minimum net infrastructure surplus is zero.

Fixed throughput multipliers are all **1.0**, and level-dependent
economy-of-scale bonuses are disabled. Trade, resource limits, arable-land
limits, and era restrictions retain their defaults. Household demand is
endogenous, calculated from household wealth and population composition.

The script loads the production table, goods, professions, population needs,
and buy packages from the existing artifact datasets. It restricts production
to the union of active building/production-method configurations in the saved
`era_5_automation/*/processes.csv` supply-chain reports. Other configurations
are excluded from both the initial mix and the optimizer's search. Generate
the datasets and supply-chain reports first:

```bash
uv run python -m examples.parse
uv run python -m examples.production_analysis
uv run python -m examples.supply_chain_compare
```

The initial mix starts with equal levels of every allowed configuration,
increases infrastructure suppliers as needed to cover consumption,
and scales to one million workers. Missing reports, an empty active set, or
configurations absent from the production table raise an error. The optimizer
checks scenario feasibility before starting its search. A starting mix that
consumes infrastructure without an active supplier raises an error.

## Run the search

The default hard trial budget is 20,000:

```bash
uv run python -m examples.optimize_equilibrium
```

Direct-file execution is also supported. A short run can validate the pipeline
and regenerate reviewable snapshots:

```bash
uv run python examples/optimize_equilibrium.py --max-evaluations 8
```

The CLI enables timestamped INFO progress on stderr by default, with periodic
summaries every 100 trials. Use a shorter interval for a small-budget run:

```bash
uv run python -m examples.optimize_equilibrium --max-evaluations 8 --log-every 2
```

`--log-level DEBUG` adds individual trial outcomes, new incumbents, and concise
inner-solver start/finish/failure messages. `--log-level WARNING` suppresses
the progress logs while retaining the printed result summary. `--log-every`
must be positive. Imported calls to `run(..., log_every=100)` leave logging
configuration to their caller. Standard logging stream handlers flush each
record, so progress appears as the search runs; redirect stderr to save it.

Progress reports distinguish initialization from subsequent search, show
uncached trials used versus budget, current and best unscaled objective values
in weekly units, scenario feasibility, inner-solver iteration counts, failures,
and elapsed seconds. See the [progress-field reference](../guides/optimization.md#live-progress-logging).
The CSV schemas and annualization rules are unaffected by logging options.

The budget limits optimizer trials. Evaluation of the initial baseline and
fresh verification of the returned state are additional equilibrium solves.
A very small budget can end during search initialization and retain the
initial mix. Larger budgets can take tens of minutes or longer.

The console reports initial and best annual GDP, actual workers and population,
search termination, and household convergence. A budget-limited search saves
its best verified equilibrium with `search_success=False` and an explicit
`search_message`; `equilibrium_status` is still `converged`. Invalid inputs or
a search without a feasible converged state raise an error before writing new
outputs. Financial flags remain visible on successful household equilibria.

## Summary and solution

The summary records scenario settings, initial and final metrics, search
diagnostics, and financial-flag counts. Monetary totals use equilibrium market
prices; annual GDP is weekly GDP multiplied by 52. See the
[summary dictionary](../data-dictionary/economy.md#equilibrium-optimization-summary)
for all columns.

<!-- table-preview: artifacts/analyses/optimization/equilibrium/summary.csv | columns=annual_gdp,employment,population,average_wealth,trial_evaluations,search_success,equilibrium_status | rows=1 -->

[:material-download: Download `artifacts/analyses/optimization/equilibrium/summary.csv`](../artifacts/analyses/optimization/equilibrium/summary.csv)

The solution uses the existing [building registry](../data-dictionary/economy.md#building-registry)
report: nonzero configuration levels, sorted by level descending. Configuration
keys identify building and production-method combinations in the source table.

<!-- table-preview: artifacts/analyses/optimization/equilibrium/buildings.csv | columns=key,level,construction_cost | rows=10 -->

[:material-download: Download `artifacts/analyses/optimization/equilibrium/buildings.csv`](../artifacts/analyses/optimization/equilibrium/buildings.csv)
· [:fontawesome-brands-github: View `examples/optimize_equilibrium.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/main/examples/optimize_equilibrium.py)

The script also exports `market.csv`, `pop.csv`, and `goods_buy_packages.csv`
from the other three `Economy.df_` reports for the same verified state. The
goods buy-package export preserves the wealth index as a `wealth` column.

Each run overwrites all five CSV files. Read the recorded budget and search status
when comparing results. See the [optimization guide](../guides/optimization.md#equilibrium-optimization)
for solver behavior and the [optimization API](../api/optimization.md).
