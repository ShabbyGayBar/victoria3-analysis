"""
General-equilibrium economy model for Victoria 3.

Defines :class:`EconomyState` as the solver state (building levels, prices,
supply, demand, employment, and wealth) and :class:`Economy` which derives a
nominal :class:`EconomyState` from a building-level vector using base goods
prices and per-profession wealth from the pop-types table.
"""

import warnings
from dataclasses import dataclass
from functools import cached_property
from pathlib import Path

import numpy as np
import pandas as pd

from vic3_analysis import PopTypesParser, goods, production_table


def _warning_missing_columns(missing: set[str], table_name: str) -> None:
    if missing:
        warnings.warn(f"Missing {table_name} columns: {sorted(missing)}")


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
    def average_wealth(self) -> float:
        """Calculate the employment-weighted average wealth.

        Returns:
            The weighted average of ``wealth`` by ``employment``, or ``0.0``
            when total employment is zero.
        """
        total_employment = np.sum(self.pops)
        if total_employment == 0:
            return 0.0
        return float(np.sum(self.pop_wealth * self.pops) / total_employment)


class Economy:
    """Builds :class:`EconomyState` instances from building-level vectors.

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
                :func:`~vic3_analysis.utils.get_vic3_directory`. Ignored for
                any table whose DataFrame is passed directly.
            df_production: Pre-built production table DataFrame. When
                provided, overrides the table that would otherwise be generated
                by :func:`~vic3_analysis.production_table`. Useful for reusing a
                filtered or cached table.
            df_goods: Pre-built goods table DataFrame. When provided,
                overrides the table that would otherwise be generated by
                :func:`~vic3_analysis.goods`.
            df_pop_types: Pre-built pop-types table DataFrame. When provided,
                overrides the table that would otherwise be generated by
                :class:`~vic3_analysis.PopTypesParser`.
        """
        if df_production is None:
            df_production = production_table(game_dir)
        if df_goods is None:
            df_goods = goods(game_dir)
        if df_pop_types is None:
            df_pop_types = PopTypesParser(game_dir).to_dataframe()
        self.df_production = df_production
        self.df_goods = df_goods
        self.df_pop_types = df_pop_types

    def building_index(self) -> list[str]:
        # Building-configuration keys (building+production_method) in df_production.
        return [
            f"{b}+{pm}"
            for b, pm in zip(
                self.df_production["building"],
                self.df_production["production_method"],
            )
        ]

    def goods_index(self) -> list[str]:
        # Good keys in df_goods row order.
        return self.df_goods["key"].tolist()

    def pop_index(self) -> list[str]:
        # Profession keys in df_pop_types row order.
        return self.df_pop_types["key"].tolist()

    def base_prices(self) -> np.ndarray:
        # Base prices aligned to the goods index.
        return self.df_goods["cost"].to_numpy(dtype=np.float64)

    def goods_input_matrix(self) -> np.ndarray:
        goods_columns = [f"goods_{good}" for good in self.goods_index()]

        missing = set(goods_columns) - set(self.df_production.columns)
        _warning_missing_columns(missing, "goods input")

        return np.maximum(
            -self.df_production.reindex(columns=goods_columns, fill_value=0), 0
        )

    def goods_output_matrix(self) -> np.ndarray:
        goods_columns = [f"goods_{good}" for good in self.goods_index()]

        missing = set(goods_columns) - set(self.df_production.columns)
        _warning_missing_columns(missing, "goods output")

        return np.maximum(
            self.df_production.reindex(columns=goods_columns, fill_value=0), 0
        )

    def employment_matrix(self) -> np.ndarray:
        employment_columns = [f"employment_{pop}" for pop in self.pop_index()]

        missing = set(employment_columns) - set(self.df_production.columns)
        _warning_missing_columns(missing, "employment")

        return self.df_production.reindex(
            columns=employment_columns, fill_value=0
        ).to_numpy(dtype=np.float64)

    def pop_wealth_init(self) -> np.ndarray:
        return self.df_pop_types["start_quality_of_life"].to_numpy(dtype=np.float64)

    def construction_cost_vector(self) -> np.ndarray:
        # Construction cost per building level aligned to production-table rows.
        return self.df_production["construction_cost"].to_numpy(dtype=np.float64)

    def market_prices_variance(self, eco: EconomyState) -> np.ndarray:
        """Calculate the market prices variance from base prices.

        Args:
            eco: The :class:`Economy` to evaluate (as produced by
                :meth:`solve`).

        Returns:
            A 1-D array of shape ``(n_goods,)`` containing the market prices variance.
        """
        return (eco.market_prices / self.base_prices() - 1) * 100

    def construction_cost(self, eco: EconomyState) -> float:
        """Calculate the total construction cost for an :class:`EconomyState`.

        Args:
            eco: The :class:`EconomyState` to evaluate (as produced by
                :meth:`solve`).

        Returns:
            The dot product of ``building_levels`` with the per-configuration
            construction cost vector.
        """
        return float(np.dot(eco.building_levels, self.construction_cost_vector()))

    def solve(
        self,
        building_levels: np.ndarray[tuple[int], np.dtype[np.float64]],
        method: str = "nominal",
        imports: np.ndarray[tuple[int], np.dtype[np.float64]] | None = None,
        exports: np.ndarray[tuple[int], np.dtype[np.float64]] | None = None,
    ) -> EconomyState:
        """Solve for an :class:`EconomyState` from a building-level vector.

        Args:
            building_levels: 1-D array of shape ``(n_buildings,)`` specifying
                the level of each building configuration in the production
                table.
            method: The solving method to use. Currently only ``"nominal"`` is
                supported.
            imports: 1-D array of shape ``(n_goods,)`` specifying imported
                goods. Defaults to zeros.
            exports: 1-D array of shape ``(n_goods,)`` specifying exported
                goods. Defaults to zeros.

        Returns:
            An :class:`EconomyState` describing the resulting state.

        Raises:
            ValueError: If *method* is not ``"nominal"``, if
                *building_levels* is not 1-D or its length does not match the
                number of rows in the production table, or if *imports* or
                *exports* lengths do not match the number of goods.
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

        if method == "nominal":
            return self._solve_nominal(building_levels, imports, exports)
        raise ValueError(f"Invalid method: {method!r}")

    def _solve_nominal(
        self,
        building_levels: np.ndarray[tuple[int], np.dtype[np.float64]],
        imports: np.ndarray[tuple[int], np.dtype[np.float64]],
        exports: np.ndarray[tuple[int], np.dtype[np.float64]],
    ) -> EconomyState:
        """Derive a nominal :class:`EconomyState` from a building-level vector.

        Uses base (nominal) goods prices, gross goods output for supply, gross
        goods input for demand (pop consumption is not yet integrated),
        per-profession employment, and per-profession
        ``start_quality_of_life`` for wealth.

        Args:
            building_levels: 1-D array of shape ``(n_buildings,)``.
            imports: 1-D array of shape ``(n_goods,)`` specifying imported
                goods.
            exports: 1-D array of shape ``(n_goods,)`` specifying exported
                goods.

        Returns:
            An :class:`EconomyState` with prices, supply, demand, employment,
            and wealth derived from *building_levels*.
        """
        building_goods_input = building_levels @ self.goods_input_matrix()
        building_goods_output = building_levels @ self.goods_output_matrix()
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
            pop_needs=np.zeros(len(self.goods_index()), dtype=np.float64),
        )

    def buildings_to_df(self, eco: EconomyState) -> pd.DataFrame:
        """Export an :class:`EconomyState`'s building registry to a DataFrame.

        Args:
            eco: The :class:`EconomyState` to export (as produced by
                :meth:`solve`).

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
        df = df.sort_values(by="level", ascending=False)
        return df

    def market_to_df(self, eco: EconomyState) -> pd.DataFrame:
        """Export an :class:`EconomyState`'s market stats to a DataFrame.

        Args:
            eco: The :class:`EconomyState` to export (as produced by
                :meth:`solve`).

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
        df = df.sort_values(by="sell_orders", ascending=False)
        return df

    def pop_to_df(self, eco: EconomyState) -> pd.DataFrame:
        """Export an :class:`EconomyState`'s pop employment and wealth to a DataFrame.

        Args:
            eco: The :class:`EconomyState` to export (as produced by
                :meth:`solve`).

        Returns:
            A ``DataFrame`` with a single column ``"profession"`` listing the
            professions in ``df_pop_types`` row order.
        """
        df = pd.DataFrame(
            {
                "profession": self.pop_index(),
            }
        )
        return df

    def to_dataframe(self, eco: EconomyState) -> dict[str, pd.DataFrame]:
        """Export all data attributes of an :class:`EconomyState` to DataFrames.

        A single entry point that returns the per-axis DataFrames produced by
        :meth:`buildings_to_df`, :meth:`market_to_df` and
        :meth:`pop_to_df`.

        Args:
            eco: The :class:`EconomyState` to export (as produced by
                :meth:`solve`).

        Returns:
            A dict mapping ``"buildings"``, ``"market"`` and ``"pops"`` to
            their respective DataFrames.
        """
        return {
            "buildings": self.buildings_to_df(eco),
            "market": self.market_to_df(eco),
            "pops": self.pop_to_df(eco),
        }
