---
title: Supply chains
description: Compare employment, construction, and production choices with results grouped by configuration and terminal good.
---

# Supply chains

How many workers and construction points does a supply chain require? Which
production configurations supply its inputs? `examples/supply_chain_compare.py`
answers these questions for every producible good, saving the reports, plots,
and diagrams under each configuration and then terminal good.

The [supply-chain guide](../guides/supply-chain.md) explains the API and graph
model. The [data dictionary](../data-dictionary/supply-chain.md) defines the
report columns, units, formulas, and failure behavior.

[:fontawesome-brands-github: View `examples/supply_chain_compare.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/supply_chain_compare.py)

## Run the comparison

Generate the parsed and production datasets first, then run:

```bash
uv run python -m examples.supply_chain_compare
```

To analyze selected goods and save the results to a temporary artifact root:

```bash
uv run python -m examples.supply_chain_compare \
    --datasets-dir artifacts/datasets \
    --output-dir /tmp/supply-chain-comparison \
    --goods automobiles steel
```

Each good has a weekly target base value of **£100,000**, with target quantity
calculated as `100_000 / base_price`. This is a minimum net-production target.
Surplus and coproducts are possible, so equal target value does not imply equal
GDP or make goods interchangeable.

| Configuration | Objective | Technology and additional restrictions |
| --- | --- | --- |
| `era_3_construction` | Minimum whole-system construction | Era 3 |
| `era_5_automation` | Minimum whole-system employment | Era 5 |
| `cangshulun` | Minimum whole-system employment | Era 5, `CANGSHULUN_BANNED_PMS`, and `CANGSHULUN_BUILDING_LIMITS` |

All configurations use autarky, the shared `DEFAULT_BANNED_BGS` exclusions,
base prices, and continuous building levels. There are no construction budgets
or budget sensitivity experiments. The era 3 and era 5 presets change both
the objective and technology availability; their difference cannot be attributed
to the objective alone. The cangshulun preset shows how its additional PM and
building restrictions change an era 5 minimum-employment chain.

Era availability does not simulate every in-game law, qualification, or
state-specific PM restriction. These are model requirements, with no wage costs
or profession availability constraints.

A failed solve produces a configuration-summary row with its requested target,
status, and error text, and the script continues to the next configuration and good.
Failed configurations have no detailed reports or plots. Unknown goods,
duplicate good keys, and invalid base prices raise before any output is written.

## Read one good's results

Filter `artifacts/analyses/supply_chains/comparison/summary.csv` by
`good == "automobiles"` to compare the three presets for automobiles.
Each preset's detailed results live under its own configuration directory.

The regenerated CSV snapshot gives the following automobile requirements.
The input CSVs do not identify a game version, so these numbers describe this
snapshot and the assumptions above.

| Configuration | Status | Employment (workers) | Construction (points) |
| --- | --- | ---: | ---: |
| Era 3 construction | Infeasible | Unavailable | Unavailable |
| Era 5 automation | Success | 125,161 | 25,217.7 |
| Cangshulun | Success | 138,218 | 27,713.7 |

The £100,000 target corresponds to **1,000 automobiles per week**. Both
successful cases produce £100,000 of weekly value added, or £5.2 million
annually, while using different amounts of labor and construction. In this
example, whole-system and terminal-chain totals agree; that equality is not
a general guarantee of the API.

Within `analyses/supply_chains/era_5_automation/automobiles/`, the reports explain
where those requirements come from:

- `goods.csv` and `goods_balance.svg` compare supply, consumption, imports,
  and net production. The terminal production floor is a separate constraint,
  rather than a population or export buy order.
- `processes.csv` identifies the selected building/PM configurations and
  their levels. `flows.csv` records process inputs and outputs.
- `workforce.csv` and `workforce.svg` describe employment by profession.
  Minimizing total employment does not necessarily minimize skilled labor.
- `constraints.csv`, `bottlenecks.csv`, and `constraints.svg` expose LP
  diagnostics and useful binding inequalities. Marginals are local and
  objective-specific, and constraints can have different units.
- `alternatives.csv` lists all allowed producer configurations, including
  inactive ones. The diagrams can prune alternatives for readability.

### Follow the network

`supply_chain_recipe.mmd` shows the allowed technology and
`supply_chain_realised.mmd` the realized chain. `network.svg` weights realized
edges by base-price value. Its layout distances have no economic units.

Allowed automobile technology in the era 5 automation preset:

```mermaid
--8<-- "artifacts/analyses/supply_chains/era_5_automation/automobiles/supply_chain_recipe.mmd"
```

Realized automobile chain:

```mermaid
--8<-- "artifacts/analyses/supply_chains/era_5_automation/automobiles/supply_chain_realised.mmd"
```

Cycles represent real feedback. For example, oil extraction can consume engines
while motor industries consume oil. A traversal cutoff does not turn either
good into a free resource. Check the quantitative flows rather than inferring
requirements from graph depth.

The regenerated era 5 automobile network contains **16 processes, 16 goods,
and 77 edges**, with one cyclic component. The allowed graph includes many
more alternatives, so a pruned diagram cannot establish their total count.

### Compare contributions

`contributions_gdp.svg`, `contributions_employment.svg`, and
`contributions_construction_cost.svg` show leading whole-process contributions
to the terminal chain. The same process can matter very differently for labor,
construction, and value added.

For the era 5 automobile chain, automotive assembly employs **70,000 workers**
and requires **16,000 construction points**. The upstream chain therefore
accounts for another 55,161 workers. Rubber plantations employ about 16,392
workers but require only 655.7 construction points; oil rigs employ 15,590
workers and require 2,078.7 points. Their relative importance changes between
the employment and construction charts. Machinists and engineers together
account for **73.9% of chain employment**, which illustrates why a small total
workforce can still depend heavily on skilled professions.

Chain totals include whole selected processes, including their coproducts;
they do not allocate a factory's workers or construction uniquely to one good.
Whole-system totals can also include activity outside the graph-defined chain.
Weekly value added is output base value minus intermediate input base cost;
annual GDP is 52 times weekly GDP.

## Compare goods

The combined summary is
`artifacts/analyses/supply_chains/comparison/summary.csv`.
It contains one row per good/configuration pair selected in the current run,
in requested good order and then configuration order. It retains failures.
Each configuration has one `summary.csv` combining its selected goods,
for example `analyses/supply_chains/era_5_automation/summary.csv`.
It records each good's target, objective, solver status, whole-system totals,
chain totals, and configuration labels. No summary files are written inside
the individual good directories.
Use a single configuration when ranking goods under common assumptions.

<!-- table-preview: artifacts/analyses/supply_chains/comparison/summary.csv | columns=good,configuration,status,objective,target_quantity,target_base_value,system_gdp_annual,system_employment | rows=5 -->

[:material-download: Download all-good comparison](../artifacts/analyses/supply_chains/comparison/summary.csv)

The comparison directory contains only this summary and two grouped bar charts:

- `pop.svg` plots `system_employment`, the whole-system employed population
  in workers. It excludes dependents and unemployed people.
- `construction_points.svg` plots `system_construction_cost` in construction
  points.

Both charts use goods as the main horizontal-axis ticks, with configuration
ticks beneath the individual bars. Colors identify configurations consistently
between charts. A failed solve keeps its tick and shows an × instead of a bar;
it is not treated as a zero requirement. SVG width grows with the number of
goods so the two tick levels remain readable when zoomed.

[:material-download: Population chart](../artifacts/analyses/supply_chains/comparison/pop.svg)
· [:material-download: Construction chart](../artifacts/analyses/supply_chains/comparison/construction_points.svg)

```python
from pathlib import Path
import pandas as pd

comparison = pd.read_csv(
    Path("artifacts/analyses/supply_chains/comparison/summary.csv")
)
successful = comparison.loc[
    comparison["configuration"].eq("era_5_automation")
    & comparison["status"].eq("success")
]
lowest_employment = successful.sort_values(
    ["system_employment", "good"], kind="stable"
).head(10)
```

Sorting the automation rows by construction answers which of those
minimum-employment chains uses least construction. It does not compute a
minimum-construction optimum for each good.

## Cangshulun product details

`examples/supply_chain_cangshulun.py` adds the separate video comparison,
including its throughput bonuses, video-specific bans, and named product
variants. These assumptions differ from the comparison script's `cangshulun`
preset. All goods and their variants are saved in the single configuration-level
`analyses/supply_chains/cangshulun_video/summary.csv`, with `good` and `variant`
columns identifying each row. This example writes no per-good files.

```bash
uv run python -m examples.supply_chain_cangshulun
```

The cross-good video index is
`artifacts/analyses/supply_chains/cangshulun_video/summary.csv`.

<!-- table-preview: artifacts/analyses/supply_chains/cangshulun_video/summary.csv | columns=good,variant,status,objective,target_base_value,system_gdp_annual,chain_employment,realized_process_count | rows=5 -->

[:material-download: Download cangshulun video index](../artifacts/analyses/supply_chains/cangshulun_video/summary.csv)
· [:fontawesome-brands-github: View `examples/supply_chain_cangshulun.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/supply_chain_cangshulun.py)

