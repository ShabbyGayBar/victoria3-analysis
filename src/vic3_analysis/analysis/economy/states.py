# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Frozen economy snapshots, derived state statistics, and solver outcomes."""

from dataclasses import dataclass, field
from functools import cached_property
from typing import Literal

import numpy as np

from vic3_analysis.analysis.economy._utils import (
    _readonly_array,
    _readonly_wealth,
    _validate_nonnegative_values,
)


@dataclass(frozen=True)
class EquilibriumDiagnostics:
    """Numerical outcome and financial flags for an equilibrium snapshot.

    Attributes:
        status: ``converged``, ``cycle``, ``max_iterations``, ``evaluation_failed``,
            or ``verification_failed``. Convergence means wealth is stationary,
            including at its boundaries; it does not promise financial sustainability.
        iterations: Completed transition steps, excluding initialization and verification.
        increasing_cells: Configuration/profession coordinates requiring advancement.
        decreasing_cells: Configuration/profession coordinates requiring a lower tier.
        unaffordable_floor_cells: Occupied minimum-tier cells below their affordability
            threshold. These cannot move down and do not prevent convergence.
        loss_buildings: Configuration indices with material unfunded weekly losses.
        cycle_start: First iteration of a repeated assignment, or None.
        cycle_length: Number of transitions in the detected cycle, or None.

    Coordinates follow ``Economy.building_index`` and ``Economy.pop_index``.
    Tuple fields contain immutable Python integer indices in row-major order.
    """

    status: Literal[
        "converged",
        "cycle",
        "max_iterations",
        "evaluation_failed",
        "verification_failed",
    ]
    iterations: int
    increasing_cells: tuple[tuple[int, int], ...] = ()
    decreasing_cells: tuple[tuple[int, int], ...] = ()
    unaffordable_floor_cells: tuple[tuple[int, int], ...] = ()
    loss_buildings: tuple[int, ...] = ()
    cycle_start: int | None = None
    cycle_length: int | None = None


def _weighted_percentile(values: np.ndarray, weights: np.ndarray, q: float) -> float:
    """Return the weighted percentile *q* (in ``[0, 1]``) of *values*.

    Args:
        values: 1-D array of observations.
        weights: 1-D array of non-negative weights, aligned to *values*.
        q: Percentile in ``[0, 1]`` (e.g. ``0.5`` for the weighted median).

    Returns:
        The smallest value whose cumulative weight reaches ``q * total_weight``.
    """
    order = np.argsort(values, kind="stable")
    v = values[order]
    w = weights[order]
    cum_w = np.cumsum(w)
    target = q * cum_w[-1]
    idx = int(np.searchsorted(cum_w, target, side="left"))
    idx = min(idx, len(v) - 1)
    return float(v[idx])


def _weighted_std(values: np.ndarray, weights: np.ndarray) -> float:
    """Return the population weighted standard deviation of *values*.

    Args:
        values: 1-D array of observations.
        weights: 1-D array of non-negative weights, aligned to *values*.

    Returns:
        ``sqrt(sum(w * (x - weighted_mean)^2) / sum(w))``, or ``0.0`` when the
        total weight is zero.
    """
    total = float(np.sum(weights))
    if total == 0:
        return 0.0
    mean = float(np.sum(values * weights) / total)
    variance = float(np.sum(weights * (values - mean) ** 2) / total)
    return float(np.sqrt(variance))


