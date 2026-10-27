# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Wealth evaluation, transitions, and equilibrium solving."""

from __future__ import annotations

from dataclasses import dataclass, replace
from typing import TYPE_CHECKING

import numpy as np

from vic3_analysis.analysis.economy._utils import (
    _readonly_wealth,
    _validate_nonnegative_values,
)
from vic3_analysis.analysis.economy.consumption import (
    _group_pop_consumption,
    _pop_demand_from_baskets,
    _pop_expenses_at_prices,
)
from vic3_analysis.analysis.economy.states import (
    EconomyContext,
    EconomyState,
    EquilibriumDiagnostics,
    EquilibriumError,
    MarketState,
    PopState,
)

if TYPE_CHECKING:
    from vic3_analysis.analysis.economy.model import Economy

from vic3_analysis.analysis.economy.income import _PopIncomeCoefficients

# common/defines/00_defines.txt: WEALTH_PROGRESS_ACCEPTABLE_DEFICIT / WANTED_BUFFER.
_WEALTH_DECREASE_THRESHOLD = 0.98
_WEALTH_INCREASE_THRESHOLD = 1.02


@dataclass
class _WealthEvaluation:
    """Mutable working arrays; public snapshots freeze copies only when needed."""

    pop_wealth: np.ndarray
    pop_buy_orders: np.ndarray
    market_prices: np.ndarray
    pop_income: np.ndarray
    pop_expenses: np.ndarray
    pop_balance: np.ndarray


@dataclass
class _WealthTransition:
    """Simultaneous permitted changes and unaffordable minimum-tier cells."""

    wealth: np.ndarray
    increasing: np.ndarray
    decreasing: np.ndarray
    unaffordable_floor: np.ndarray


def evaluate_wealth(
    economy: Economy, context: EconomyContext, pop_wealth: np.ndarray
) -> tuple[MarketState, PopState]:
    """Evaluate demand, market prices, and finances at fixed household wealth.

    Prepare missing context baskets and consumption scales, preserving any
    supplied prepared fields. Calculate demand first, then market prices
    from total buy orders and fixed sell orders, and finally cooperative
    income and household expenses at those same prices.

    Args:
        context: Fixed production, trade, and worker counts aligned to this
            economy. Prepared baskets and scales are optional.
        pop_wealth: Non-negative integer wealth matrix aligned to
            configurations and professions. Occupied tiers need baskets;
            empty cells may use undefined tiers.

    Returns:
        Matching market and household components, in that order, with
        read-only arrays and fully evaluated household finances. Wealth
        values are preserved. The market shares the supplied context when
        fully prepared; otherwise it references a newly prepared context.
        Compose a complete snapshot with
        ``EconomyState(market.context, market, households)``.

    Raises:
        ValueError: If context inputs or wealth are invalid or misaligned,
            preparation fails, occupied tiers lack baskets, income cannot
            be allocated, or calculated results are non-finite.

    Notes:
        Inputs and model tables are unchanged. This evaluates one wealth
        assignment without affordability limits or wealth transitions.
    """
    economy._validate_building_goods_flow(context)
    economy._validate_goods_vector(
        context.goods_trade_flow, "context.goods_trade_flow", nonnegative=False
    )
    context = economy.prepare_context(context)
    wealth = economy._validate_wealth_assignment(context, pop_wealth)
    evaluation = economy._evaluate_prepared_wealth(
        context, wealth, economy._prepare_pop_income(context)
    )
    return economy._freeze_wealth(context, evaluation)


def _validate_wealth_assignment(
    economy: Economy, context: EconomyContext, pop_wealth: np.ndarray
) -> np.ndarray:
    """Validate full matrix alignment and occupied basket coverage."""
    pops = economy._validate_worker_counts(context)
    wealth = _readonly_wealth(pop_wealth, "pop_wealth")
    if wealth.shape != pops.shape:
        raise ValueError(
            "state.pop_wealth shape must match building_index and pop_index."
        )
    if context.goods_buy_packages is None:
        raise ValueError("Prepared goods_buy_packages are required.")
    economy._select_goods_buy_packages(
        context.goods_buy_packages,
        np.unique(wealth[pops > 0]),
    )
    return wealth


