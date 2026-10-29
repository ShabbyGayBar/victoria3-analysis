---
title: Supply-chain equilibrium optimization
description: Search GDP by scaling complete era-5 production recipes.
---

# Equilibrium search over era-5 supply chains

`examples/optimize_supply_chain_equilibrium.py` loads the transformation matrix
directly from `era_5_automation/building_levels.csv`, trusting the saved input
and selecting the hard-coded `ALLOWED_CHAIN_GOODS` columns. It does not read
the adjacent `summary.csv`. One chain level reproduces a
saved recipe targeting £100,000/week of terminal output at base prices.
Each trial transforms chain levels into building levels, then solves household
wealth, demand, and market prices using the existing equilibrium solver.

Generate inputs with `examples/parse.py`, `examples/production_analysis.py`, and
`examples/supply_chain_compare.py` first. The example selects recipes
in `ALLOWED_CHAIN_GOODS` order and includes every configuration used by a
selected recipe, including supporting infrastructure outside the terminal
graph. It filters unused matrix rows and retains the recipes' production ratios.
If an older artifact collection lacks `building_levels.csv`, rerun
`uv run python -m examples.supply_chain_compare` to generate it. Per-good
process reports are no longer used to reconstruct recipes. The example assumes
the source recipes use the preset's throughput multiplier of 1; the matrix
does not carry throughput metadata.
Exported target metadata assumes the preset's £100,000 base-price target;
target quantities are derived by dividing that value by each good's base price.

The 20 allowed chains, in vector order, are `clothes`, `furniture`, `groceries`,
`coal`, `oil`, `electricity`, `glass`, `services`, `liquor`, `tobacco`, `opium`,
`wine`, `tea`, `coffee`, `transportation`, `automobiles`, `luxury_clothes`,
`luxury_furniture`, `porcelain`, and `small_arms`. Other goods can still be
produced by upstream processes or as coproducts within these recipes.

The objective is GDP. The worker cap is one million, the workforce
ratio is 0.4. Infrastructure is unconstrained (`min_net_infrastructure=None`);
usage remains a reported diagnostic, and the summary records an empty minimum.
The example uses
the shared banned building groups, no goods-balance floor, fixed throughput
of 1, and no level-dependent economies of scale. The initial vector assigns
equal chain levels and scales them to one million workers. Matrix dimensions
are derived from the surviving recipes after unused rows are filtered out.

```bash
uv run python -m examples.optimize_supply_chain_equilibrium --max-evaluations 100 --max-iterations 10 --log-every 10
```

Operating losses are funded by default through a proportional tax on cooperative
and dependent income, without guaranteeing payroll. Disable it with:

```bash
uv run python -m examples.optimize_supply_chain_equilibrium --no-subsidize-operating-losses --max-evaluations 100 --max-iterations 10
```