@dataclass(frozen=True)
class GoodsBuyPackages:
    """Owned, read-only goods baskets and their ascending wealth labels.

    Attributes:
        wealth: Unique positive int64 wealth tiers, sorted on construction.
        quantities: Weekly goods quantities per 10,000 standard workers,
            shaped as wealth tiers × goods in the owning economy's
            ``goods_index`` order. Rows are sorted with ``wealth``.

    Empty tiers are allowed with a quantities matrix of shape ``(0, n_goods)``.
    """

    wealth: np.ndarray
    quantities: np.ndarray

    def __post_init__(self) -> None:
        """Validate aligned baskets and own sorted, read-only array copies."""
        tiers = _readonly_wealth(self.wealth, "goods_buy_packages.wealth")
        if tiers.ndim != 1 or (tiers == 0).any() or len(np.unique(tiers)) != len(tiers):
            raise ValueError(
                "goods_buy_packages.wealth must contain unique positive wealth tiers."
            )
        values = _validate_nonnegative_values(
            self.quantities, "goods_buy_packages.quantities"
        )
        if values.ndim != 2 or values.shape[0] != len(tiers):
            raise ValueError(
                "goods_buy_packages.quantities shape must match wealth tiers × goods."
            )
        order = np.argsort(tiers)
        object.__setattr__(
            self, "wealth", _readonly_wealth(tiers[order], "goods_buy_packages.wealth")
        )
        object.__setattr__(self, "quantities", _readonly_array(values[order]))


@dataclass(frozen=True)
class EconomyContext:
    """Fixed production, trade, and population inputs shared by snapshots.

    Direct array inputs are owned, read-only copies; immutable ``GoodsBuyPackages``
    objects are shared. Goods columns follow the owning economy's
    ``goods_index``; population columns follow its ``pop_index``.
    Prepared consumption data is optional and remains fixed as wealth and
    prices change. Clear affected prepared fields when changing their inputs,
    then call ``Economy.prepare_context`` to refresh them.

    Attributes:
        building_levels: Levels per production configuration.
        building_goods_flow: Realized weekly signed quantities by configuration
            and good, including throughput and economy-of-scale bonuses.
        goods_import: Non-negative weekly import quantities by good.
        goods_export: Non-negative weekly export quantities by good. The same
            good may have both import and export orders.
        goods_trade_flow: Derived net imports (imports minus exports).
        imports: Read-only alias for goods_import.
        exports: Read-only alias for goods_export.
        pops: Employed-worker counts by configuration and profession.
        workforce_ratio: Workers / total population, in ``(0, 1]``.
        goods_buy_packages: Optional immutable goods baskets with their wealth labels,
            shared across contexts and snapshots.
        consumption_scales: Optional dimensionless basket multiples, shaped
            like ``pops`` and zero in empty cells.
    """

    building_levels: np.ndarray
    building_goods_flow: np.ndarray
    goods_import: np.ndarray
    goods_export: np.ndarray
    pops: np.ndarray
    workforce_ratio: float = field(default=1.0, kw_only=True)
    goods_buy_packages: GoodsBuyPackages | None = field(default=None, kw_only=True)
    consumption_scales: np.ndarray | None = field(default=None, kw_only=True)

    def __post_init__(self) -> None:
        """Own fixed arrays and validate optional prepared consumption data."""
        if not np.isfinite(self.workforce_ratio) or not 0 < self.workforce_ratio <= 1:
            raise ValueError("workforce_ratio must be finite and in (0, 1].")
        for name in (
            "building_levels",
            "building_goods_flow",
            "goods_import",
            "goods_export",
            "pops",
        ):
            object.__setattr__(self, name, _readonly_array(getattr(self, name)))
        if self.goods_buy_packages is not None:
            if not isinstance(self.goods_buy_packages, GoodsBuyPackages):
                raise TypeError(
                    "goods_buy_packages must be a GoodsBuyPackages instance or None."
                )
            quantities = self.goods_buy_packages.quantities
            if (
                self.goods_import.ndim != 1
                or quantities.shape[1] != len(self.goods_import)
                or self.goods_export.shape != self.goods_import.shape
            ):
                raise ValueError(
                    "goods_buy_packages.quantities shape must match context goods."
                )
        if self.consumption_scales is not None:
            scales = _validate_nonnegative_values(
                self.consumption_scales, "consumption_scales"
            )
            pops = _validate_nonnegative_values(self.pops, "pops")
            if scales.shape != pops.shape:
                raise ValueError("consumption_scales shape must match pops.")
            if (scales[pops == 0] != 0).any():
                raise ValueError("consumption_scales must be zero for empty cells.")
            object.__setattr__(self, "consumption_scales", _readonly_array(scales))

    @cached_property
    def goods_trade_flow(self) -> np.ndarray:
        """Return read-only net imports, preserving gross orders separately."""
        return _readonly_array(self.goods_import - self.goods_export)

    @property
    def imports(self) -> np.ndarray:
        """Return read-only weekly import quantities."""
        return self.goods_import

    @property
    def exports(self) -> np.ndarray:
        """Return read-only weekly export quantities."""
        return self.goods_export

    @cached_property
    def building_goods_input(self) -> np.ndarray:
        """Return total weekly input quantities, splitting signs before summing."""
        return _readonly_array(np.maximum(-self.building_goods_flow, 0).sum(axis=0))

    @cached_property
    def building_goods_output(self) -> np.ndarray:
        """Return total weekly output quantities, splitting signs before summing."""
        return _readonly_array(np.maximum(self.building_goods_flow, 0).sum(axis=0))

    @cached_property
    def sell_orders(self) -> np.ndarray:
        """Calculate the sell orders for each good.

        Returns:
            The sell orders vector, computed as the sum of building_goods_output and imports
        """
        result = self.building_goods_output + self.imports
        result.setflags(write=False)
        return result

    @cached_property
    def dependents_per_worker(self) -> float:
        """Return the number of dependents per employed worker."""
        return (1.0 - self.workforce_ratio) / self.workforce_ratio

    @cached_property
    def total_employment(self) -> float:
        """Return the employed-worker headcount, excluding dependents."""
        return float(np.sum(self.pops))

    @cached_property
    def total_population(self) -> float:
        """Return workers plus their dependents, using the uniform workforce ratio."""
        return self.total_employment / self.workforce_ratio

    @cached_property
    def employment_by_profession(self) -> np.ndarray:
        """Calculate total employment per profession.

        Returns:
            A 1-D array of shape ``(n_professions,)`` giving the column sums of
            ``pops``.
        """
        result = self.pops.sum(axis=0)
        result.setflags(write=False)
        return result

    @cached_property
    def profession_shares(self) -> np.ndarray:
        """Calculate each profession's share of total employment.

        Returns:
            A 1-D array of shape ``(n_professions,)`` summing to ``1.0``, or
            all zeros when total employment is zero.
        """
        if self.total_employment == 0:
            result = np.zeros(self.pops.shape[1], dtype=np.float64)
        else:
            result = self.employment_by_profession / self.total_employment
        result.setflags(write=False)
        return result

    @cached_property
    def non_pop_buy_orders(self) -> np.ndarray:
        """Return weekly industrial input and export orders by good."""
        return _readonly_array(self.building_goods_input + self.exports)