def _evaluate_prepared_wealth(
    economy: Economy,
    context: EconomyContext,
    wealth: np.ndarray,
    income_coefficients: _PopIncomeCoefficients,
) -> _WealthEvaluation:
    """Evaluate working arrays without constructing immutable intermediate states."""
    packages, scales = economy._prepared_consumption(context)
    occupied, used_wealth, inverse, cell_scales = _group_pop_consumption(
        context.pops, wealth, scales
    )
    selected = economy._select_goods_buy_packages(packages, used_wealth)
    with np.errstate(over="ignore", invalid="ignore"):
        demand = _validate_nonnegative_values(
            _pop_demand_from_baskets(selected, inverse, cell_scales),
            "calculated pop_buy_orders",
        )
        prices = economy._validate_goods_vector(
            economy.market_prices(
                context.non_pop_buy_orders + demand, context.sell_orders
            ),
            "calculated market_prices",
        )
        income = economy._pop_income_at_prices(context, prices, income_coefficients)
        expenses = _pop_expenses_at_prices(
            occupied, inverse, cell_scales, selected, prices
        )
        balance = income - expenses
    if not np.isfinite(balance).all():
        raise ValueError("calculated pop_balance must contain finite values.")
    return _WealthEvaluation(wealth, demand, prices, income, expenses, balance)


def _freeze_wealth(
    context: EconomyContext, evaluation: _WealthEvaluation
) -> tuple[MarketState, PopState]:
    """Freeze matching components while sharing all fixed context arrays."""
    return (
        MarketState(context, evaluation.market_prices),
        PopState(
            evaluation.pop_wealth,
            evaluation.pop_buy_orders,
            evaluation.pop_income,
            evaluation.pop_expenses,
        ),
    )


def _validate_equilibrium_tolerances(rtol: float, atol: float) -> None:
    """Reject negative, non-finite, boolean, or non-scalar tolerances."""
    for name, value in (("rtol", rtol), ("atol", atol)):
        if (
            isinstance(value, (bool, np.bool_))
            or not isinstance(value, (int, float, np.integer, np.floating))
            or not np.isfinite(value)
            or value < 0
        ):
            raise ValueError(f"{name} must be a finite non-negative scalar.")


def _validate_iteration_context(economy: Economy, context: EconomyContext) -> None:
    """Check prepared axes and consecutive tiers without restricting evaluation."""
    economy._validate_building_goods_flow(context)
    economy._validate_goods_vector(
        context.goods_trade_flow, "context.goods_trade_flow", nonnegative=False
    )
    pops = economy._validate_worker_counts(context)
    _validate_nonnegative_values(context.building_levels, "building_levels")
    if context.building_levels.shape != (len(economy.building_index),):
        raise ValueError("building_levels shape must match building_index.")
    packages, scales = economy._prepared_consumption(context)
    tiers = packages.wealth
    economy._validate_goods_buy_packages(packages)
    if scales.shape != pops.shape:
        raise ValueError("consumption_scales shape must match state.pops.")
    if (len(tiers) == 0 and (pops > 0).any()) or (np.diff(tiers) != 1).any():
        raise ValueError(
            "Wealth iteration requires nonempty consecutive wealth tiers for occupied cells."
        )


def _wealth_transition(
    economy: Economy,
    context: EconomyContext,
    wealth: np.ndarray,
    prices: np.ndarray,
    income: np.ndarray,
    rtol: float,
    atol: float,
) -> _WealthTransition:
    """Select simultaneous one-tier changes, with decrease taking precedence."""
    packages, scales = economy._prepared_consumption(context)
    tiers = packages.wealth
    occupied = context.pops > 0
    increasing = np.zeros(wealth.shape, dtype=bool)
    decreasing = np.zeros(wealth.shape, dtype=bool)
    floor = np.zeros(wealth.shape, dtype=bool)
    result = wealth.copy()
    if occupied.any():
        positions = np.searchsorted(tiers, wealth[occupied])
        next_positions = np.minimum(positions + 1, len(tiers) - 1)
        # Price only tiers needed now, avoiding a household-by-goods tensor.
        used, inverse = np.unique(
            np.concatenate((positions, next_positions)), return_inverse=True
        )
        with np.errstate(over="ignore", invalid="ignore"):
            costs = _validate_nonnegative_values(
                packages.quantities[used] @ prices, "calculated transition basket costs"
            )
            current_cost, next_cost = np.split(costs[inverse], 2)
            next_cost = np.where(positions < len(tiers) - 1, next_cost, 0)
            lower = _validate_nonnegative_values(
                _WEALTH_DECREASE_THRESHOLD * (scales[occupied] * current_cost),
                "calculated decrease threshold",
            )
            upper = _validate_nonnegative_values(
                _WEALTH_INCREASE_THRESHOLD * (scales[occupied] * next_cost),
                "calculated increase threshold",
            )
            earnings = income[occupied]
            lower_tolerance = _validate_nonnegative_values(
                atol + rtol * np.maximum(earnings, lower), "decrease tolerance"
            )
            upper_tolerance = _validate_nonnegative_values(
                atol + rtol * np.maximum(earnings, upper), "increase tolerance"
            )
        below = earnings < lower - lower_tolerance
        decreasing[occupied] = below & (positions > 0)
        increasing[occupied] = (
            ~below
            & (positions < len(tiers) - 1)
            & (earnings >= upper - upper_tolerance)
        )
        floor[occupied] = below & (positions == 0)
        result[decreasing] -= 1
        result[increasing] += 1
    return _WealthTransition(result, increasing, decreasing, floor)