The selected policy applies to saved baselines and every restart. `--resume` uses
the current invocation's policy, which defaults to enabled; `summary.csv` records
it in `subsidize_operating_losses`. Imported calls also default to enabled; use
`run(..., subsidize_operating_losses=False)` to disable it. Unfundable starting or
saved mixes still enter the optimizer, whose funding-shortfall penalty guides
search toward a fundable recipe mix. An unfunded saved mix cannot become the
best solution. Its initial wealth/GDP metrics are empty, and the summary records
`initial_equilibrium_status=insufficient_income`. Only verified, funded equilibria
are exported. If no valid result is found within the trial budget, existing
exports remain untouched. Other initialization errors still propagate. See
[tax-funded operating losses](../guides/economy.md#tax-funded-operating-losses).

The default hard trial budget is 20,000 **per local search**;
`--log-level WARNING|INFO|DEBUG` controls progress verbosity. After each local
search, the example reduces loss-making terminal producers' chain levels by
`--loss-reduction` (default 0.5), keeps other levels unchanged, and starts the
next search with a fresh trial budget. It does not scale employment back up.
The adjustment includes coproduct revenue and uses the existing numerical loss
tolerance; upstream profits do not hide terminal-producer losses.

Iteration stops when a search's verified weekly GDP is strictly lower than
the preceding search's GDP. Equal GDP continues, with the earliest solution
retained on ties. `--max-iterations` optionally limits the number of completed
local searches. Omit it to continue until GDP decreases; an equal-GDP plateau
can then continue indefinitely. `--loss-reduction 0` disables reductions for
every restart.

The example returns the best feasible, freshly verified equilibrium found
and writes its solution reports once, after iteration ends. The worse result
that triggers stopping is recorded in the summary. A small trial budget can stop during initialization,
retaining the baseline with `search_success=False`. Budget exhaustion does not
imply that the equilibrium solver failed or that a global optimum was found.
Financial deficits and unaffordable households remain visible diagnostics.

To start the next search from the saved solution and halve loss-making goods'
starting chain levels:

```bash
uv run python -m examples.optimize_supply_chain_equilibrium --resume --loss-reduction 0.5 --max-evaluations 100 --max-iterations 10
```

Resume aligns saved levels by good and verifies that the saved recipe matrix
matches the current recipes. It re-evaluates the saved solution, then identifies
negative operating surplus among each recipe's terminal-good producers,
including coproduct revenue. It scales those chains by `1 - loss_reduction`
and keeps other chain levels unchanged, without scaling employment back up.
This changes the starting point; the optimizer can subsequently increase or
decrease any allowed chain. The adjusted vector must satisfy scenario constraints.
The reduction fraction must be at least 0 and less than 1 and defaults to 0.5.
The re-evaluated saved solution remains eligible as the best export. The first
new search is compared against this baseline, so a worse first result stops
iteration and preserves the saved solution. Use
`--resume --loss-reduction 0 --max-iterations 1` for a single search starting
from the saved vector unchanged.
Without `--resume`, the first search starts from equal chain levels; subsequent
searches use the same profitability adjustment as resumed runs.
Validation and equilibrium errors propagate before any export is overwritten.

## Outputs

The separate collection `artifacts/analyses/optimization/supply_chain_equilibrium`
contains:

- `chain_matrix.csv`: labeled building-by-chain transformation coefficients.
- `chains.csv`: invocation starting levels and best chain levels with recipe normalization targets.
- `buildings.csv`: positive building levels and equilibrium finances.
- `market.csv`: all goods' buy/sell orders and equilibrium prices.
- `pop.csv`: population, wealth, income, expenses, and balances by configuration and profession.
- `goods_buy_packages.csv`: wealth-indexed goods baskets, with wealth retained as a CSV column.
- `summary.csv`: one row per completed local search, including initial/final metrics,
  scenario settings, search diagnostics, GDP change, reduction counts, UTC start
  time, and elapsed seconds. Resumed runs also include iteration zero for the
  re-evaluated saved baseline, with empty search diagnostics. `is_best` identifies
  the exported solution. Every row includes the invocation's completed-search
  count, total trial evaluations, total elapsed seconds, selected best iteration,
  optional iteration cap, and stop reason (`objective_worsened` or `max_iterations`).
  Trial totals follow the optimizer's counting convention: initialization counts,
  but final verification and separate baseline/starting-point evaluations do not.

<!-- table-preview: artifacts/analyses/optimization/supply_chain_equilibrium/summary.csv | columns=annual_gdp,average_wealth,employment,trial_evaluations,search_success,equilibrium_status | rows=1 -->

[Download matrix](../artifacts/analyses/optimization/supply_chain_equilibrium/chain_matrix.csv)
· [Download chain levels](../artifacts/analyses/optimization/supply_chain_equilibrium/chains.csv)
· [Download building levels](../artifacts/analyses/optimization/supply_chain_equilibrium/buildings.csv)
· [Download market report](../artifacts/analyses/optimization/supply_chain_equilibrium/market.csv)
· [Download population report](../artifacts/analyses/optimization/supply_chain_equilibrium/pop.csv)
· [Download goods baskets](../artifacts/analyses/optimization/supply_chain_equilibrium/goods_buy_packages.csv)
· [Download summary](../artifacts/analyses/optimization/supply_chain_equilibrium/summary.csv)

Matrix rows use `building + "+" + production_method`. Columns and chain-level
rows use terminal-good keys. Their product reproduces the returned building
levels; the building report filters zeros and sorts positive levels.
See the [guide](../guides/optimization.md#equilibrium-optimization-over-supply-chains)
and [column definitions](../data-dictionary/economy.md#supply-chain-equilibrium-exports).
