# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Household baskets, demand, and expenses."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import numpy as np

from vic3_analysis.analysis.economy._utils import (
    _readonly_array,
    _readonly_wealth,
    _validate_columns,
    _validate_index_keys,
    _validate_nonnegative_values,
)
from vic3_analysis.analysis.economy.states import (
    EconomyContext,
    EconomyState,
    GoodsBuyPackages,
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
    _validate_columns(packages, {"wealth"}, "df_buy_packages")
    _validate_columns(
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
    values = _validate_nonnegative_values(
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
        coefficients = _validate_nonnegative_values(
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
    return _readonly_array(
        _validate_nonnegative_values(consumption, "consumption_mult")
    )


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
    prices = _validate_nonnegative_values(economy.base_prices, "base_prices")
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
    if (
        context.goods_buy_packages is not None
        and context.consumption_scales is not None
    ):
        return context
    packages = context.goods_buy_packages
    if packages is None:
        packages = economy.calculate_goods_buy_packages(context)
    scales = context.consumption_scales
    if scales is None:
        scales = economy.calculate_pop_consumption_scales(context)
    return replace(context, goods_buy_packages=packages, consumption_scales=scales)


def calculate_goods_buy_packages(
    economy: Economy, state: EconomyState | EconomyContext
) -> GoodsBuyPackages:
    """Calculate weekly goods packages per 10,000 standard workers by wealth.

    Convert the model's wealth-by-category values to goods quantities using
    the supplied state's substitution shares and the model's base prices:
    ``wealth_category_values @ category_purchase_shares / base_prices``.
    Substitution uses effective supply, configured weights, minimum/maximum
    supply shares, and default goods as described by `calculate_pop_needs`.

    Args:
        state: Snapshot or context aligned to this economy. Prepared
            context baskets are reused when present; otherwise only
            building inputs/outputs, imports, and exports are used.

    Returns:
        Immutable `GoodsBuyPackages` with ascending int64 ``wealth`` labels and
        read-only float64 ``quantities`` in `goods_index` column order.
        Prepared context baskets are returned unchanged after validating
        goods alignment; otherwise all tiers in ``df_buy_packages`` are
        calculated. Quantities are goods units per week per 10,000 standard
        workers, with zero for unconsumed goods. Inputs are unchanged.
        Use `Economy.df_goods_buy_packages` for a mutable DataFrame export.

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
    if context.goods_buy_packages is not None:
        economy._validate_goods_buy_packages(context.goods_buy_packages)
        return context.goods_buy_packages
    purchases, prices = economy._pop_need_purchase_shares(context)
    data = economy._pop_needs_coefficients
    with np.errstate(over="ignore", invalid="ignore"):
        values = _validate_nonnegative_values(
            data.packages @ purchases / prices, "calculated goods_buy_packages"
        )
    return GoodsBuyPackages(wealth=data.wealth_levels, quantities=values)


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
    return _validate_nonnegative_values(scales, "calculated consumption_scales")


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
        scales = _validate_nonnegative_values(consumption_scales, "consumption_scales")
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
    tiers: np.ndarray, wealth: np.ndarray, name: str = "goods_buy_packages"
) -> np.ndarray:
    """Locate occupied wealth in sorted, unique tiers after checking coverage."""
    if not np.isin(wealth, tiers).all():
        raise ValueError(f"Occupied pop_wealth tiers must be defined in {name}.")
    return np.searchsorted(tiers, wealth)


def _validate_goods_buy_packages(economy: Economy, packages: GoodsBuyPackages) -> None:
    """Require immutable baskets with columns aligned to this economy's goods."""
    if not isinstance(packages, GoodsBuyPackages):
        raise TypeError("goods_buy_packages must be a GoodsBuyPackages instance.")
    if packages.quantities.shape[1] != len(economy.goods_index):
        raise ValueError("goods_buy_packages columns must match goods_index.")


def _select_goods_buy_packages(
    economy: Economy, packages: GoodsBuyPackages, wealth: np.ndarray
) -> np.ndarray:
    """Check goods alignment and select baskets for occupied wealth tiers."""
    economy._validate_goods_buy_packages(packages)
    return packages.quantities[_wealth_positions(packages.wealth, wealth)]


def _prepare_goods_buy_packages(
    economy: Economy,
    state: EconomyState,
    wealth: np.ndarray,
    goods_buy_packages: GoodsBuyPackages | None,
) -> np.ndarray:
    """Select explicit, prepared, or newly calculated baskets, in that order."""
    if goods_buy_packages is None:
        goods_buy_packages = state.context.goods_buy_packages
    if goods_buy_packages is None:
        goods_buy_packages = economy.calculate_goods_buy_packages(state)
    return economy._select_goods_buy_packages(goods_buy_packages, wealth)


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
        costs = _validate_nonnegative_values(
            selected @ prices, "calculated basket costs"
        )
        expenses[occupied] = scales * costs[inverse]
    return _validate_nonnegative_values(expenses, "calculated pop_expenses")


def calculate_pop_needs(
    economy: Economy,
    state: EconomyState,
    *,
    goods_buy_packages: GoodsBuyPackages | None = None,
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
    obtain units per week. Household scales are aggregated by wealth before
    allocating goods baskets, without a building-by-profession-by-goods tensor.

    Args:
        state: Snapshot aligned to this economy's building, profession,
            and goods indexes. Workers and their dependents consume at the
            same wealth tier; dependents consume half as much per person.
            Empty cells need no wealth package.
        goods_buy_packages: Optional immutable `GoodsBuyPackages`, as returned by
            `calculate_goods_buy_packages`. Wealth labels must cover every occupied
            tier. Quantity columns must follow `goods_index` order; column
            count is checked against the economy. Construction validates and
            sorts wealth labels and quantities together. Supplied baskets
            are scaled directly by worker-
            equivalent population and profession consumption multipliers,
            without substitution or base-price conversion, and remain fixed
            when supply changes.
            Unused state goods flows and raw need/package tables are not
            validated in this mode. The baskets are unchanged.
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
        TypeError: If supplied baskets are not a `GoodsBuyPackages` instance.
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
    selected = _prepare_goods_buy_packages(economy, state, wealth, goods_buy_packages)
    demand = _pop_demand_from_baskets(selected, inverse, scales)
    return economy._validate_goods_vector(demand, "calculated pop_needs")


def calculate_pop_expenses(
    economy: Economy,
    state: EconomyState,
    *,
    goods_buy_packages: GoodsBuyPackages | None = None,
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
        goods_buy_packages: Optional goods baskets with the same contract as in
            `calculate_pop_needs`. When omitted, reuse prepared context
            baskets or call `calculate_goods_buy_packages(state)`. Supplied baskets
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
        TypeError: If supplied baskets are not a `GoodsBuyPackages` instance.
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
    selected = _prepare_goods_buy_packages(economy, state, wealth, goods_buy_packages)
    return _pop_expenses_at_prices(occupied, inverse, scales, selected, prices)


def _prepared_consumption(
    context: EconomyContext,
) -> tuple[GoodsBuyPackages, np.ndarray]:
    """Require the prepared arrays needed by wealth iteration."""
    if context.goods_buy_packages is None or context.consumption_scales is None:
        raise ValueError(
            "Prepared baskets and consumption_scales are required; use evaluate_wealth()."
        )
    return (
        context.goods_buy_packages,
        context.consumption_scales,
    )