def iterate(
    economy: Economy,
    context: EconomyContext,
    market: MarketState,
    households: PopState,
    *,
    rtol: float = 1e-9,
    atol: float = 1e-8,
) -> tuple[MarketState, PopState]:
    """Apply one simultaneous wealth transition and evaluate matching results.

    Initialize with ``evaluate_wealth()`` and pass its prepared market context.
    Inputs must be consistent: this method validates alignment and finances,
    but trusts their economic consistency without reevaluating the old wealth.
    Decrease below 98% of current cost; otherwise increase at or above 102%
    of next-tier cost, using previous prices and household scales. Each
    threshold accepts equality within ``atol + rtol * max(income, threshold)``.
    Decreases take precedence. Empty cells and bounded tiers are preserved.

    Returns:
        Matching read-only market and population components sharing ``context``.
        If wealth is unchanged, the exact supplied components are returned.
        A step is numerical rather than a simulated week and makes no
        convergence or financial-sustainability claim.

    Raises:
        ValueError: If tolerances, context identity, prepared tiers, component
            axes, prices, or finances are invalid, or calculations fail.
    """
    economy._validate_equilibrium_tolerances(rtol, atol)
    if market.context is not context:
        raise ValueError("market.context must be the same object as context.")
    economy._validate_iteration_context(context)
    wealth = economy._validate_wealth_assignment(context, households.pop_wealth)
    economy._validate_goods_vector(market.market_prices, "market.market_prices")
    economy._validate_goods_vector(
        households.pop_buy_orders, "households.pop_buy_orders"
    )
    if households.pop_income is None or households.pop_expenses is None:
        raise ValueError(
            "Evaluated household income and expenses are required; use evaluate_wealth()."
        )
    transition = economy._wealth_transition(
        context, wealth, market.market_prices, households.pop_income, rtol, atol
    )
    if np.array_equal(transition.wealth, wealth):
        return market, households
    evaluation = economy._evaluate_prepared_wealth(
        context, transition.wealth, economy._prepare_pop_income(context)
    )
    return economy._freeze_wealth(context, evaluation)


def _equilibrium_diagnostics(
    economy: Economy,
    context: EconomyContext,
    evaluation: _WealthEvaluation,
    transition: _WealthTransition,
    iterations: int,
    rtol: float,
    atol: float,
) -> EquilibriumDiagnostics:
    """Describe the current assignment and its material financial shortfalls."""

    def coordinates(mask: np.ndarray) -> tuple[tuple[int, int], ...]:
        return tuple((int(row), int(col)) for row, col in np.argwhere(mask))

    with np.errstate(over="ignore", invalid="ignore"):
        output_value = _validate_nonnegative_values(
            np.maximum(context.building_goods_flow, 0) @ evaluation.market_prices,
            "building output value",
        )
        input_value = _validate_nonnegative_values(
            np.maximum(-context.building_goods_flow, 0) @ evaluation.market_prices,
            "building input value",
        )
    # Only divide positive excess losses; both operands are then bounded by scale.
    losses = input_value - output_value
    scale = np.maximum(input_value, output_value)
    material = losses > atol
    material[material] = (losses[material] - atol) / scale[material] > rtol
    return EquilibriumDiagnostics(
        status="max_iterations",
        iterations=iterations,
        increasing_cells=coordinates(transition.increasing),
        decreasing_cells=coordinates(transition.decreasing),
        unaffordable_floor_cells=coordinates(transition.unaffordable_floor),
        loss_buildings=tuple(int(i) for i in np.flatnonzero(material)),
    )


def _equilibrium_snapshot(
    economy: Economy,
    context: EconomyContext,
    evaluation: _WealthEvaluation,
    diagnostics: EquilibriumDiagnostics,
) -> EconomyState:
    """Freeze only public success/failure results, never the fixed context again."""
    market, households = economy._freeze_wealth(context, evaluation)
    return EconomyState(
        context, market, households, equilibrium_diagnostics=diagnostics
    )