@dataclass(frozen=True)
class MarketState:
    """Prices and building finances for a shared fixed economy context.

    Attributes:
        context: Fixed inputs shared with the enclosing ``EconomyState``.
        market_prices: Goods-aligned prices in pounds per unit.
    """

    context: EconomyContext
    market_prices: np.ndarray

    def __post_init__(self) -> None:
        """Own prices without copying the shared context."""
        object.__setattr__(self, "market_prices", _readonly_array(self.market_prices))

    @cached_property
    def building_surplus(self) -> np.ndarray:
        """Return weekly goods value added per configuration before wages (£)."""
        return _readonly_array(self.context.building_goods_flow @ self.market_prices)

    @cached_property
    def building_deficit(self) -> np.ndarray:
        """Return unfunded weekly input costs per configuration (£)."""
        return _readonly_array(np.maximum(-self.building_surplus, 0))

    @cached_property
    def gdp_weekly(self) -> float:
        """Calculate the weekly GDP from net goods and prices.

        Returns:
            The sum of ``(building_goods_output - building_goods_input)
            * market_prices`` (weekly).
        """
        return float(
            np.sum(
                (self.context.building_goods_output - self.context.building_goods_input)
                * self.market_prices
            )
        )

    def gdp(self, annual: bool = False) -> float:
        """Calculate the weekly or annual GDP from net goods and prices.

        Args:
            annual: If ``True``, multiply the weekly GDP by 52 to annualise it.

        Returns:
            The sum of ``(building_goods_output - building_goods_input)
            * market_prices`` (weekly), or 52 times that value when *annual*
            is set.
        """
        if annual:
            return self.gdp_weekly * 52
        return self.gdp_weekly


