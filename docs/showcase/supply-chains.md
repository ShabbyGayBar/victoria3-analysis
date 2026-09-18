---
title: Supply chains
description: Compare Victoria 3 supply-chain scenarios and inspect recipe and realized dependency graphs.
---

# Supply chains

These examples use the same reusable `Economy`, `Scenario`, and supply-chain
APIs described in the [supply-chain guide](../guides/supply-chain.md).

## Allowed technology graph

The allowed view follows scenario-permitted automobile producers and their
upstream goods. It retains active configurations and otherwise limits each good
to the top three producers by adjusted output rate. Dashed edges mark cycles.

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
normalized by base value. Each row uses the fixed sweep schema and records
solver failures without stopping later goods.

<!-- table-preview: tables/supply_chain_sweep.csv | columns=good,configuration,status,objective,target_quantity,target_base_value,system_gdp_annual,system_employment | rows=5 -->

[:material-download: Download `tables/supply_chain_sweep.csv`](../tables/supply_chain_sweep.csv)
· [:fontawesome-brands-github: View `examples/supply_chain_compare.py`](https://github.com/ShabbyGayBar/victoria3-analysis/blob/DEV/examples/supply_chain_compare.py)

```bash
uv run python -m examples.supply_chain_compare
```

## Cangshulun product details

`supply_chain_cangshulun.csv` contains one normalized automation scenario per
producible good plus named glass, furniture, logging, groceries, clothing,
urban-center, and power variants. It records the same stable summary metrics as
the public analyzer, including cyclic structure, resource processes, and chain
shares of whole-system totals.

<!-- table-preview: tables/supply_chain_cangshulun.csv | columns=good,variant,status,objective,target_base_value,system_gdp_annual,chain_employment,realized_process_count | rows=5 -->

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