def _verify_equilibrium(
    economy: Economy,
    context: EconomyContext,
    evaluation: _WealthEvaluation,
    rtol: float,
    atol: float,
) -> tuple[_WealthEvaluation, _WealthTransition]:
    """Recompute through public accounting helpers and recheck stationarity."""
    market, households = economy._freeze_wealth(context, evaluation)
    state = EconomyState(context, market, households)
    needs = economy.pop_buy_orders(state)
    prices = economy.market_prices(
        context.non_pop_buy_orders + needs, context.sell_orders
    )
    state = replace(state, market=MarketState(context, prices))
    income = economy.pop_income(state)
    expenses = economy.pop_expenses(state)
    balance = income - expenses
    verified = _WealthEvaluation(
        evaluation.pop_wealth, needs, prices, income, expenses, balance
    )
    for name in (
        "pop_buy_orders",
        "market_prices",
        "pop_income",
        "pop_expenses",
        "pop_balance",
    ):
        actual = getattr(verified, name)
        if not np.isfinite(actual).all() or not np.allclose(
            actual, getattr(evaluation, name), rtol=rtol, atol=atol
        ):
            raise ValueError(f"Final verification disagrees on {name}.")
    transition = economy._wealth_transition(
        context, verified.pop_wealth, prices, income, rtol, atol
    )
    if not np.array_equal(transition.wealth, verified.pop_wealth):
        raise ValueError("Final verification requires further wealth transitions.")
    return verified, transition


def _solve_equilibrium(
    economy: Economy,
    context: EconomyContext,
    initial_wealth: np.ndarray,
    *,
    max_iterations: int,
    rtol: float,
    atol: float,
) -> EconomyState:
    """Bounded discrete fixed-point iteration with exact cycle detection."""
    context = economy.prepare_context(context)
    economy._validate_iteration_context(context)
    wealth = economy._validate_wealth_assignment(context, initial_wealth)
    coefficients = economy._prepare_pop_income(context)
    evaluation = economy._evaluate_prepared_wealth(context, wealth, coefficients)
    transition = economy._wealth_transition(
        context, wealth, evaluation.market_prices, evaluation.pop_income, rtol, atol
    )
    diagnostics = economy._equilibrium_diagnostics(
        context, evaluation, transition, 0, rtol, atol
    )
    occupied = context.pops > 0
    seen: dict[bytes, int] = {}
    while True:
        if np.array_equal(transition.wealth, evaluation.pop_wealth):
            try:
                verified, final_transition = economy._verify_equilibrium(
                    context, evaluation, rtol, atol
                )
                final_diagnostics = replace(
                    economy._equilibrium_diagnostics(
                        context,
                        verified,
                        final_transition,
                        diagnostics.iterations,
                        rtol,
                        atol,
                    ),
                    status="converged",
                )
            except (ValueError, FloatingPointError, OverflowError) as exc:
                failure = replace(diagnostics, status="verification_failed")
                raise EquilibriumError(
                    f"Equilibrium final verification failed: {exc}",
                    economy._equilibrium_snapshot(context, evaluation, failure),
                ) from exc
            return economy._equilibrium_snapshot(context, verified, final_diagnostics)
        key = evaluation.pop_wealth[occupied].tobytes()
        if key in seen:
            start = seen[key]
            failure = replace(
                diagnostics,
                status="cycle",
                cycle_start=start,
                cycle_length=diagnostics.iterations - start,
            )
            raise EquilibriumError(
                f"Equilibrium cycle of length {failure.cycle_length} detected after {diagnostics.iterations} iterations; this does not prove no equilibrium exists.",
                economy._equilibrium_snapshot(context, evaluation, failure),
            )
        seen[key] = diagnostics.iterations
        if diagnostics.iterations >= max_iterations:
            raise EquilibriumError(
                f"Equilibrium exhausted max_iterations={max_iterations}.",
                economy._equilibrium_snapshot(context, evaluation, diagnostics),
            )
        try:
            candidate = economy._evaluate_prepared_wealth(
                context, transition.wealth, coefficients
            )
            candidate_transition = economy._wealth_transition(
                context,
                candidate.pop_wealth,
                candidate.market_prices,
                candidate.pop_income,
                rtol,
                atol,
            )
            candidate_diagnostics = economy._equilibrium_diagnostics(
                context,
                candidate,
                candidate_transition,
                diagnostics.iterations + 1,
                rtol,
                atol,
            )
        except (ValueError, FloatingPointError, OverflowError) as exc:
            failure = replace(diagnostics, status="evaluation_failed")
            raise EquilibriumError(
                f"Equilibrium evaluation failed after {diagnostics.iterations} completed iterations: {exc}",
                economy._equilibrium_snapshot(context, evaluation, failure),
            ) from exc
        evaluation, transition, diagnostics = (
            candidate,
            candidate_transition,
            candidate_diagnostics,
        )