## Output inventory

Paths are relative to `--output-dir`. All text outputs use UTF-8 without a BOM.
The comparison writes one detailed result at a time rather than retaining
all goods' graphs and snapshots in memory.

| Directory | Files |
| --- | --- |
| `analyses/supply_chains/era_3_construction/<good>/` | Detailed files below for successful solves |
| `analyses/supply_chains/era_5_automation/<good>/` | Same reports, plots, and diagrams |
| `analyses/supply_chains/cangshulun/<good>/` | Same reports, plots, and diagrams |
| `analyses/supply_chains/<configuration>/` | `summary.csv`, combining that configuration's selected goods |
| `analyses/supply_chains/comparison/` | `summary.csv`, `pop.svg`, `construction_points.svg`, covering all selected goods and presets |

Each successful comparison configuration contains `goods.csv`, `processes.csv`,
`flows.csv`, `workforce.csv`, `constraints.csv`, `bottlenecks.csv`,
`alternatives.csv`, `supply_chain_recipe.mmd`, `supply_chain_realised.mmd`,
`network.svg`, `goods_balance.svg`, `workforce.svg`, `constraints.svg`,
`contributions_gdp.svg`, `contributions_employment.svg`, and
`contributions_construction_cost.svg`. Headline metrics and failure rows are
stored only in the configuration-level `summary.csv` and comparison CSVs.

The configuration summary and comparison CSVs use the public sweep schema,
plus `configuration` and `ban_config`. The other detailed CSVs retain their
public report schemas. Cross-good summaries sit at configuration level.
A selected-good run replaces the configuration summaries and combined
comparison with that run's selection; other goods' directories remain.
