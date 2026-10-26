# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Market prices and nominal/market snapshot construction."""

from __future__ import annotations

from dataclasses import replace
from typing import TYPE_CHECKING

import numpy as np

from vic3_analysis.analysis.economy.states import (
    EconomyContext,
    EconomyState,
    MarketState,
    PopState,
)

if TYPE_CHECKING:
    from vic3_analysis.analysis.economy.model import Economy


def market_prices_variance(economy: Economy, state: EconomyState) -> np.ndarray:
    """Calculate the market prices variance from base prices.

    Args:
        state: The `EconomyState` to evaluate (as produced by
            `solve`).

    Returns:
        A 1-D array of shape ``(n_goods,)`` containing the market prices variance.
    """
    return (state.market_prices / economy.base_prices - 1) * 100


def market_prices(
    economy: Economy,
    buy_orders: np.ndarray[tuple[int], np.dtype[np.float64]],
    sell_orders: np.ndarray[tuple[int], np.dtype[np.float64]],
) -> np.ndarray:
    """Calculate market prices from buy and sell orders.

    Args:
        buy_orders: 1-D array of non-negative buy orders aligned to the
            goods table.
        sell_orders: 1-D array of non-negative sell orders aligned to the
            goods table.

    Returns:
        A float64 array of prices aligned to `goods_index`.

    Raises:
        ValueError: If either input is not a 1-D goods-aligned array, does
            not contain finite values, or contains negative values.
    """
    buy_orders = economy._validate_goods_vector(buy_orders, "buy_orders")
    sell_orders = economy._validate_goods_vector(sell_orders, "sell_orders")

    base_prices = economy.base_prices
    prices = base_prices.copy()
    shared = np.minimum(buy_orders, sell_orders)
    mask = shared > 0
    if mask.any():
        ratio = (buy_orders[mask] - sell_orders[mask]) / shared[mask]
        prices[mask] = base_prices[mask] * (1 + 0.75 * np.clip(ratio, -1, 1))
    buy_only = (buy_orders > 0) & (sell_orders == 0)
    sell_only = (sell_orders > 0) & (buy_orders == 0)
    prices[buy_only] = base_prices[buy_only] * 1.75
    prices[sell_only] = base_prices[sell_only] * 0.25
    return prices.astype(np.float64, copy=False)


def _solve_nominal(
    economy: Economy,
    building_levels: np.ndarray[tuple[int], np.dtype[np.float64]],
    goods_trade_flow: np.ndarray[tuple[int], np.dtype[np.float64]],
    throughput_multipliers: (np.ndarray[tuple[int], np.dtype[np.float64]] | None),
    pop_needs: np.ndarray[tuple[int], np.dtype[np.float64]],
    *,
    workforce_ratio: float = 1.0,
) -> EconomyState:
    """Derive a nominal `EconomyState` from a building-level vector.

    Uses base (nominal) goods prices, gross goods output for supply, gross
    goods input plus supplied population needs for demand, per-profession
    employment, and per-profession
    ``start_quality_of_life`` for wealth.

    Args:
        building_levels: 1-D array of shape ``(n_buildings,)``.
        goods_trade_flow: Signed 1-D array of shape ``(n_goods,)``;
            positive values import goods, negative values export goods.
        throughput_multipliers: Optional per-configuration multipliers for
            gross goods inputs and outputs.
        pop_needs: 1-D array of goods-aligned population needs demand.
        workforce_ratio: Economy-wide workers / total population.

    Returns:
        An `EconomyState` with prices, supply, demand, employment,
        and wealth derived from *building_levels*.
    """
    goods_input_matrix = economy.goods_input_matrix(throughput_multipliers)
    goods_output_matrix = economy.goods_output_matrix(throughput_multipliers)
    building_goods_flow = building_levels[:, None] * (
        goods_output_matrix - goods_input_matrix
    )
    pops = building_levels[:, None] * economy.employment_matrix

    context = EconomyContext(
        building_levels=building_levels,
        building_goods_flow=building_goods_flow,
        goods_trade_flow=goods_trade_flow,
        pops=pops,
        workforce_ratio=workforce_ratio,
    )
    return EconomyState(
        context=context,
        market=MarketState(context=context, market_prices=economy.base_prices),
        households=PopState(
            pop_wealth=np.broadcast_to(economy.pop_wealth_init, pops.shape),
            pop_needs=pop_needs,
        ),
    )


def _solve_market(
    economy: Economy,
    building_levels: np.ndarray[tuple[int], np.dtype[np.float64]],
    goods_trade_flow: np.ndarray[tuple[int], np.dtype[np.float64]],
    throughput_multipliers: (np.ndarray[tuple[int], np.dtype[np.float64]] | None),
    pop_needs: np.ndarray[tuple[int], np.dtype[np.float64]],
    *,
    workforce_ratio: float = 1.0,
) -> EconomyState:
    """Derive a market-price `EconomyState` from a building vector."""
    state = economy._solve_nominal(
        building_levels,
        goods_trade_flow,
        throughput_multipliers,
        pop_needs,
        workforce_ratio=workforce_ratio,
    )
    return replace(
        state,
        market=MarketState(
            context=state.context,
            market_prices=economy.market_prices(state.buy_orders, state.sell_orders),
        ),
    )
