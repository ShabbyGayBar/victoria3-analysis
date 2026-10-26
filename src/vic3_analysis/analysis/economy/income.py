# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Cooperative income and dependent earnings."""

from __future__ import annotations

from dataclasses import dataclass
from typing import TYPE_CHECKING

import numpy as np

from vic3_analysis.analysis.economy._utils import (
    _nonnegative_values,
    _readonly_array,
    _readonly_wealth,
    _require_columns,
    _validate_index_keys,
)
from vic3_analysis.analysis.economy.states import (
    EconomyContext,
    EconomyState,
)

if TYPE_CHECKING:
    from vic3_analysis.analysis.economy.model import Economy


@dataclass
class _PopIncomeCoefficients:
    """Fixed cooperative shares, recipient totals, and weekly dependent earnings."""

    shares: np.ndarray
    totals: np.ndarray
    dependent_income: np.ndarray


def pop_wealth_init(economy: Economy) -> np.ndarray:
    """Return read-only int64 starting wealth aligned to `pop_index`."""
    return _readonly_wealth(
        economy.df_pop_types["start_quality_of_life"].to_numpy(), "pop_wealth_init"
    )


def pop_wage_weights(economy: Economy) -> np.ndarray:
    """Return all professions' cooperative wage weights in pop_index order."""
    _require_columns(economy.df_pop_types, {"key", "wage_weight"}, "df_pop_types")
    _validate_index_keys(economy.pop_index, "pop_index")
    return _readonly_array(
        _nonnegative_values(
            economy.df_pop_types["wage_weight"].to_numpy(), "wage_weight"
        )
    )


def calculate_pop_income(economy: Economy, state: EconomyState) -> np.ndarray:
    """Return cooperative employee income plus exogenous dependent earnings.

    Each configuration distributes all of its positive ``building_surplus``
    in proportion to ``state.pops * wage_weight``. Every profession is
    included regardless of ``paid_private_wage``; zero weights receive no
    cooperative income. Configurations are independent, including those of the same
    building type. Losses pay zero cooperative wages and remain visible
    through ``state.building_deficit``, without implicit financing.
    Add ``pops * dependents_per_worker * dependent_wage / 52`` for household
    dependent earnings; missing annual dependent wages default to zero.

    Args:
        state: Snapshot aligned to this economy's configuration, goods, and
            profession indexes. Stored signed flows and market prices are
            authoritative; production and throughput are not reconstructed.

    Returns:
        A fresh writable float64 matrix shaped like ``state.pops`` containing
        total household income in £ per week for each configuration-profession
        group, rather than per-worker rates. The state and model tables are unchanged.

    Raises:
        ValueError: If relevant arrays are misaligned or non-finite, prices,
            populations, or wage weights are negative, profession keys are
            invalid, wage weights are missing, used dependent wages are invalid,
            calculated income is non-finite, or a configuration has positive
            surplus but no positive recipient weight.

    Notes:
        This is a simplified worker-cooperative accounting policy. It does
        not apply taxes, transfers, subsistence income, reserves, or household
        expenses, and does not change wealth or ``pop_balance``. Dependent
        earnings do not reduce building surplus or increase production GDP.
    """
    economy._validate_goods_vector(state.market_prices, "state.market_prices")
    return economy._pop_income_at_prices(
        state.context, state.market_prices, economy._prepare_pop_income(state.context)
    )


def _prepare_pop_income(
    economy: Economy, context: EconomyContext
) -> _PopIncomeCoefficients:
    """Compile price-independent cooperative shares and dependent earnings once."""
    weights = economy.pop_wage_weights
    economy._validate_building_goods_flow(context)
    pops = economy._validate_worker_counts(context)
    with np.errstate(over="ignore", invalid="ignore"):
        weighted = _nonnegative_values(pops * weights, "weighted population")
        totals = _nonnegative_values(weighted.sum(axis=1), "total wage weight")
    shares = np.divide(
        weighted,
        totals[:, None],
        out=np.zeros_like(weighted),
        where=totals[:, None] > 0,
    )
    dependent_income = np.zeros_like(pops)
    if context.dependents_per_worker > 0 and "dependent_wage" in economy.df_pop_types:
        used = (pops > 0).any(axis=0)
        wages = np.zeros(len(economy.pop_index), dtype=np.float64)
        wages[used] = _nonnegative_values(
            economy.df_pop_types["dependent_wage"].fillna(0).to_numpy()[used],
            "dependent_wage",
        )
        with np.errstate(over="ignore", invalid="ignore"):
            dependent_income = _nonnegative_values(
                pops * context.dependents_per_worker * (wages / 52),
                "calculated pop_income",
            )
    return _PopIncomeCoefficients(shares, totals, dependent_income)


def _pop_income_at_prices(
    economy: Economy,
    context: EconomyContext,
    prices: np.ndarray,
    coefficients: _PopIncomeCoefficients,
) -> np.ndarray:
    """Allocate changing surplus using fixed income coefficients."""
    with np.errstate(over="ignore", invalid="ignore"):
        surplus = context.building_goods_flow @ prices
    if not np.isfinite(surplus).all():
        raise ValueError("state.building_surplus must contain finite values.")
    missing = (surplus > 0) & (coefficients.totals == 0)
    if missing.any():
        keys = [economy.building_index[i] for i in np.flatnonzero(missing)]
        raise ValueError(
            f"Positive surplus has no positive recipient weight for: {keys}"
        )
    with np.errstate(over="ignore", invalid="ignore"):
        return _nonnegative_values(
            coefficients.shares * np.maximum(surplus, 0)[:, None]
            + coefficients.dependent_income,
            "calculated pop_income",
        )