@dataclass(frozen=True)
class PopState:
    """Changing household wealth, demand, and optional weekly finances.

    Wealth, income, and expenses use configuration-by-profession matrices;
    demand is goods-aligned. ``None`` finances mean unevaluated, including for
    nominal and market solves. Balance is derived only when both are supplied.

    Attributes:
        pop_wealth: Non-negative integer wealth tiers.
        pop_buy_orders: Weekly household goods demand.
        pop_income: Optional total household income in pounds per week.
        pop_expenses: Optional total consumption expenses in pounds per week.
    """

    pop_wealth: np.ndarray
    pop_buy_orders: np.ndarray
    pop_income: np.ndarray | None = None
    pop_expenses: np.ndarray | None = None

    def __post_init__(self) -> None:
        """Own population arrays and validate supplied finances."""
        object.__setattr__(
            self, "pop_wealth", _readonly_wealth(self.pop_wealth, "pop_wealth")
        )
        object.__setattr__(self, "pop_buy_orders", _readonly_array(self.pop_buy_orders))
        for name in ("pop_income", "pop_expenses"):
            value = getattr(self, name)
            if value is not None:
                values = _validate_nonnegative_values(value, name)
                if values.ndim != 2 or values.shape != self.pop_wealth.shape:
                    raise ValueError(f"{name} shape must match the pop_wealth matrix.")
                object.__setattr__(self, name, _readonly_array(values))

    @cached_property
    def pop_balance(self) -> np.ndarray | None:
        """Return weekly income minus expenses, or None when unevaluated."""
        if self.pop_income is None or self.pop_expenses is None:
            return None
        return _readonly_array(self.pop_income - self.pop_expenses)


