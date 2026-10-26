# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""DataFrame reports for complete economy snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from vic3_analysis.analysis.economy.states import (
    EconomyState,
)

if TYPE_CHECKING:
    from vic3_analysis.analysis.economy.model import Economy


def df_buildings(economy: Economy, eco: EconomyState) -> pd.DataFrame:
    """Export an `EconomyState`'s building registry to a DataFrame.

    Args:
        eco: The `EconomyState` to export (as produced by
            `solve`).

    Returns:
        A ``DataFrame`` with columns ``"key"``, ``"level"`` and
        ``"construction_cost"``, filtered to non-zero levels and sorted by
        ``"level"`` descending.
    """
    df = pd.DataFrame(
        {
            "key": economy.building_index,
            "level": eco.building_levels,
            "construction_cost": economy.construction_cost_vector * eco.building_levels,
        }
    )
    df = df[df["level"] > 0].copy()
    df = df.sort_values(by="level", ascending=False)  # pyright: ignore[reportCallIssue]
    return df


def df_market(economy: Economy, eco: EconomyState) -> pd.DataFrame:
    """Export an `EconomyState`'s market stats to a DataFrame.

    Args:
        eco: The `EconomyState` to export (as produced by
            `solve`).

    Returns:
        A ``DataFrame`` with columns ``"goods"``, ``"market_prices"``,
        ``"market_prices_variance"``, ``"sell_orders"``, ``"buy_orders"``,
        ``"building_goods_input"``, ``"building_goods_output"``,
        ``"imports"``, ``"exports"`` and ``"pop_needs"``, filtered to goods
        with non-zero ``sell_orders`` or ``buy_orders`` and sorted by
        ``"sell_orders"`` descending.
    """
    df = pd.DataFrame(
        {
            "goods": economy.goods_index,
            "market_prices": eco.market_prices,
            "market_prices_variance": economy.market_prices_variance(eco),
            "sell_orders": eco.sell_orders,
            "buy_orders": eco.buy_orders,
            "building_goods_input": eco.building_goods_input,
            "building_goods_output": eco.building_goods_output,
            "imports": eco.imports,
            "exports": eco.exports,
            "pop_needs": eco.pop_needs,
        }
    )
    df = df[(df["sell_orders"] > 0) | (df["buy_orders"] > 0)].copy()
    df = df.sort_values(by="sell_orders", ascending=False)  # pyright: ignore[reportCallIssue]
    return df


def df_pop(economy: Economy, eco: EconomyState) -> pd.DataFrame:
    """Export an `EconomyState`'s pop employment and wealth to a DataFrame.

    Each row describes one profession, aggregating the per-building arrays
    in *eco*.

    Args:
        eco: The `EconomyState` to export (as produced by
            `solve`).

    Returns:
        A ``DataFrame`` with columns ``"profession"``, ``"employment"``,
        ``"employment_share"``, ``"dependents"``, ``"population"``,
        ``"avg_wealth"``, ``"total_wealth"`` and
        ``"pop_balance"``, filtered to professions with non-zero employment
        and sorted by ``"employment"`` descending.
    """
    df = pd.DataFrame(
        {
            "profession": economy.pop_index,
            "employment": eco.employment_by_profession,
            "employment_share": eco.profession_shares,
            "dependents": eco.employment_by_profession * eco.dependents_per_worker,
            "population": eco.employment_by_profession / eco.workforce_ratio,
            "avg_wealth": eco.wealth_by_profession,
            "total_wealth": (eco.pop_wealth * eco.pops).sum(axis=0)
            / eco.workforce_ratio,
            "pop_balance": (
                eco.pop_balance.sum(axis=0)
                if eco.pop_balance is not None
                else np.full(len(economy.pop_index), np.nan)
            ),
        }
    )
    df = df[df["employment"] > 0].copy()
    df = df.sort_values(by="employment", ascending=False).reset_index(drop=True)  # pyright: ignore[reportCallIssue]
    return df
