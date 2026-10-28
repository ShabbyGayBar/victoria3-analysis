---
title: Supply-chain equilibrium optimization
description: Search GDP by scaling complete era-5 production recipes.
---

# Equilibrium search over era-5 supply chains

`examples/optimize_supply_chain_equilibrium.py` builds a transformation matrix
from the successful `era_5_automation` reports. One chain level reproduces a
saved recipe targeting £100,000/week of terminal output at base prices.
Each trial transforms chain levels into building levels, then solves household
wealth, demand, and market prices using the existing equilibrium solver.

Generate inputs with `examples/parse.py`, `examples/production_analysis.py`, and
`examples/supply_chain_compare.py` first. The example selects successful recipes
in `ALLOWED_CHAIN_GOODS` order and includes every active configuration, including supporting infrastructure
outside the terminal graph. It retains the recipes' production ratios.

The 20 allowed chains, in vector order, are `clothes`, `furniture`, `groceries`,
`coal`, `oil`, `electricity`, `glass`, `services`, `liquor`, `tobacco`, `opium`,
`wine`, `tea`, `coffee`, `transportation`, `automobiles`, `luxury_clothes`,
`luxury_furniture`, `porcelain`, and `small_arms`. Other goods can still be
produced by upstream processes or as coproducts within these recipes.

The objective is GDP. The worker cap is one million, the workforce
ratio is 0.4, and infrastructure generation must cover usage. The example uses
the shared banned building groups, no domestic-output minima, fixed throughput
of 1, and no level-dependent economies of scale. The initial vector assigns
equal chain levels and scales them to one million workers. The current
47-configuration, 20-chain data yields a converged starting equilibrium;
dimensions are derived from the reports.

```bash
uv run python -m examples.optimize_supply_chain_equilibrium --max-evaluations 100 --log-every 10
```

The default hard trial budget is 20,000; `--log-level WARNING|INFO|DEBUG`
controls progress verbosity. The search returns the best feasible, freshly
verified equilibrium found. A small budget can stop during initialization,
retaining the baseline with `search_success=False`. Budget exhaustion does not
imply that the equilibrium solver failed or that a global optimum was found.
Financial deficits and unaffordable households remain visible diagnostics.

To start the next search from the saved solution and halve loss-making goods'
starting chain levels:

```bash
uv run python -m examples.optimize_supply_chain_equilibrium --resume --loss-reduction 0.5 --max-evaluations 100
```

Resume aligns saved levels by good and verifies that the saved recipe matrix
matches the current basis. It re-evaluates the saved solution, then identifies
negative operating surplus among each recipe's terminal-good producers,
including coproduct revenue. It scales those chains by `1 - loss_reduction`
and keeps other chain levels unchanged, without scaling employment back up.
This changes the starting point; the optimizer can subsequently increase or
decrease any allowed chain. The adjusted vector must satisfy scenario constraints.
The reduction fraction must be at least 0 and less than 1 and defaults to 0.5.
Use `--resume --loss-reduction 0` to optimize the saved vector unchanged, then
use `--resume --loss-reduction 0.5` for the reduce-and-optimize step. Both runs
default to a full 20,000-trial budget and may converge earlier.
Without `--resume`, the example still starts from equal chain levels.

## Outputs

The separate collection `artifacts/analyses/optimization/supply_chain_equilibrium`
contains:

- `chain_matrix.csv`: labeled building-by-chain transformation coefficients.
- `chains.csv`: initial and final chain levels with recipe normalization targets.
- `buildings.csv`: positive building levels and equilibrium finances.
- `market.csv`: all goods' buy/sell orders and equilibrium prices.
- `pop.csv`: population, wealth, income, expenses, and balances by configuration and profession.
- `goods_buy_packages.csv`: wealth-indexed goods baskets, with wealth retained as a CSV column.
- `summary.csv`: initial/final metrics, scenario settings, and search diagnostics.

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