@dataclass(frozen=True)
class EconomyState:
    """Complete snapshot composed from fixed context, market, and population.

    Components share immutable data without copying production arrays. Familiar
    flat attribute reads forward to their owners; constructors and replacements
    use the component fields. Composition does not evaluate household finances
    or establish consistency between supplied wealth, demand, and prices.

    Attributes:
        context: Fixed production, trade, population, and prepared consumption.
        market: Prices and building finances referencing this exact context.
        households: Household wealth, demand, and optional finances.
        equilibrium_diagnostics: Optional solver outcome and financial flags.
    """

    context: EconomyContext
    market: MarketState
    households: PopState
    equilibrium_diagnostics: EquilibriumDiagnostics | None = field(
        default=None, kw_only=True
    )

    def __post_init__(self) -> None:
        """Reject a market attached to a different context."""
        if self.market.context is not self.context:
            raise ValueError("market.context must be the same object as context.")

    @property
    def building_levels(self) -> np.ndarray:
        """Return ``context.building_levels``."""
        return self.context.building_levels

    @property
    def building_goods_flow(self) -> np.ndarray:
        """Return ``context.building_goods_flow``."""
        return self.context.building_goods_flow

    @property
    def goods_import(self) -> np.ndarray:
        """Return ``context.goods_import``."""
        return self.context.goods_import

    @property
    def goods_export(self) -> np.ndarray:
        """Return ``context.goods_export``."""
        return self.context.goods_export

    @property
    def goods_trade_flow(self) -> np.ndarray:
        """Return net imports from ``context.goods_trade_flow``."""
        return self.context.goods_trade_flow

    @property
    def imports(self) -> np.ndarray:
        """Return ``context.imports``."""
        return self.context.imports

    @property
    def exports(self) -> np.ndarray:
        """Return ``context.exports``."""
        return self.context.exports

    @property
    def pops(self) -> np.ndarray:
        """Return ``context.pops``."""
        return self.context.pops

    @property
    def workforce_ratio(self) -> float:
        """Return ``context.workforce_ratio``."""
        return self.context.workforce_ratio

    @property
    def goods_buy_packages(self) -> GoodsBuyPackages | None:
        """Return ``context.goods_buy_packages``."""
        return self.context.goods_buy_packages

    @property
    def consumption_scales(self) -> np.ndarray | None:
        """Return ``context.consumption_scales``."""
        return self.context.consumption_scales

    @property
    def building_goods_input(self) -> np.ndarray:
        """Return ``context.building_goods_input``."""
        return self.context.building_goods_input

    @property
    def building_goods_output(self) -> np.ndarray:
        """Return ``context.building_goods_output``."""
        return self.context.building_goods_output

    @property
    def sell_orders(self) -> np.ndarray:
        """Return ``context.sell_orders``."""
        return self.context.sell_orders

    @property
    def dependents_per_worker(self) -> float:
        """Return ``context.dependents_per_worker``."""
        return self.context.dependents_per_worker

    @property
    def total_employment(self) -> float:
        """Return ``context.total_employment``."""
        return self.context.total_employment

    @property
    def total_population(self) -> float:
        """Return ``context.total_population``."""
        return self.context.total_population

    @property
    def employment_by_profession(self) -> np.ndarray:
        """Return ``context.employment_by_profession``."""
        return self.context.employment_by_profession

    @property
    def profession_shares(self) -> np.ndarray:
        """Return ``context.profession_shares``."""
        return self.context.profession_shares

    @property
    def non_pop_buy_orders(self) -> np.ndarray:
        """Return ``context.non_pop_buy_orders``."""
        return self.context.non_pop_buy_orders

    @property
    def market_prices(self) -> np.ndarray:
        """Return ``market.market_prices``."""
        return self.market.market_prices

    @property
    def building_surplus(self) -> np.ndarray:
        """Return ``market.building_surplus``."""
        return self.market.building_surplus

    @property
    def building_deficit(self) -> np.ndarray:
        """Return ``market.building_deficit``."""
        return self.market.building_deficit

    @property
    def gdp_weekly(self) -> float:
        """Return ``market.gdp_weekly``."""
        return self.market.gdp_weekly

    @property
    def pop_wealth(self) -> np.ndarray:
        """Return ``households.pop_wealth``."""
        return self.households.pop_wealth

    @property
    def pop_buy_orders(self) -> np.ndarray:
        """Return ``households.pop_buy_orders``."""
        return self.households.pop_buy_orders

    @property
    def pop_income(self) -> np.ndarray | None:
        """Return ``households.pop_income``."""
        return self.households.pop_income

    @property
    def pop_expenses(self) -> np.ndarray | None:
        """Return ``households.pop_expenses``."""
        return self.households.pop_expenses

    @property
    def pop_balance(self) -> np.ndarray | None:
        """Return ``households.pop_balance``."""
        return self.households.pop_balance

    @cached_property
    def buy_orders(self) -> np.ndarray:
        """Calculate the buy orders for each good.

        Returns:
            The buy orders vector, computed as the sum of building_goods_input, exports and population buy orders.
        """
        result = self.context.non_pop_buy_orders + self.pop_buy_orders
        result.setflags(write=False)
        return result

    def gdp(self, annual: bool = False) -> float:
        """Return weekly GDP, or annual GDP when requested."""
        return self.market.gdp(annual)

    def gdp_per_capita(self, annual: bool = False) -> float:
        """Calculate the weekly or annual GDP per capita.

        Args:
            annual: If ``True``, multiply the weekly GDP by 52 to annualise it.

        Returns:
            The GDP per capita, computed as ``gdp(annual) / total_population``,
            or ``0.0`` when total population is zero.
        """
        if self.total_population == 0:
            return 0.0
        return self.gdp(annual) / self.total_population

    @cached_property
    def total_wealth_by_profession(self) -> np.ndarray:
        """Return read-only employment-weighted wealth sums by profession.

        Values sum ``pop_wealth * pops`` over configurations, excluding
        dependents. Divide by ``workforce_ratio`` for population-weighted totals.
        """
        return _readonly_array((self.pop_wealth * self.pops).sum(axis=0))

    @cached_property
    def average_wealth(self) -> float:
        """Calculate the employment-weighted average wealth.

        With a uniform workforce ratio and dependents sharing household wealth,
        this also equals ``total_wealth / total_population``.

        Returns:
            The weighted average of ``wealth`` by ``employment``, or ``0.0``
            when total employment is zero.
        """
        if self.total_employment == 0:
            return 0.0
        return float(self.total_wealth_by_profession.sum() / self.total_employment)

    @cached_property
    def total_wealth(self) -> float:
        """Calculate total population-weighted wealth, including dependents.

        Returns:
            The sum of ``pop_wealth * pops / workforce_ratio``. This is a
            population-weighted sum of wealth tiers, not a monetary stock.
        """
        return float(self.total_wealth_by_profession.sum()) / self.workforce_ratio

    @cached_property
    def average_wealth_by_profession(self) -> np.ndarray:
        """Calculate the employment-weighted average wealth per profession.

        Returns:
            A 1-D array of shape ``(n_professions,)``; entries are ``0.0``
            where a profession has no employment.
        """
        emp = self.employment_by_profession
        weighted = self.total_wealth_by_profession
        with np.errstate(divide="ignore", invalid="ignore"):
            result = np.where(emp > 0, weighted / emp, 0.0)
        result.setflags(write=False)
        return result

    @cached_property
    def wealth_distribution(self) -> dict[str, float]:
        """Calculate weighted wealth-distribution statistics across pops.

        Returns:
            A dict with keys ``"min"``, ``"mean"``, ``"median"``, ``"std"`` and
            ``"max"`` of wealth, weighted by employment. All values are ``0.0``
            when there is no employment.
        """
        weights = self.pops.flatten()
        values = self.pop_wealth.flatten()
        mask = weights > 0
        if not mask.any():
            return {"min": 0.0, "mean": 0.0, "median": 0.0, "std": 0.0, "max": 0.0}
        vw = values[mask]
        ww = weights[mask]
        return {
            "min": float(vw.min()),
            "max": float(vw.max()),
            "mean": self.average_wealth,
            "median": _weighted_percentile(vw, ww, 0.5),
            "std": _weighted_std(vw, ww),
        }

    @cached_property
    def gini_wealth(self) -> float:
        """Calculate the Gini coefficient of the wealth distribution.

        Returns:
            A float in ``[0, 1]`` (``0`` = perfectly equal, ``1`` = maximally
            unequal), weighted by employment. Returns ``0.0`` when there is no
            employment or no total wealth.
        """
        weights = self.pops.flatten()
        values = self.pop_wealth.flatten()
        mask = weights > 0
        if not mask.any():
            return 0.0
        vw = values[mask]
        ww = weights[mask]
        if float(np.sum(vw * ww)) == 0:
            return 0.0
        order = np.argsort(vw, kind="stable")
        x = vw[order]
        w = ww[order]
        cum_w = np.cumsum(w)
        cum_wv = np.cumsum(w * x)
        f = np.concatenate(([0.0], cum_w / cum_w[-1]))
        lorenz = np.concatenate(([0.0], cum_wv / cum_wv[-1]))
        area = float(np.sum((f[1:] - f[:-1]) * (lorenz[1:] + lorenz[:-1]) / 2.0))
        return float(1.0 - 2.0 * area)


class EquilibriumError(RuntimeError):
    """Failure after initialization, retaining the last evaluated snapshot.

    Attributes:
        state: Immutable last evaluated state with solver diagnostics attached.
        diagnostics: The same diagnostics object as on ``state``.

    Cycles and iteration exhaustion do not prove that no equilibrium exists.
    Calculation failures retain the original exception through ``__cause__``.
    """

    def __init__(self, message: str, state: EconomyState) -> None:
        """Attach a diagnostic-bearing snapshot to a solver failure message."""
        super().__init__(message)
        if state.equilibrium_diagnostics is None:
            raise ValueError("EquilibriumError requires state diagnostics.")
        self.state = state
        self.diagnostics = state.equilibrium_diagnostics
