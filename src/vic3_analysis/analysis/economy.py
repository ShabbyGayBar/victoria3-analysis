"""
General-equilibrium economy model for Victoria 3.

Defines `EconomyState` as the solver state (building levels, prices,
supply, demand, employment, and wealth) and `Economy` which derives a
nominal `EconomyState` from a building-level vector using base goods
prices and per-profession wealth from the pop-types table.
"""

import warnings
from dataclasses import dataclass, replace
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

from vic3_analysis import (
    BuildingsParser,
    PopTypesParser,
    ProductionMethodParser,
    goods,
    production_table,
    technology,
)

_ARABLE_LAND_BUILDING_GROUPS: frozenset[str] = frozenset(
    {
        "bg_staple_crops",
        "bg_ranching",
        "bg_agriculture",
        "bg_plantations",
        "bg_subsistence_agriculture",
        "bg_subsistence_ranching",
    }
)


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
class EconomyState:
    """Snapshot state of a Victoria 3 economy.

    Attributes:
        building_levels: 1-D array of building-configuration levels (one per
            row of the production table).
        market_prices: 1-D array of good prices (one per tradeable good).
        imports: 1-D array of imported goods (one per tradeable good).
        exports: 1-D array of exported goods (one per tradeable good).
        buy_orders: 1-D array of buy orders (one per tradeable good).
        sell_orders: 1-D array of sell orders (one per tradeable good).
        building_goods_input: 1-D array of total input goods from all buildings (one per tradeable good).
        building_goods_output: 1-D array of total output goods from all buildings (one per tradeable good).
        pops: 2-D array of employment (rows are buildings, columns are
            professions); cell ``[i, j]`` is the employment of profession ``j``
            at building ``i``.
        pop_balance: 2-D array of pop balance (rows are buildings, columns are pop types); cell ``[i, j]`` is the total balance of pop type ``j`` at building ``i``.
        pop_needs: 1-D array of pop needs (one per tradeable good).
        pop_wealth: 2-D array of wealth (rows are buildings, columns are
            professions); cell ``[i, j]`` is the wealth of profession ``j`` at
            building ``i``.
    """

    building_levels: np.ndarray
    building_goods_input: np.ndarray
    building_goods_output: np.ndarray
    imports: np.ndarray
    exports: np.ndarray
    market_prices: np.ndarray
    pops: np.ndarray
    pop_wealth: np.ndarray
    pop_balance: np.ndarray
    pop_needs: np.ndarray

    @cached_property
    def sell_orders(self) -> np.ndarray:
        """Calculate the sell orders for each good.

        Returns:
            The sell orders vector, computed as the sum of building_goods_output and imports
        """
        return self.building_goods_output + self.imports

    @cached_property
    def buy_orders(self) -> np.ndarray:
        """Calculate the buy orders for each good.

        Returns:
            The buy orders vector, computed as the sum of building_goods_input, exports and pop needs.
        """
        return self.building_goods_input + self.exports + self.pop_needs

    @cached_property
    def gdp_weekly(self) -> float:
        """Calculate the weekly GDP from net goods and prices.

        Returns:
            The sum of ``(building_goods_output - building_goods_input)
            * market_prices`` (weekly).
        """
        return float(
            np.sum(
                (self.building_goods_output - self.building_goods_input)
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

    @cached_property
    def total_population(self) -> float:
        """Calculate the total population from employment.

        Returns:
            The sum of ``pops`` (total population).
        """
        return float(np.sum(self.pops))

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
    def average_wealth(self) -> float:
        """Calculate the employment-weighted average wealth.

        Returns:
            The weighted average of ``wealth`` by ``employment``, or ``0.0``
            when total employment is zero.
        """
        if self.total_population == 0:
            return 0.0
        return float(np.sum(self.pop_wealth * self.pops) / self.total_population)

    @cached_property
    def employment_by_profession(self) -> np.ndarray:
        """Calculate total employment per profession.

        Returns:
            A 1-D array of shape ``(n_professions,)`` giving the column sums of
            ``pops``.
        """
        return self.pops.sum(axis=0)

    @cached_property
    def total_wealth(self) -> float:
        """Calculate the total employment-weighted wealth.

        Returns:
            The sum of ``pop_wealth * pops`` (the wealth counterpart of GDP).
        """
        return float(np.sum(self.pop_wealth * self.pops))

    def wealth_per_capita(self) -> float:
        """Calculate the wealth per capita.

        Returns:
            ``total_wealth / total_population``, or ``0.0`` when total
            population is zero.
        """
        if self.total_population == 0:
            return 0.0
        return self.total_wealth / self.total_population

    @cached_property
    def wealth_by_profession(self) -> np.ndarray:
        """Calculate the employment-weighted average wealth per profession.

        Returns:
            A 1-D array of shape ``(n_professions,)``; entries are ``0.0``
            where a profession has no employment.
        """
        emp = self.employment_by_profession
        weighted = (self.pop_wealth * self.pops).sum(axis=0)
        with np.errstate(divide="ignore", invalid="ignore"):
            return np.where(emp > 0, weighted / emp, 0.0)

    @cached_property
    def profession_shares(self) -> np.ndarray:
        """Calculate each profession's share of total employment.

        Returns:
            A 1-D array of shape ``(n_professions,)`` summing to ``1.0``, or
            all zeros when total population is zero.
        """
        if self.total_population == 0:
            return np.zeros(self.pops.shape[1], dtype=np.float64)
        return self.employment_by_profession / self.total_population

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
            "mean": float(np.average(vw, weights=ww)),
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


class Economy:
    """Builds `EconomyState` instances from building-level vectors.

    Wraps the production table, goods table, and pop-types table parsed from
    the Victoria 3 game files and pre-computes the matrices needed to derive
    prices, supply, demand, employment, and wealth for a given
    ``building_levels`` vector.

    Attributes:
        df_production: The production table DataFrame.
        df_goods: The goods table DataFrame.
        df_pop_types: The pop-types table DataFrame.
    """

    df_production: pd.DataFrame
    df_goods: pd.DataFrame
    df_pop_types: pd.DataFrame

    def __init__(
        self,
        game_dir: str | Path | None = None,
        df_production: pd.DataFrame | None = None,
        df_goods: pd.DataFrame | None = None,
        df_pop_types: pd.DataFrame | None = None,
    ):
        """Initialise the model by parsing the required game tables.

        Args:
            game_dir: Path to the Victoria 3 ``game`` directory. If ``None``
                the directory is located automatically via
                `get_vic3_directory`. Ignored for
                any table whose DataFrame is passed directly.
            df_production: Pre-built production table DataFrame. When
                provided, overrides the table that would otherwise be generated
                by `production_table`. Useful for reusing a
                filtered or cached table.
            df_goods: Pre-built goods table DataFrame. When provided,
                overrides the table that would otherwise be generated by
                `goods`.
            df_pop_types: Pre-built pop-types table DataFrame. When provided,
                overrides the table that would otherwise be generated by
                `PopTypesParser`.
        """
        if df_production is None:
            df_production = production_table(
                BuildingsParser(game_dir).to_dataframe(),
                goods(game_dir),
                ProductionMethodParser(game_dir).to_dataframe(),
                technology(game_dir),
            )
        if df_goods is None:
            df_goods = goods(game_dir)
        if df_pop_types is None:
            df_pop_types = PopTypesParser(game_dir).to_dataframe()
        self.df_production = df_production
        self.df_goods = df_goods
        self.df_pop_types = df_pop_types
        goods_columns = [f"goods_{good}" for good in self.goods_index()]

        missing = set(goods_columns) - set(self.df_production.columns)
        if missing:
            warnings.warn(f"Missing goods input columns: {sorted(missing)}")

    def building_index(self) -> list[str]:
        """Return production-configuration keys in production-table row order.

        Each key combines the row's building and production-method strings with
        ``"+"``. The resulting order defines the alignment of building-level
        vectors and the rows of building matrices.
        """
        return [
            f"{b}+{pm}"
            for b, pm in zip(
                self.df_production["building"],
                self.df_production["production_method"],
            )
        ]

    def goods_index(self) -> list[str]:
        """Return good keys in goods-table row order.

        This order defines the alignment of goods vectors and the columns of
        goods matrices.
        """
        return self.df_goods["key"].tolist()

    def producible_goods(self) -> list[str]:
        """Return goods that have at least one producer configuration.

        Returns:
            A list of good keys that can be produced by at least one building
            configuration in the production table.
        """
        out_mat = self.goods_output_matrix()
        goods_index = self.goods_index()
        return [g for j, g in enumerate(goods_index) if (out_mat[:, j] > 0).any()]

    def pop_index(self) -> list[str]:
        """Return profession keys in pop-types-table row order.

        This order defines the alignment of profession vectors and employment
        matrix columns.
        """
        return self.df_pop_types["key"].tolist()

    def base_prices(self) -> np.ndarray:
        """Return Victoria 3 base prices aligned to `goods_index`."""
        return self.df_goods["cost"].to_numpy(dtype=np.float64)

    def _apply_throughput_multipliers(
        self,
        matrix: np.ndarray,
        throughput_multipliers: (np.ndarray[tuple[int], np.dtype[np.float64]] | None),
    ) -> np.ndarray:
        """Scale matrix rows by optional per-configuration multipliers."""
        if throughput_multipliers is None:
            return matrix
        self._validate_throughput_multipliers(throughput_multipliers)
        return matrix * throughput_multipliers[:, None]

    def _validate_throughput_multipliers(
        self,
        throughput_multipliers: np.ndarray[tuple[int], np.dtype[np.float64]],
    ) -> None:
        """Validate a production-row-aligned throughput multiplier vector."""
        if throughput_multipliers.ndim != 1:
            raise ValueError("throughput_multipliers must be a 1-D array.")
        if throughput_multipliers.shape[0] != len(self.building_index()):
            raise ValueError(
                "throughput_multipliers length must match the number of rows "
                "in the production table."
            )

    def economy_of_scale_bonuses(
        self,
        building_levels: np.ndarray[tuple[int], np.dtype[np.float64]],
        level_cap: float = 20.0,
    ) -> np.ndarray:
        """Return per-configuration economy-of-scale throughput bonuses.

        Levels are summed across all production-method configurations of each
        building. Eligible configurations receive one percentage point of
        throughput per total building level, capped by *level_cap*. Returned
        values are additive bonuses (for example, ``0.2`` for +20%), not full
        multipliers.

        Args:
            building_levels: Production-row-aligned building levels.
            level_cap: Maximum number of levels contributing to the bonus.

        Returns:
            A 1-D bonus vector aligned to the production table.

        Raises:
            ValueError: If *building_levels* is not aligned to the production
                table or *level_cap* is negative or non-finite.
        """
        expected_shape = (len(self.df_production),)
        if building_levels.shape != expected_shape:
            raise ValueError("building_levels shape must match the production table.")
        if not np.isfinite(level_cap) or level_cap < 0:
            raise ValueError("level_cap must be a non-negative finite number.")
        if "economy_of_scale" not in self.df_production.columns:
            return np.zeros(expected_shape, dtype=np.float64)

        buildings = self.df_production["building"].astype(str).to_numpy()
        totals: dict[str, float] = {}
        for building, level in zip(buildings, building_levels):
            totals[building] = totals.get(building, 0.0) + float(level)

        eligible = (
            self.df_production["economy_of_scale"]
            .fillna(False)
            .eq(True)
            .to_numpy(dtype=bool)
        )
        bonuses = np.zeros(expected_shape, dtype=np.float64)
        for i, building in enumerate(buildings):
            if eligible[i]:
                bonuses[i] = 0.01 * min(max(totals[building], 0.0), level_cap)
        return bonuses

    def goods_input_matrix(
        self,
        throughput_multipliers: (
            np.ndarray[tuple[int], np.dtype[np.float64]] | None
        ) = None,
    ) -> np.ndarray:
        """Return gross goods inputs, optionally scaled by configuration."""
        goods_columns = [f"goods_{good}" for good in self.goods_index()]
        matrix = np.maximum(
            -self.df_production.reindex(columns=goods_columns, fill_value=0).to_numpy(
                dtype=np.float64
            ),
            0,
        )
        return self._apply_throughput_multipliers(matrix, throughput_multipliers)

    def goods_output_matrix(
        self,
        throughput_multipliers: (
            np.ndarray[tuple[int], np.dtype[np.float64]] | None
        ) = None,
    ) -> np.ndarray:
        """Return gross goods outputs, optionally scaled by configuration."""
        goods_columns = [f"goods_{good}" for good in self.goods_index()]
        matrix = np.maximum(
            self.df_production.reindex(columns=goods_columns, fill_value=0).to_numpy(
                dtype=np.float64
            ),
            0,
        )
        return self._apply_throughput_multipliers(matrix, throughput_multipliers)

    def employment_matrix(self) -> np.ndarray:
        """Return employment by production configuration and profession.

        Rows align to `building_index` and columns align to
        `pop_index`. Values are the number of employees per building
        level; missing profession columns are filled with zero.
        """
        employment_columns = [f"employment_{pop}" for pop in self.pop_index()]

        return self.df_production.reindex(
            columns=employment_columns, fill_value=0
        ).to_numpy(dtype=np.float64)

    def pop_wealth_init(self) -> np.ndarray:
        """Return starting wealth values aligned to `pop_index`."""
        return self.df_pop_types["start_quality_of_life"].to_numpy(dtype=np.float64)

    def employment_vector(self) -> np.ndarray:
        """Total employment per building level, aligned to production-table rows.

        Returns:
            A 1-D array of shape ``(n_buildings,)`` giving the total employment
            of each building configuration per level (``"employment"`` column,
            missing values zero-filled).
        """
        return self.df_production["employment"].fillna(0).to_numpy(dtype=np.float64)

    def construction_cost_vector(self) -> np.ndarray:
        """Return per-level construction cost aligned to `building_index`."""
        return self.df_production["construction_cost"].to_numpy(dtype=np.float64)

    def _validate_goods_vector(
        self,
        vector: np.ndarray,
        name: str,
    ) -> np.ndarray:
        """Validate a goods-aligned vector and return it as float64."""
        if vector.ndim != 1:
            raise ValueError(f"{name} must be a 1-D array.")
        if vector.shape[0] != len(self.goods_index()):
            raise ValueError(f"{name} length must match the number of goods.")
        if not np.isfinite(vector).all():
            raise ValueError(f"{name} must contain only finite values.")
        if (vector < 0).any():
            raise ValueError(f"{name} must contain only non-negative values.")
        return vector.astype(np.float64, copy=False)

    def market_prices_variance(self, eco: EconomyState) -> np.ndarray:
        """Calculate the market prices variance from base prices.

        Args:
            eco: The `Economy` to evaluate (as produced by
                `solve`).

        Returns:
            A 1-D array of shape ``(n_goods,)`` containing the market prices variance.
        """
        return (eco.market_prices / self.base_prices() - 1) * 100

    def market_prices(
        self,
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
        buy_orders = self._validate_goods_vector(buy_orders, "buy_orders")
        sell_orders = self._validate_goods_vector(sell_orders, "sell_orders")

        base_prices = self.base_prices()
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

    def construction_cost(self, eco: EconomyState) -> float:
        """Calculate the total construction cost for an `EconomyState`.

        Args:
            eco: The `EconomyState` to evaluate (as produced by
                `solve`).

        Returns:
            The dot product of ``building_levels`` with the per-configuration
            construction cost vector.
        """
        return float(np.dot(eco.building_levels, self.construction_cost_vector()))

    def arable_land_vector(self) -> np.ndarray:
        """Return arable-land consumption per production configuration.

        Returns:
            A float vector aligned to the production table, with ``1.0`` for
            agricultural, plantation, ranching, and subsistence land-use
            configurations and ``0.0`` otherwise.
        """
        if "building_group" not in self.df_production.columns:
            return np.zeros(len(self.df_production), dtype=np.float64)
        return (
            self.df_production["building_group"]
            .isin(tuple(_ARABLE_LAND_BUILDING_GROUPS))
            .to_numpy(dtype=np.float64)
        )

    def arable_land_consumption(self, state: EconomyState) -> float:
        """Return the total arable land consumed by an economy state.

        Each building level consumes one unit of arable land when its building
        group is agricultural, plantation, ranching, or subsistence land use.

        Args:
            state: The `EconomyState` whose land consumption is summed.

        Returns:
            The sum of building-configuration levels in arable-land-consuming
            building groups.

        Raises:
            ValueError: If the state's building-level vector is not aligned to
                the production table.
        """
        expected_shape = (len(self.df_production),)
        if state.building_levels.shape != expected_shape:
            raise ValueError(
                "state.building_levels shape must match the production table."
            )

        return float(np.dot(state.building_levels, self.arable_land_vector()))

    def levels_per_building(self, state: EconomyState) -> dict[str, float]:
        """Return total levels per building across all PM configurations.

        Building levels in `EconomyState` are aligned to production-table
        rows, where one building can appear in many production-method
        configurations.  This method aggregates those configuration levels by
        building key while preserving the buildings' first-appearance order in
        `df_production`.

        Args:
            state: The `EconomyState` whose levels are aggregated.

        Returns:
            A mapping from every building key in the production table to its
            total level.  Unused buildings are included with value ``0.0``.

        Raises:
            ValueError: If the state's building-level vector is not aligned to
                the production table.
        """
        expected_shape = (len(self.df_production),)
        if state.building_levels.shape != expected_shape:
            raise ValueError(
                "state.building_levels shape must match the production table."
            )

        totals: dict[str, float] = {}
        for building, level in zip(
            self.df_production["building"], state.building_levels
        ):
            key = str(building)
            totals[key] = totals.get(key, 0.0) + float(level)
        return totals

    def solve(
        self,
        building_levels: np.ndarray[tuple[int], np.dtype[np.float64]],
        method: str = "nominal",
        imports: np.ndarray[tuple[int], np.dtype[np.float64]] | None = None,
        exports: np.ndarray[tuple[int], np.dtype[np.float64]] | None = None,
        throughput_multipliers: (
            np.ndarray[tuple[int], np.dtype[np.float64]] | None
        ) = None,
        pop_needs: np.ndarray[tuple[int], np.dtype[np.float64]] | None = None,
        economy_of_scale_level_cap: float = 0.0,
    ) -> EconomyState:
        """Solve for an `EconomyState` from a building-level vector.

        Args:
            building_levels: 1-D array of shape ``(n_buildings,)`` specifying
                the level of each building configuration in the production
                table.
            method: The solving method to use. ``"nominal"`` uses base prices;
                ``"market"`` derives prices from buy and sell orders.
            imports: 1-D array of shape ``(n_goods,)`` specifying imported
                goods. Defaults to zeros.
            exports: 1-D array of shape ``(n_goods,)`` specifying exported
                goods. Defaults to zeros.
            throughput_multipliers: Optional 1-D array of shape
                ``(n_buildings,)`` scaling each configuration's gross goods
                inputs and outputs. Defaults to no scaling.
            pop_needs: Optional 1-D array of shape ``(n_goods,)`` specifying
                population needs demand. Defaults to zeros.
            economy_of_scale_level_cap: Maximum building level contributing to
                economy of scale. The default ``0.0`` disables the effect; use
                ``20.0`` to cap the throughput bonus at +20%.

        Returns:
            An `EconomyState` describing the resulting state.

        Raises:
            ValueError: If *method* is not ``"nominal"`` or ``"market"``, if
                *building_levels* is not 1-D or its length does not match the
                number of rows in the production table, if *imports* or
                *exports* lengths do not match the number of goods, or if
                *throughput_multipliers* is not aligned to the production
                table, if *pop_needs* is not a non-negative finite
                goods-aligned vector, or if the economy-of-scale cap is
                negative or non-finite.
        """

        if building_levels.ndim != 1:
            raise ValueError("building_levels must be a 1-D array.")
        if building_levels.shape[0] != len(self.building_index()):
            raise ValueError(
                "building_levels length must match the number of rows in the "
                "production table."
            )
        if imports is None:
            imports = np.zeros(len(self.goods_index()), dtype=np.float64)
        elif imports.shape[0] != len(self.goods_index()):
            raise ValueError("imports length must match the number of goods.")
        if exports is None:
            exports = np.zeros(len(self.goods_index()), dtype=np.float64)
        elif exports.shape[0] != len(self.goods_index()):
            raise ValueError("exports length must match the number of goods.")
        if pop_needs is None:
            pop_needs = np.zeros(len(self.goods_index()), dtype=np.float64)
        else:
            pop_needs = self._validate_goods_vector(pop_needs, "pop_needs")
        bonuses = self.economy_of_scale_bonuses(
            building_levels, economy_of_scale_level_cap
        )
        if throughput_multipliers is None:
            throughput_multipliers = np.ones(len(self.df_production), dtype=np.float64)
        else:
            self._validate_throughput_multipliers(throughput_multipliers)
        throughput_multipliers = throughput_multipliers + bonuses
        if method == "nominal":
            return self._solve_nominal(
                building_levels,
                imports,
                exports,
                throughput_multipliers,
                pop_needs,
            )
        if method == "market":
            return self._solve_market(
                building_levels,
                imports,
                exports,
                throughput_multipliers,
                pop_needs,
            )
        raise ValueError(f"Invalid method: {method!r}")

    def _solve_nominal(
        self,
        building_levels: np.ndarray[tuple[int], np.dtype[np.float64]],
        imports: np.ndarray[tuple[int], np.dtype[np.float64]],
        exports: np.ndarray[tuple[int], np.dtype[np.float64]],
        throughput_multipliers: (np.ndarray[tuple[int], np.dtype[np.float64]] | None),
        pop_needs: np.ndarray[tuple[int], np.dtype[np.float64]],
    ) -> EconomyState:
        """Derive a nominal `EconomyState` from a building-level vector.

        Uses base (nominal) goods prices, gross goods output for supply, gross
        goods input plus supplied population needs for demand, per-profession
        employment, and per-profession
        ``start_quality_of_life`` for wealth.

        Args:
            building_levels: 1-D array of shape ``(n_buildings,)``.
            imports: 1-D array of shape ``(n_goods,)`` specifying imported
                goods.
            exports: 1-D array of shape ``(n_goods,)`` specifying exported
                goods.
            throughput_multipliers: Optional per-configuration multipliers for
                gross goods inputs and outputs.
            pop_needs: 1-D array of goods-aligned population needs demand.

        Returns:
            An `EconomyState` with prices, supply, demand, employment,
            and wealth derived from *building_levels*.
        """
        goods_input_matrix = self.goods_input_matrix(throughput_multipliers)
        goods_output_matrix = self.goods_output_matrix(throughput_multipliers)
        building_goods_input = building_levels @ goods_input_matrix
        building_goods_output = building_levels @ goods_output_matrix
        pops = building_levels[:, None] * self.employment_matrix()

        return EconomyState(
            building_levels=building_levels,
            building_goods_input=building_goods_input,
            building_goods_output=building_goods_output,
            imports=imports,
            exports=exports,
            market_prices=self.base_prices(),
            pops=pops,
            pop_wealth=np.broadcast_to(self.pop_wealth_init(), pops.shape).copy(),
            pop_balance=np.zeros((len(self.building_index()), len(self.pop_index()))),
            pop_needs=pop_needs,
        )

    def _solve_market(
        self,
        building_levels: np.ndarray[tuple[int], np.dtype[np.float64]],
        imports: np.ndarray[tuple[int], np.dtype[np.float64]],
        exports: np.ndarray[tuple[int], np.dtype[np.float64]],
        throughput_multipliers: (np.ndarray[tuple[int], np.dtype[np.float64]] | None),
        pop_needs: np.ndarray[tuple[int], np.dtype[np.float64]],
    ) -> EconomyState:
        """Derive a market-price `EconomyState` from a building vector."""
        state = self._solve_nominal(
            building_levels,
            imports,
            exports,
            throughput_multipliers,
            pop_needs,
        )
        return replace(
            state,
            market_prices=self.market_prices(state.buy_orders, state.sell_orders),
        )

    def df_buildings(self, eco: EconomyState) -> pd.DataFrame:
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
                "key": self.building_index(),
                "level": eco.building_levels,
                "construction_cost": self.construction_cost_vector()
                * eco.building_levels,
            }
        )
        df = df[df["level"] > 0].copy()
        df = df.sort_values(by="level", ascending=False)  # pyright: ignore[reportCallIssue]
        return df

    def df_market(self, eco: EconomyState) -> pd.DataFrame:
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
                "goods": self.goods_index(),
                "market_prices": eco.market_prices,
                "market_prices_variance": self.market_prices_variance(eco),
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

    def df_pop(self, eco: EconomyState) -> pd.DataFrame:
        """Export an `EconomyState`'s pop employment and wealth to a DataFrame.

        Each row describes one profession, aggregating the per-building arrays
        in *eco*.

        Args:
            eco: The `EconomyState` to export (as produced by
                `solve`).

        Returns:
            A ``DataFrame`` with columns ``"profession"``, ``"employment"``,
            ``"employment_share"``, ``"avg_wealth"``, ``"total_wealth"`` and
            ``"pop_balance"``, filtered to professions with non-zero employment
            and sorted by ``"employment"`` descending.
        """
        df = pd.DataFrame(
            {
                "profession": self.pop_index(),
                "employment": eco.employment_by_profession,
                "employment_share": eco.profession_shares,
                "avg_wealth": eco.wealth_by_profession,
                "total_wealth": (eco.pop_wealth * eco.pops).sum(axis=0),
                "pop_balance": eco.pop_balance.sum(axis=0),
            }
        )
        df = df[df["employment"] > 0].copy()
        df = df.sort_values(by="employment", ascending=False).reset_index(drop=True)  # pyright: ignore[reportCallIssue]
        return df
