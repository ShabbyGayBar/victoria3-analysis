# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""All-goods supply-chain sweep orchestration."""

from __future__ import annotations

import warnings
from collections.abc import Iterable
from dataclasses import replace

import numpy as np
import pandas as pd

from vic3_analysis.analysis.economy import Economy
from vic3_analysis.analysis.supply_chain.analyzer import SupplyChainAnalyzer
from vic3_analysis.analysis.supply_chain.result import (
    SUMMARY_FIELDS,
    SupplyChainResult,
    SupplyChainSweepResult,
    resource_level_fields,
)
from vic3_analysis.optimize.scenario import Scenario

SWEEP_COLUMNS = ["good", "status", "error_type", "error_message", *SUMMARY_FIELDS]


def sweep_columns(production: pd.DataFrame) -> list[str]:
    """Return fixed and economy-specific columns, even for an empty sweep."""
    return [*SWEEP_COLUMNS, *resource_level_fields(production)]


def sweep_supply_chains(
    economy: Economy,
    scenario_template: Scenario,
    *,
    goods: Iterable[str] | None = None,
    target_value: float = 100_000.0,
    keep_results: bool = False,
    tolerance: float = 1e-9,
) -> SupplyChainSweepResult:
    """Analyze every requested good at an equal base-price target value.

    A non-empty ``scenario_template.min_goods_output`` basket is ignored with a
    ``UserWarning`` because the sweep generates one normalized target for each
    requested good.

    Summary columns include fixed economic metrics and per-building resource
    levels derived from the full economy, including banned and unused types.
    Empty sweeps retain the same columns; failed solves use NaN for metrics.
    """
    if scenario_template.min_goods_output:
        warnings.warn(
            "scenario_template.min_goods_output is ignored; sweep targets are generated "
            "from goods and target_value.",
            UserWarning,
            stacklevel=2,
        )
    if not np.isfinite(target_value) or target_value <= 0:
        raise ValueError("target_value must be a positive finite number.")
    selected_goods = list(economy.producible_goods) if goods is None else list(goods)
    if len(selected_goods) != len(set(selected_goods)):
        raise ValueError("goods must not contain duplicates.")
    goods_index = economy.goods_index
    unknown = [good for good in selected_goods if good not in goods_index]
    if unknown:
        raise ValueError(f"Goods not found in goods index: {unknown}")

    prices = dict(zip(goods_index, economy.base_prices))
    columns = sweep_columns(economy._supply_chain_production)
    rows: list[dict[str, object]] = []
    retained: dict[str, SupplyChainResult] = {}
    for good in selected_goods:
        price = float(prices[good])
        if not np.isfinite(price) or price <= 0:
            raise ValueError(f"Good '{good}' must have a positive finite base price.")
        amount = float(target_value / price)
        name = (
            f"{scenario_template.name}:{good}"
            if scenario_template.name is not None
            else good
        )
        scenario = replace(
            scenario_template,
            min_goods_output=((good, amount),),
            name=name,
        )
        try:
            result = SupplyChainAnalyzer(
                economy,
                scenario,
                good,
                tolerance=tolerance,
            ).run()
            row: dict[str, object] = {
                str(key): value for key, value in result.summary().items()
            }
            row.update(
                {
                    "good": good,
                    "status": "success",
                    "error_type": "",
                    "error_message": "",
                }
            )
            if keep_results:
                retained[good] = result
        except ValueError as exc:
            row = {field: float("nan") for field in columns}
            row.update(
                {
                    "good": good,
                    "status": "failure",
                    "error_type": type(exc).__name__,
                    "error_message": str(exc),
                    "scenario": name,
                    "terminal_good": good,
                    "objective": scenario.objective,
                    "solver_status": -1,
                    "solver_message": str(exc),
                    "target_quantity": amount,
                    "target_base_value": target_value,
                    "terminal_base_price": price,
                }
            )
        rows.append(row)

    summary = pd.DataFrame(rows, columns=columns)
    failures = pd.DataFrame(
        summary.loc[summary["status"].eq("failure"), :]
    ).reset_index(drop=True)
    return SupplyChainSweepResult(
        _summary=summary,
        _failures=failures,
        _results=retained,
    )
