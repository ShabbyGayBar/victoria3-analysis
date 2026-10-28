---
title: Equilibrium optimization
description: Search equilibrium wealth with up to one million workers and a 40% workforce ratio.
---

# Million-worker equilibrium wealth search

`examples/optimize_equilibrium.py` uses `EquilibriumOptimizer` to search for
the highest average wealth found while household wealth, consumption, prices, and finances
settle together. The search is deterministic and local; its result does not
establish a global maximum.

## Scenario and inputs

The worker cap is **1,000,000**, and the workforce ratio is **0.4**, allowing
up to **2,500,000** people including dependents. Actual employment may be lower.
The scenario excludes `DEFAULT_BANNED_BGS` from `examples/__init__.py`, and uses
`min_goods_balance=None`.
Infrastructure is unconstrained (`min_net_infrastructure=None`); usage remains
visible in reports as a diagnostic, and the summary records an empty minimum.

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

The initial mix starts with equal levels of every allowed configuration
and scales to one million workers without balancing infrastructure. A mix
with infrastructure consumption and no supplier is permitted.
Missing reports, an empty active set, or
configurations absent from the production table raise an error. The optimizer
checks scenario feasibility before starting its search.

## Run the search

The default hard trial budget is 20,000 per local search:

```bash
uv run python -m examples.optimize_equilibrium --max-iterations 10
```

Direct-file execution is also supported. A short run can validate the pipeline
and regenerate reviewable snapshots:

```bash
uv run python examples/optimize_equilibrium.py --max-evaluations 8 --max-iterations 1
```

The CLI enables timestamped INFO progress on stderr by default, with periodic
summaries every 100 trials. Use a shorter interval for a small-budget run:

```bash
uv run python -m examples.optimize_equilibrium --max-evaluations 8 --max-iterations 1 --log-every 2
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

After each completed search, the example reduces materially loss-making
building configurations by `--loss-reduction` (default 0.5) and restarts with
a fresh trial budget. Profitability uses all output revenue, including
coproducts, minus input costs at the returned equilibrium prices, with the
same absolute/relative loss tolerance as the supply-chain example. Other levels
are unchanged, and employment is not scaled back up. The adjusted mix must
remain feasible under the scenario's worker cap and building exclusions.

Iteration stops when the returned objective is strictly lower than the preceding
search's objective. The scenario maximizes **average wealth**; GDP remains a
reported metric. Equal objectives continue, and the earliest result wins ties.
`--max-iterations` optionally caps completed local searches. Omission means
unlimited searches, so an equal-objective plateau can continue indefinitely.
`--loss-reduction 0` disables reductions for all restarts.

To start from the saved solution:

```bash
uv run python -m examples.optimize_equilibrium --resume --loss-reduction 0.5 --max-iterations 10
```

Resume aligns `buildings.csv` by building and production method, restores
omitted zero configurations, and validates the saved levels against the current
scenario. Duplicate or unknown configurations are rejected. The saved levels
are re-evaluated, then adjusted for the first local search. The saved baseline
remains eligible as the best solution; if the first new result is worse,
iteration stops and exports that baseline. Use
`--resume --loss-reduction 0 --max-iterations 1` for one local search from the
unchanged saved levels.

The budget limits optimizer trials. Evaluation of the initial baseline and
fresh verification of the returned state are additional equilibrium solves.
A very small budget can end during search initialization and retain the
initial mix. Larger budgets can take tens of minutes or longer.

The console reports each search's initial and returned objective, the best
objective, annual GDP, actual workers and population, and iteration termination.
A budget-limited search retains
its best verified equilibrium with `search_success=False` and an explicit
`search_message`; `equilibrium_status` is still `converged`. Invalid inputs or
a search without a feasible converged state raise an error before writing new
outputs. Financial flags remain visible on successful household equilibria.

## Summary and solution

The summary has one row per completed local search, including the worse attempt
that triggers stopping. A resumed invocation also has an iteration-zero row for
the re-evaluated saved baseline with empty search diagnostics. Each row records
scenario settings, starting and returned metrics, search diagnostics,
financial-flag counts, applied reduction, objective change, UTC start time, and
elapsed seconds. `is_best` selects the row whose solution is exported. Every row
also records invocation totals, the selected best iteration, optional iteration
cap, and stop reason (`objective_worsened` or `max_iterations`).
Monetary totals use equilibrium market
prices; annual GDP is weekly GDP multiplied by 52. See the
[summary dictionary](../data-dictionary/economy.md#equilibrium-optimization-summary)
for all columns.

<!-- table-preview: artifacts/analyses/optimization/equilibrium/summary.csv | columns=annual_gdp,employment,population,average_wealth,trial_evaluations,search_success,equilibrium_status | rows=1 -->

[:material-download: Download `artifacts/analyses/optimization/equilibrium/summary.csv`](../artifacts/analyses/optimization/equilibrium/summary.csv)

The solution uses the existing [building registry](../data-dictionary/economy.md#building-registry)
report: nonzero configuration levels, sorted by level descending. Configuration
keys identify building and production-method combinations in the source table.

<!-- table-preview: artifacts/analyses/optimization/equilibrium/buildings.csv | columns=building,production_method,level,construction_cost | rows=10 -->

[:material-download: Download `artifacts/analyses/optimization/equilibrium/buildings.csv`](../artifacts/analyses/optimization/equilibrium/buildings.csv)
· [:fontawesome-brands-github: View `examples/optimize_equilibrium.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/main/examples/optimize_equilibrium.py)

The script also exports `market.csv`, `pop.csv`, and `goods_buy_packages.csv`
from the other three `Economy.df_` reports for the same verified state. The
goods buy-package export preserves the wealth index as a `wealth` column.

After iteration ends, the best retained solution is written once to the four
solution CSVs; `summary.csv` contains the full search history. Validation and
equilibrium errors propagate before any files are overwritten.
Read the recorded budgets and search status
when comparing results. See the [optimization guide](../guides/optimization.md#equilibrium-optimization)
for solver behavior and the [optimization API](../api/optimization.md).
