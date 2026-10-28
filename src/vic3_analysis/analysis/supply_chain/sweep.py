# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""All-goods supply-chain sweep orchestration."""

from __future__ import annotations

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
from vic3_analysis.optimize._orders import goods_order_vector
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
    """Analyze goods with at least the requested base-price export value.

    Each terminal export amount is the higher of its aggregated template
    exports and ``target_value / base_price``. Other exports and all imports
    are retained. Target metadata reports the effective terminal exports.

    Summary columns include fixed economic metrics and per-building resource
    levels derived from the full economy, including banned and unused types.
    Empty sweeps retain the same columns; failed solves use NaN for metrics.
    ``df_building_levels`` retains every production unit's solved level for
    each requested good, independently of ``keep_results``; failures use NaN.
    """
    if not np.isfinite(target_value) or target_value <= 0:
        raise ValueError("target_value must be a positive finite number.")
    selected_goods = list(economy.producible_goods) if goods is None else list(goods)
    if len(selected_goods) != len(set(selected_goods)):
        raise ValueError("goods must not contain duplicates.")
    goods_index = economy.goods_index
    unknown = [good for good in selected_goods if good not in goods_index]
    if unknown:
        raise ValueError(f"Goods not found in goods index: {unknown}")

    template_exports = goods_order_vector(
        goods_index, scenario_template.goods_export, "goods_export"
    )
    prices = dict(zip(goods_index, economy.base_prices))
    columns = sweep_columns(economy.df_production)
    rows: list[dict[str, object]] = []
    retained: dict[str, SupplyChainResult] = {}
    building_levels = pd.DataFrame(
        np.nan,
        index=pd.Index(economy.building_index, name="config"),
        columns=selected_goods,
        dtype=np.float64,
    )
    for good in selected_goods:
        price = float(prices[good])
        if not np.isfinite(price) or price <= 0:
            raise ValueError(f"Good '{good}' must have a positive finite base price.")
        amount = max(
            float(template_exports[goods_index.index(good)]),
            float(target_value / price),
        )
        name = (
            f"{scenario_template.name}:{good}"
            if scenario_template.name is not None
            else good
        )
        scenario = replace(
            scenario_template,
            goods_export=tuple(
                (key, value)
                for key, value in scenario_template.goods_export
                if key != good
            )
            + ((good, amount),),
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
            building_levels[good] = result.state.building_levels
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
                    "target_base_value": amount * price,
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
        _building_levels=building_levels,
        _results=retained,
    )
