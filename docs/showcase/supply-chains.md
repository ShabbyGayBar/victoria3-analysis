---
title: Supply chains
description: Compare Victoria 3 supply-chain scenarios and inspect recipe and realized dependency graphs.
---

# Supply chains

These examples use the same reusable `Economy`, `Scenario`, and supply-chain
APIs described in the [supply-chain guide](../guides/supply-chain.md).

## Recipe graph

The recipe view aggregates all configurations that can produce automobiles and
follows their upstream goods. Dashed edges mark mutual dependencies.

```mermaid
--8<-- "figures/supply_chain_recipe.mmd"
```

[:material-download: Download `figures/supply_chain_recipe.mmd`](../figures/supply_chain_recipe.mmd)
· [:fontawesome-brands-github: View `examples/supply_chain_trace.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/supply_chain_trace.py)

## Realized graph

The realized view solves one automobile per week under autarky with maximum
automation, then shows only active producer configurations and their levels.

```mermaid
--8<-- "figures/supply_chain_realised.mmd"
```

[:material-download: Download `figures/supply_chain_realised.mmd`](../figures/supply_chain_realised.mmd)
· [:fontawesome-brands-github: View `examples/supply_chain_trace.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/supply_chain_trace.py)

```bash
uv run python -m examples.supply_chain_trace
```

## All-goods scenario sweep

`supply_chain_sweep.csv` compares every producible good across era 2, era 3,
era 5 automation, and the cangshulun ban configuration. Production targets are
normalized by base value, making GDP-per-capita and construction efficiency
comparable across goods.

<!-- table-preview: tables/supply_chain_sweep.csv | columns=goods,objective,ban_config,production,annual_gdp,employment,gdp_per_capita,gdp_per_construction | rows=5 -->

[:material-download: Download `tables/supply_chain_sweep.csv`](../tables/supply_chain_sweep.csv)
· [:fontawesome-brands-github: View `examples/supply_chain_compare.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/supply_chain_compare.py)

```bash
uv run python -m examples.supply_chain_compare
```

## Cangshulun product details

`supply_chain_cangshulun.csv` contains one normalized automation scenario per
producible good plus named railway, glass, furniture, logging, groceries,
clothing, grain, and urban-center variants. It records annual GDP, GDP per
capita, resource-building levels, and employment-normalized levels.

<!-- table-preview: tables/supply_chain_cangshulun.csv | columns=scenario,goods,objective,ban_config,annual_gdp,employment,gdp_per_capita,construction_cost | rows=5 -->

[:material-download: Download `tables/supply_chain_cangshulun.csv`](../tables/supply_chain_cangshulun.csv)
· [:fontawesome-brands-github: View `examples/supply_chain_cangshulun.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/supply_chain_cangshulun.py)

```bash
uv run python -m examples.supply_chain_cangshulun
```

## Automobile market optimization

`examples/supply_chain_market_automobiles.py` solves a bounded automobile
supply chain with 100 weekly automobile export orders, no imports, and the
`gdp_per_capita` market-price objective. It prints the same fixed summary
columns used by the cangshulun report without writing a generated artifact.

[:fontawesome-brands-github: View `examples/supply_chain_market_automobiles.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/supply_chain_market_automobiles.py)

```bash
uv run python -m examples.supply_chain_market_automobiles
```
