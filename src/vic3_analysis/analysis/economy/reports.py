# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""DataFrame reports for complete economy snapshots."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

from vic3_analysis.analysis.economy.states import (
    EconomyContext,
    EconomyState,
    GoodsBuyPackages,
)

if TYPE_CHECKING:
    from vic3_analysis.analysis.economy.model import Economy


def df_goods_buy_packages(
    economy: Economy, source: EconomyState | EconomyContext | GoodsBuyPackages
) -> pd.DataFrame:
    """Export standard goods baskets as an independent, mutable DataFrame.

    Args:
        source: A snapshot or context from which to calculate or reuse baskets,
            or immutable `GoodsBuyPackages` with columns in `goods_index` order.

    Returns:
        A fresh DataFrame with ascending int64 index named ``wealth`` and
        float64 goods quantities in `goods_index` column order. Quantities
        are weekly units per 10,000 standard workers. Both data and labels
        are copied; editing the report does not modify its source.

    Raises:
        TypeError: If source is not a state, context, or `GoodsBuyPackages`.
        ValueError: If goods alignment or basket calculation is invalid.
    """
    if isinstance(source, GoodsBuyPackages):
        packages = source
        economy._validate_goods_buy_packages(packages)
    elif isinstance(source, (EconomyState, EconomyContext)):
        packages = economy.goods_buy_packages(source)
    else:
        raise TypeError(
            "source must be an EconomyState, EconomyContext, or GoodsBuyPackages."
        )
    return pd.DataFrame(
        packages.quantities,
        index=pd.Index(packages.wealth, name="wealth", copy=True),
        columns=list(economy.goods_index),
        copy=True,
    )


def df_buildings(economy: Economy, state: EconomyState) -> pd.DataFrame:
    """Export an `EconomyState`'s building registry to a DataFrame.

    Args:
        state: The `EconomyState` to export (as produced by
            `solve`).

    Returns:
        A ``DataFrame`` with columns ``"key"``, ``"level"`` and
        ``"construction_cost"``, filtered to non-zero levels and sorted by
        ``"level"`` descending.
    """
    df = pd.DataFrame(
        {
            "key": economy.building_index,
            "level": state.building_levels,
            "construction_cost": economy.construction_cost_vector
            * state.building_levels,
        }
    )
    df = df[df["level"] > 0].copy()
    df = df.sort_values(by="level", ascending=False)  # pyright: ignore[reportCallIssue]
    return df


def df_market(economy: Economy, state: EconomyState) -> pd.DataFrame:
    """Export an `EconomyState`'s market stats to a DataFrame.

    Args:
        state: The `EconomyState` to export (as produced by
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
            "market_prices": state.market_prices,
            "market_prices_variance": economy.market_prices_variance(state),
            "sell_orders": state.sell_orders,
            "buy_orders": state.buy_orders,
            "building_goods_input": state.building_goods_input,
            "building_goods_output": state.building_goods_output,
            "imports": state.imports,
            "exports": state.exports,
            "pop_needs": state.pop_needs,
        }
    )
    df = df[(df["sell_orders"] > 0) | (df["buy_orders"] > 0)].copy()
    df = df.sort_values(by="sell_orders", ascending=False)  # pyright: ignore[reportCallIssue]
    return df


def df_pop(economy: Economy, state: EconomyState) -> pd.DataFrame:
    """Export an `EconomyState`'s pop employment and wealth to a DataFrame.

    Each row describes one profession, aggregating the per-building arrays
    in *state*.

    Args:
        state: The `EconomyState` to export (as produced by
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
            "employment": state.employment_by_profession,
            "employment_share": state.profession_shares,
            "dependents": state.employment_by_profession * state.dependents_per_worker,
            "population": state.employment_by_profession / state.workforce_ratio,
            "avg_wealth": state.average_wealth_by_profession,
            "total_wealth": state.total_wealth_by_profession / state.workforce_ratio,
            "pop_balance": (
                state.pop_balance.sum(axis=0)
                if state.pop_balance is not None
                else np.full(len(economy.pop_index), np.nan)
            ),
        }
    )
    df = df[df["employment"] > 0].copy()
    df = df.sort_values(by="employment", ascending=False).reset_index(drop=True)  # pyright: ignore[reportCallIssue]
    return df
