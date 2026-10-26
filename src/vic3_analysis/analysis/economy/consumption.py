# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Household baskets, demand, and expenses."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

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


@dataclass(frozen=True)
class _PopNeedsCoefficients:
    """Cached arrays indexed by wealth, need category, or good."""

    wealth_levels: np.ndarray
    packages: np.ndarray
    eligible: np.ndarray
    weights: np.ndarray
    min_shares: np.ndarray
    max_shares: np.ndarray
    defaults: np.ndarray


def _pop_needs_coefficients(economy: Economy) -> _PopNeedsCoefficients:
    """Validate and compile model tables once for repeated demand updates."""
    packages = economy.df_buy_packages
    needs = economy.df_pop_needs
    _require_columns(packages, {"wealth"}, "df_buy_packages")
    _require_columns(
        needs,
        {
            "key",
            "goods",
            "weight",
            "min_supply_share",
            "max_supply_share",
            "is_default",
        },
        "df_pop_needs",
    )
    categories = [
        c for c in packages.columns if isinstance(c, str) and c.startswith("popneed_")
    ]
    wealth = _readonly_wealth(packages["wealth"].to_numpy(), "df_buy_packages.wealth")
    if (
        not len(wealth)
        or not categories
        or (wealth == 0).any()
        or len(np.unique(wealth)) != len(wealth)
    ):
        raise ValueError(
            "df_buy_packages must define unique positive wealth tiers and popneed_ columns."
        )
    order = np.argsort(wealth)
    values = _nonnegative_values(
        packages[categories].to_numpy(), "df_buy_packages need values"
    )[order]
    _validate_index_keys(economy.goods_index, "goods_index")
    if any(not isinstance(key, str) or not key for key in needs["key"].tolist()):
        raise ValueError("df_pop_needs.key must contain non-empty category keys.")
    goods_positions = {key: j for j, key in enumerate(economy.goods_index)}
    shape = (len(categories), len(economy.goods_index))
    eligible = np.zeros(shape, dtype=np.float64)
    weights = np.zeros(shape, dtype=np.float64)
    minima = np.zeros(shape, dtype=np.float64)
    maxima = np.zeros(shape, dtype=np.float64)
    defaults = np.zeros(shape, dtype=np.float64)
    for i, category in enumerate(categories):
        entries = needs.loc[needs["key"] == category]
        keys = entries["goods"].tolist()
        if (
            not keys
            or len(set(keys)) != len(keys)
            or any(key not in goods_positions for key in keys)
        ):
            raise ValueError(
                f"df_pop_needs {category} must reference unique goods in goods_index."
            )
        flags = entries["is_default"]
        if (
            not flags.isin([True, False]).all()
            or flags.isna().any()
            or flags.sum() != 1
        ):
            raise ValueError(
                f"df_pop_needs {category} must define exactly one default good."
            )
        coefficients = _nonnegative_values(
            entries[["weight", "min_supply_share", "max_supply_share"]].to_numpy(),
            f"df_pop_needs {category}",
        )
        if (coefficients[:, 1] > coefficients[:, 2]).any() or (
            coefficients[:, 2] > 1
        ).any():
            raise ValueError(
                f"df_pop_needs {category} shares must satisfy 0 <= min <= max <= 1."
            )
        positions = [goods_positions[key] for key in keys]
        eligible[i, positions] = 1
        weights[i, positions] = coefficients[:, 0]
        minima[i, positions] = coefficients[:, 1]
        maxima[i, positions] = coefficients[:, 2]
        defaults[i, positions] = flags.to_numpy(dtype=np.float64)
    return _PopNeedsCoefficients(
        wealth_levels=_readonly_wealth(wealth[order], "df_buy_packages.wealth"),
        packages=_readonly_array(values),
        eligible=_readonly_array(eligible),
        weights=_readonly_array(weights),
        min_shares=_readonly_array(minima),
        max_shares=_readonly_array(maxima),
        defaults=_readonly_array(defaults),
    )


