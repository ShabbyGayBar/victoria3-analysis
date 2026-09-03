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

from vic3_analysis import (
    BuildingsParser,
    PopTypesParser,
    ProductionMethodParser,
    goods,
    production_table,
    technology,
)


def _warning_missing_columns(missing: set[str], table_name: str) -> None:
    if missing:
        warnings.warn(f"Missing {table_name} columns: {sorted(missing)}")


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
            -self.df_production.reindex(columns=goods_columns, fill_value=0).to_numpy(
                dtype=np.float64
            ),
            0,
        )

    def goods_output_matrix(self) -> np.ndarray:
        goods_columns = [f"goods_{good}" for good in self.goods_index()]

        missing = set(goods_columns) - set(self.df_production.columns)
        _warning_missing_columns(missing, "goods output")

        return np.maximum(
            self.df_production.reindex(columns=goods_columns, fill_value=0).to_numpy(
                dtype=np.float64
            ),
            0,
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

    def employment_vector(self) -> np.ndarray:
        """Total employment per building level, aligned to production-table rows.

        Returns:
            A 1-D array of shape ``(n_buildings,)`` giving the total employment
            of each building configuration per level (``"employment"`` column,
            missing values zero-filled).
        """
        return self.df_production["employment"].fillna(0).to_numpy(dtype=np.float64)

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

    def df_buildings(self, eco: EconomyState) -> pd.DataFrame:
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
        df = df.sort_values(by="level", ascending=False)  # pyright: ignore[reportCallIssue]
        return df

    def df_market(self, eco: EconomyState) -> pd.DataFrame:
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
        df = df.sort_values(by="sell_orders", ascending=False)  # pyright: ignore[reportCallIssue]
        return df

    def df_pop(self, eco: EconomyState) -> pd.DataFrame:
        """Export an :class:`EconomyState`'s pop employment and wealth to a DataFrame.

        Each row describes one profession, aggregating the per-building arrays
        in *eco*.

        Args:
            eco: The :class:`EconomyState` to export (as produced by
                :meth:`solve`).

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
