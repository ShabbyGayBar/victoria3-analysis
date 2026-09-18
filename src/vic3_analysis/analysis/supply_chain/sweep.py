"""All-goods supply-chain sweep orchestration."""

from __future__ import annotations

import warnings
from collections.abc import Iterable
from dataclasses import replace

import numpy as np
import pandas as pd

from vic3_analysis.analysis.economy import Economy
from vic3_analysis.analysis.supply_chain.analyzer import (
    SupplyChainAnalyzer,
    _EconomySnapshot,
)
from vic3_analysis.analysis.supply_chain.result import (
    SUMMARY_FIELDS,
    SupplyChainResult,
    SupplyChainSweepResult,
)
from vic3_analysis.optimize.scenario import Scenario

SWEEP_COLUMNS = ["good", "status", "error_type", "error_message", *SUMMARY_FIELDS]


class _CachedSweepEconomy(Economy):
    """Economy facade that reuses immutable indexes, vectors, and matrices."""

    def __init__(self, source: Economy, snapshot: _EconomySnapshot) -> None:
        self.df_production = source.df_production
        self.df_goods = source.df_goods
        self.df_pop_types = source.df_pop_types
        self._snapshot = snapshot
        self._input_matrix = source.goods_input_matrix()
        self._output_matrix = source.goods_output_matrix()
        self._base_prices = source.base_prices()

    def building_index(self) -> list[str]:
        return list(self._snapshot.config_index)

    def goods_index(self) -> list[str]:
        return list(self._snapshot.goods_index)

    def pop_index(self) -> list[str]:
        return list(self._snapshot.profession_index)

    def base_prices(self) -> np.ndarray:
        return self._base_prices.copy()

    def goods_input_matrix(
        self, throughput_multipliers: np.ndarray | None = None
    ) -> np.ndarray:
        if throughput_multipliers is None:
            return self._input_matrix.copy()
        self._validate_throughput_multipliers(throughput_multipliers)
        return self._input_matrix * throughput_multipliers[:, None]

    def goods_output_matrix(
        self, throughput_multipliers: np.ndarray | None = None
    ) -> np.ndarray:
        if throughput_multipliers is None:
            return self._output_matrix.copy()
        self._validate_throughput_multipliers(throughput_multipliers)
        return self._output_matrix * throughput_multipliers[:, None]

    def employment_matrix(self) -> np.ndarray:
        return self._snapshot.employment_matrix.copy()

    def employment_vector(self) -> np.ndarray:
        return self._snapshot.employment_vector.copy()

    def construction_cost_vector(self) -> np.ndarray:
        return self._snapshot.construction_cost_vector.copy()

    def arable_land_vector(self) -> np.ndarray:
        return self._snapshot.arable_land_vector.copy()


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

    A non-empty ``scenario_template.produce`` basket is ignored with a
    ``UserWarning`` because the sweep generates one normalized target for each
    requested good.
    """
    if scenario_template.produce:
        warnings.warn(
            "scenario_template.produce is ignored; sweep targets are generated "
            "from goods and target_value.",
            UserWarning,
            stacklevel=2,
        )
    if not np.isfinite(target_value) or target_value <= 0:
        raise ValueError("target_value must be a positive finite number.")
    selected_goods = list(economy.producible_goods()) if goods is None else list(goods)
    if len(selected_goods) != len(set(selected_goods)):
        raise ValueError("goods must not contain duplicates.")
    goods_index = economy.goods_index()
    unknown = [good for good in selected_goods if good not in goods_index]
    if unknown:
        raise ValueError(f"Goods not found in goods index: {unknown}")

    snapshot = _EconomySnapshot.from_economy(economy)
    cached_economy = _CachedSweepEconomy(economy, snapshot)
    prices = dict(zip(goods_index, cached_economy.base_prices()))
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
            produce=((good, amount),),
            name=name,
        )
        try:
            result = SupplyChainAnalyzer(
                cached_economy,
                scenario,
                good,
                tolerance=tolerance,
                _snapshot=snapshot,
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
            row = {field: float("nan") for field in SUMMARY_FIELDS}
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

    summary = pd.DataFrame(rows, columns=SWEEP_COLUMNS)
    failures = pd.DataFrame(
        summary.loc[summary["status"].eq("failure"), :]
    ).reset_index(drop=True)
    return SupplyChainSweepResult(
        _summary=summary,
        _failures=failures,
        _results=retained,
    )