def _pop_consumption_multipliers(economy: Economy) -> np.ndarray:
    """Return validated profession multipliers for aggregate population demand."""
    _validate_index_keys(economy.pop_index, "pop_index")
    if "consumption_mult" in economy.df_pop_types:
        consumption = economy.df_pop_types["consumption_mult"].fillna(1).to_numpy()
    else:
        consumption = np.ones(len(economy.pop_index), dtype=np.float64)
    return _readonly_array(_nonnegative_values(consumption, "consumption_mult"))


def _pop_need_purchase_shares(
    economy: Economy, state: EconomyState | EconomyContext
) -> tuple[np.ndarray, np.ndarray]:
    """Return category-by-goods purchase shares and validated base prices."""
    economy._validate_building_goods_flow(state)
    for name in (
        "building_goods_input",
        "building_goods_output",
    ):
        economy._validate_goods_vector(getattr(state, name), f"state.{name}")
    economy._validate_goods_vector(
        state.goods_trade_flow, "state.goods_trade_flow", nonnegative=False
    )
    supply = economy._validate_goods_vector(state.sell_orders, "state.sell_orders")
    prices = _nonnegative_values(economy.base_prices, "base_prices")
    if (prices == 0).any():
        raise ValueError("base_prices must be strictly positive.")
    data = economy._pop_needs_coefficients
    effective = np.maximum(
        supply - 0.5 * state.building_goods_input - 0.5 * state.exports, 0
    )
    shares = data.eligible * effective
    totals = shares.sum(axis=1, keepdims=True)
    np.divide(shares, totals, out=shares, where=totals > 0)
    purchases = np.clip(shares, data.min_shares, data.max_shares) * data.weights
    totals = purchases.sum(axis=1, keepdims=True)
    np.divide(purchases, totals, out=purchases, where=totals > 0)
    return np.where(totals > 0, purchases, data.defaults), prices


def prepare_context(economy: Economy, context: EconomyContext) -> EconomyContext:
    """Return a context with reusable baskets and consumption scales.

    Compute only missing prepared fields. Existing fields are authoritative;
    a fully prepared context is returned unchanged. No household wealth,
    demand, prices, or finances are evaluated. Clear affected fields before
    refreshing changed production, trade, or population assumptions.
    """
    if context.buy_packages is not None and context.consumption_scales is not None:
        return context
    changes: dict[str, np.ndarray] = {}
    if context.buy_packages is None:
        packages = economy.calculate_buy_packages(context)
        changes["buy_packages"] = packages.to_numpy()
        changes["buy_package_wealth"] = packages.index.to_numpy()
    if context.consumption_scales is None:
        changes["consumption_scales"] = economy.calculate_pop_consumption_scales(
            context
        )
    return replace(context, **changes)


