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
`min_net_infrastructure_usage=0.0`, and uses
`default_min_goods_output=None`. Net infrastructure usage retains the
scenario's existing lower-bound semantics.

Fixed throughput multipliers are all **1.0**, and level-dependent
economy-of-scale bonuses are disabled. Trade, resource limits, arable-land
limits, and era restrictions retain their defaults. Household demand is
endogenous, so no fixed `pop_needs` orders are supplied.

The script loads the production table, goods, professions, population needs,
and buy packages from the existing artifact datasets. Generate them first:

```bash
uv run python -m examples.parse
uv run python -m examples.production_analysis
```

The initial mix uses equal levels of every allowed configuration, scaled to
one million workers. With the current datasets it is feasible and supplies a
broader consumption basket than the nominal GDP LP seed. The optimizer checks
scenario feasibility before starting its search.

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

Each run overwrites these two files. Read the recorded budget and search status
when comparing results. See the [optimization guide](../guides/optimization.md#equilibrium-optimization)
for solver behavior and the [optimization API](../api/optimization.md).