def calculate_buy_packages(
    economy: Economy, state: EconomyState | EconomyContext
) -> pd.DataFrame:
    """Calculate weekly goods packages per 10,000 standard workers by wealth.

    Convert the model's wealth-by-category values to goods quantities using
    the supplied state's substitution shares and the model's base prices:
    ``wealth_category_values @ category_purchase_shares / base_prices``.
    Substitution uses effective supply, configured weights, minimum/maximum
    supply shares, and default goods as described by `calculate_pop_needs`.

    Args:
        state: Snapshot or context aligned to this economy. Prepared
            context baskets are copied when present; otherwise only
            building inputs/outputs, imports, and exports are used.

    Returns:
        An independent, mutable DataFrame with an ascending int64 index
        named ``wealth``. Prepared context tiers are authoritative;
        otherwise it contains every tier in ``df_buy_packages``.
        Columns are all good keys in `goods_index` order, with float64
        values in goods units per week per 10,000 standard workers.
        Unconsumed goods have zero values. Neither the state nor model
        tables are modified.

    Raises:
        ValueError: If goods flows are misaligned, negative, or non-finite,
            base prices are not positive, or package/substitution
            definitions are invalid or reference missing categories/goods.

    Notes:
        Packages are independent of represented population, workforce ratio,
        occupied wealth, profession consumption multipliers, market prices,
        and existing population demand. Culture, prestige goods, local-state
        effects, and weekly adjustment are not modeled.
        Subtracting half of non-pop demand from supply is community-derived,
        documented by the Needs wiki rather than game-file comments.
        Clamping negative effective supply to zero is a model convention.

    References:
        - ``common/buy_packages/00_buy_packages.txt``: category values by
          integer wealth.
        - ``common/pop_needs/00_pop_needs.txt``: substitution weights,
          supply-share limits, and default goods.
        - [Needs wiki, Formulas](https://vic3.paradoxwikis.com/Needs#Formulas):
          scaling per 10,000 workers and substitution, including the
          community-derived half-non-pop-demand deduction.
        - [Official developer diary #13](https://steamcommunity.com/games/529340/announcements/detail/2965045886379003737):
          wealth-dependent needs and valuation at goods' base prices.
    """
    context = state.context if isinstance(state, EconomyState) else state
    if context.buy_packages is not None and context.buy_package_wealth is not None:
        tiers = context.buy_package_wealth
        values = economy._select_prepared_buy_packages(
            context.buy_packages, tiers, tiers
        )
    else:
        purchases, prices = economy._pop_need_purchase_shares(context)
        data = economy._pop_needs_coefficients
        tiers = data.wealth_levels
        values = _nonnegative_values(
            data.packages @ purchases / prices, "calculated buy_packages"
        )
    return pd.DataFrame(
        values,
        index=pd.Index(tiers, name="wealth", copy=True),
        columns=list(economy.goods_index),
        copy=True,
    )


def calculate_pop_consumption_scales(
    economy: Economy, state: EconomyState | EconomyContext
) -> np.ndarray:
    """Return household consumption as multiples of a standard buy package.

    Calculate ``pops / 10_000 * consumption_mult * (1 + 0.5 *
    dependents_per_worker)``. Missing profession multipliers default to one.
    Workers and dependents share a wealth tier; dependents consume half as
    much per person. Wealth values, prices, and goods flows are not used.

    Args:
        state: Snapshot or context with aligned worker counts. Prepared
            context scales are copied when present. Snapshot wealth must
            also have the population shape.

    Returns:
        A fresh, owned, writable float64 matrix aligned to configurations
        and professions. Values are dimensionless multiples of weekly
        goods packages per 10,000 standard workers. Reuse them while worker
        counts, workforce ratio, and profession multipliers remain fixed.
        The state and model tables are unchanged.

    Raises:
        ValueError: If household shapes, worker counts, profession keys,
            or consumption multipliers are invalid, or scales overflow.
    """
    pops = economy._validate_worker_counts(state)
    context = state.context if isinstance(state, EconomyState) else state
    if context.consumption_scales is not None:
        return context.consumption_scales.copy()
    with np.errstate(over="ignore", invalid="ignore"):
        scales = (
            pops
            / 10_000
            * economy._pop_consumption_multipliers
            * (1.0 + 0.5 * state.dependents_per_worker)
        )
    return _nonnegative_values(scales, "calculated consumption_scales")


def _prepare_pop_consumption(
    economy: Economy, state: EconomyState, consumption_scales: np.ndarray | None
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Return occupied cells, unique wealth, inverse labels, and cell scales."""
    pops = economy._validate_worker_counts(state)
    occupied = pops > 0
    if consumption_scales is None:
        consumption_scales = state.context.consumption_scales
    if consumption_scales is None:
        scales = economy.calculate_pop_consumption_scales(state)
    else:
        scales = _nonnegative_values(consumption_scales, "consumption_scales")
        if scales.shape != pops.shape:
            raise ValueError("consumption_scales shape must match state.pops.")
        if (scales[~occupied] != 0).any():
            raise ValueError("consumption_scales must be zero for empty cells.")
    return _group_pop_consumption(pops, state.pop_wealth, scales)


def _group_pop_consumption(
    pops: np.ndarray, pop_wealth: np.ndarray, scales: np.ndarray
) -> tuple[np.ndarray, np.ndarray, np.ndarray, np.ndarray]:
    """Group validated occupied cells by wealth without constructing a state."""
    occupied = pops > 0
    wealth, inverse = np.unique(pop_wealth[occupied], return_inverse=True)
    return occupied, wealth, inverse, scales[occupied]


def _wealth_positions(
    tiers: np.ndarray, wealth: np.ndarray, name: str = "buy_packages"
) -> np.ndarray:
    """Locate occupied wealth in sorted, unique tiers after checking coverage."""
    if not np.isin(wealth, tiers).all():
        raise ValueError(f"Occupied pop_wealth tiers must be defined in {name}.")
    return np.searchsorted(tiers, wealth)


def _select_pop_buy_packages(
    economy: Economy, buy_packages: pd.DataFrame, wealth: np.ndarray
) -> np.ndarray:
    """Validate supplied baskets and select rows for occupied wealth tiers."""
    _require_columns(buy_packages, set(economy.goods_index), "buy_packages")
    if len(buy_packages.columns) != len(economy.goods_index):
        raise ValueError("buy_packages columns must match goods_index exactly.")
    tiers = _readonly_wealth(buy_packages.index.to_numpy(), "buy_packages index")
    if (tiers == 0).any() or len(np.unique(tiers)) != len(tiers):
        raise ValueError(
            "buy_packages index must contain unique positive wealth tiers."
        )
    values = _nonnegative_values(
        buy_packages.loc[:, list(economy.goods_index)].to_numpy(),
        "buy_packages quantities",
    )
    order = np.argsort(tiers)
    return values[order[_wealth_positions(tiers[order], wealth)]]


def _select_prepared_buy_packages(
    economy: Economy, values: np.ndarray, tiers: np.ndarray, wealth: np.ndarray
) -> np.ndarray:
    """Select prepared baskets without materializing a DataFrame."""
    if values.shape[1] != len(economy.goods_index):
        raise ValueError("Prepared buy_packages columns must match goods_index.")
    return values[_wealth_positions(tiers, wealth)]


def _select_consumption_baskets(
    economy: Economy,
    state: EconomyState,
    wealth: np.ndarray,
    buy_packages: pd.DataFrame | None,
) -> np.ndarray | None:
    """Select explicit or prepared baskets, leaving raw calculation to callers."""
    if buy_packages is not None:
        return economy._select_pop_buy_packages(buy_packages, wealth)
    context = state.context
    if context.buy_packages is not None and context.buy_package_wealth is not None:
        return economy._select_prepared_buy_packages(
            context.buy_packages, context.buy_package_wealth, wealth
        )
    return None


def _pop_demand_from_baskets(
    selected: np.ndarray, inverse: np.ndarray, scales: np.ndarray
) -> np.ndarray:
    """Aggregate household scales before allocating their selected baskets."""
    with np.errstate(over="ignore", invalid="ignore"):
        counts = np.bincount(inverse, weights=scales, minlength=len(selected))
        return counts @ selected


def _pop_expenses_at_prices(
    occupied: np.ndarray,
    inverse: np.ndarray,
    scales: np.ndarray,
    selected: np.ndarray,
    prices: np.ndarray,
) -> np.ndarray:
    """Price selected baskets and allocate costs to validated occupied cells."""
    expenses = np.zeros(occupied.shape, dtype=np.float64)
    with np.errstate(over="ignore", invalid="ignore"):
        costs = _nonnegative_values(selected @ prices, "calculated basket costs")
        expenses[occupied] = scales * costs[inverse]
    return _nonnegative_values(expenses, "calculated pop_expenses")


def calculate_pop_needs(
    economy: Economy,
    state: EconomyState,
    *,
    buy_packages: pd.DataFrame | None = None,
    consumption_scales: np.ndarray | None = None,
) -> np.ndarray:
    """Calculate target weekly goods demand for the represented workers.

    Prepared context baskets and scales are reused when their explicit
    arguments are omitted. Without prepared baskets, each need category's
    effective supply is
    ``max(sell_orders - 0.5 * (building_goods_input + exports), 0)``.
    Divide each eligible good's effective supply by the category total,
    clip that share to its configured minimum and maximum, multiply by
    its configured weight, and normalize these purchase weights. Share
    limits apply before normalization; they do not cap final purchases.
    With zero effective supply, start from zero shares, retaining any
    configured minimum shares. If all purchase weights are zero, use the
    category's default good exclusively.

    Each occupied cell's integer wealth selects a buy package, whose
    category values are measured in pounds at base prices per 10,000
    workers. Multiply worker counts by ``1 + 0.5 * dependents_per_worker``,
    scale by ``consumption_mult / 10_000``, distribute by
    normalized purchase weights, and divide by goods' base prices to
    obtain units per week. Category budgets are aggregated before goods
    allocation, without a building-by-profession-by-goods tensor.

    Args:
        state: Snapshot aligned to this economy's building, profession,
            and goods indexes. Workers and their dependents consume at the
            same wealth tier; dependents consume half as much per person.
            Empty cells need no wealth package.
        buy_packages: Optional weekly goods quantities per 10,000 standard
            workers, as returned by `calculate_buy_packages`. The index must
            contain unique positive integer wealth tiers, including every
            occupied tier; its name is ignored. Columns must contain exactly
            `goods_index`, in any order. Values must be finite and
            non-negative. Supplied baskets are scaled directly by worker-
            equivalent population and profession consumption multipliers,
            without substitution or base-price conversion, and remain fixed
            when supply changes.
            Unused state goods flows and raw need/package tables are not
            validated in this mode. The table is unchanged.
        consumption_scales: Optional precomputed matrix returned by
            `calculate_pop_consumption_scales`. Supplied values are
            authoritative, finite, non-negative, and shaped like ``pops``;
            empty cells must have zero scale. They already include all
            population factors, so profession multipliers are not read or
            reapplied. The caller ensures scales remain valid for the
            population assumptions. The matrix is unchanged.

    Returns:
        A fresh writable float64 vector of shape ``(n_goods,)`` aligned
        to `goods_index`, suitable for ``EconomyState.pop_needs`` or the
        ``pop_needs`` argument to `solve`. The state is unchanged.

    Raises:
        ValueError: If relevant state arrays are misaligned, quantities
            are negative or non-finite, base prices are not positive,
            occupied wealth tiers are undefined, or model tables have
            invalid definitions or missing category/goods references. Also
            raised for invalid supplied package labels, quantities, or
            consumption scales, or non-finite calculated demand.

    Notes:
        The half-non-pop-demand deduction is community-derived and
        documented by the Needs wiki; it is not confirmed by the comments
        in the game files. Clamping negative effective supply to zero is
        this model's convention. This is target consumption, without
        weekly adjustment, culture, prestige goods, local-state effects,
        demographic changes, or wealth feedback. Market prices and
        existing ``state.pop_needs`` do not influence the result.

    References:
        - ``common/pop_needs/00_pop_needs.txt``: substitution weights,
          minimum/maximum supply shares, comments on their meaning, and
          default goods.
        - ``common/buy_packages/00_buy_packages.txt``: category values
          indexed by integer wealth.
        - ``common/pop_types/``: profession ``consumption_mult`` values.
        - [Needs wiki, Formulas](https://vic3.paradoxwikis.com/Needs#Formulas):
          population scaling and detailed substitution formulas. The
          non-pop-demand deduction is attributed there to community
          reverse engineering:
          https://www.reddit.com/r/victoria3/comments/yudc80/pop_needs_consumer_good_substitution_and_why_oil/
        - [Official developer diary #13](https://steamcommunity.com/games/529340/announcements/detail/2965045886379003737):
          wealth-dependent needs and valuation using goods' base prices.
    """
    _, wealth, inverse, scales = economy._prepare_pop_consumption(
        state, consumption_scales
    )
    selected = _select_consumption_baskets(economy, state, wealth, buy_packages)
    with np.errstate(over="ignore", invalid="ignore"):
        if selected is not None:
            demand = _pop_demand_from_baskets(selected, inverse, scales)
        else:
            counts = np.bincount(inverse, weights=scales, minlength=len(wealth))
            purchases, prices = economy._pop_need_purchase_shares(state)
            data = economy._pop_needs_coefficients
            budgets = (
                counts
                @ data.packages[
                    _wealth_positions(data.wealth_levels, wealth, "df_buy_packages")
                ]
            )
            demand = budgets @ purchases / prices
    return economy._validate_goods_vector(demand, "calculated pop_needs")


def calculate_pop_expenses(
    economy: Economy,
    state: EconomyState,
    *,
    buy_packages: pd.DataFrame | None = None,
    consumption_scales: np.ndarray | None = None,
) -> np.ndarray:
    """Return weekly household expenses for target goods consumption.

    Value each occupied wealth tier's standard goods basket at the state's
    market prices, then multiply by its household consumption scale. This
    uses the same baskets and scales as `calculate_pop_needs`, without a
    configuration-by-profession-by-goods tensor.

    Args:
        state: Snapshot with aligned household matrices, finite non-negative
            worker counts, and finite non-negative goods-aligned market
            prices. Zero prices are valid. Empty cells need no wealth basket.
        buy_packages: Optional goods baskets with the same contract as in
            `calculate_pop_needs`. When omitted, reuse prepared context
            baskets or call `calculate_buy_packages(state)`. Supplied baskets
            bypass unused goods flows, base prices, and raw needs/package
            definitions.
        consumption_scales: Optional authoritative precomputed household
            scales, with the same contract as in `calculate_pop_needs`.
            When omitted, reuse context scales or calculate them.

    Returns:
        A fresh, owned, writable float64 matrix shaped like ``state.pops``
        containing household totals in pounds per week. Empty cells have
        zero expenses. Inputs, model tables, and ``pop_balance`` are unchanged.

    Raises:
        ValueError: If relevant state inputs, baskets, or scales are invalid,
            occupied tiers are undefined, or calculated costs are non-finite.

    Notes:
        Expenses price target consumption without affordability restrictions,
        rationing, taxes, or wealth transitions. Prices affect expenses but
        do not affect the basket quantities or consumption scales.
    """
    occupied, wealth, inverse, scales = economy._prepare_pop_consumption(
        state, consumption_scales
    )
    prices = economy._validate_goods_vector(state.market_prices, "state.market_prices")
    selected = _select_consumption_baskets(economy, state, wealth, buy_packages)
    if selected is None:
        selected = economy._select_pop_buy_packages(
            economy.calculate_buy_packages(state), wealth
        )
    return _pop_expenses_at_prices(occupied, inverse, scales, selected, prices)


def _prepared_consumption(
    context: EconomyContext,
) -> tuple[np.ndarray, np.ndarray, np.ndarray]:
    """Require the prepared arrays needed by wealth iteration."""
    if (
        context.buy_packages is None
        or context.buy_package_wealth is None
        or context.consumption_scales is None
    ):
        raise ValueError(
            "Prepared baskets and consumption_scales are required; use evaluate_wealth()."
        )
    return (
        context.buy_packages,
        context.buy_package_wealth,
        context.consumption_scales,
    )
