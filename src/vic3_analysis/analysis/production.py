"""
Economic production analysis for Victoria 3.

Provides :class:`ProductionUnit` for representing per-building-level
production data, :func:`production_table` for building a comprehensive
DataFrame of all possible building configurations, and
:class:`ProductionAnalyzer` for filtering and linear-programming optimisation
of building portfolios.
"""

from vic3_analysis import (
    get_vic3_directory,
    BuildingsParser,
    goods,
    production_method_groups,
    production_method,
    technology,
)
import re
import numpy as np
import scipy.optimize as opt
import pandas as pd
from itertools import product
from typing import Iterable, List, Tuple, Any


def _all_combinations(lists: List[Iterable[Any]]) -> Iterable[Tuple[Any, ...]]:
    """
    Lazily generate all combinations (Cartesian product) from n lists.

    Args:
        lists: A list of iterables (e.g., lists/tuples/ranges). Lists can be of different lengths.

    Yields:
        Tuples, each being one combination (one pick from each input list).
    """
    # Convert to list so multiple passes are safe (product may need to re-iterate)
    normalized = [list(lst) for lst in lists]
    # If any list is empty, the product is empty by definition
    if any(len(lst) == 0 for lst in normalized):
        return  # yields nothing
    yield from product(*normalized)


class ProductionUnit(dict):
    """A dict-like snapshot of one building level's production statistics.

    Stores goods flows (positive = output, negative = input), employment, and
    the earliest era at which this configuration becomes available.  Supports
    addition (``+``) to aggregate multiple production methods.

    """

    def __init__(self, production: dict[str, int], employment: int = 0, era: int = 0):
        """Initialise a :class:`ProductionUnit`.

        Args:
            production: Mapping of good keys to their net amounts per building
                level (positive = output, negative = input).
            employment: Number of pops employed per building level.
            era: Minimum era required to unlock this production configuration.
        """
        super().__init__()
        self["era"] = era
        self["employment"] = employment
        self.update(production)

    def __add__(self, other):
        """Combine two :class:`ProductionUnit` instances into one.

        Goods amounts are summed; ``"era"`` is set to the maximum of the two
        units; ``"employment"`` is summed.

        Args:
            other: Another :class:`ProductionUnit` (or compatible dict).

        Returns:
            A new :class:`ProductionUnit` representing the combined production.
        """
        result = self.copy()
        for key in other.keys():
            if key in self.keys():
                result[key] += other[key]
            else:
                result[key] = other[key]
        result["era"] = max(self["era"], other["era"])
        return ProductionUnit(production=result)

    def profit(self, goods_cost: dict[str, int]) -> int:
        """Calculate the net profit per building level.

        Args:
            goods_cost: Mapping of good keys to their base market prices.

        Returns:
            The net monetary value of all goods flows (revenues from outputs
            minus costs of inputs).
        """
        profit = 0
        for good, amount in self.items():
            if good in ["employment", "era"]:
                continue
            profit += goods_cost[good] * amount
        return profit

    def profit_per_employment(self, goods_cost: dict[str, int]) -> float:
        """Calculate profit divided by employment per building level.

        Args:
            goods_cost: Mapping of good keys to their base market prices.

        Returns:
            Net profit divided by total employment, or ``float("inf")`` when
            employment is zero.
        """
        if self["employment"] == 0:
            return float("inf")  # Infinite profit per employment if employment is zero
        return self.profit(goods_cost) / self["employment"]


def production_table(game_dir: str | None = None) -> pd.DataFrame:
    """Build a DataFrame of all possible building configurations and their stats.

    For every building that has a construction cost, enumerates every
    combination of production methods (one per production-method-group) and
    records the aggregated employment, goods flows, profit, era, and
    construction cost.

    Args:
        game_dir: Path to the Victoria 3 ``game`` directory.  If ``None`` the
            directory is located automatically via
            :func:`~vic3_analysis.utils.get_vic3_directory`.

    Returns:
        A ``DataFrame`` where each row represents one specific building
        configuration (a unique combination of production methods).  The
        ``"key"`` column encodes ``"<building>(<pm1>+<pm2>+...)"``; other
        columns include ``"building_group"``, ``"era"``,
        ``"construction_cost"``, ``"profit"``, ``"employment"``, and one
        column per tradeable good.
    """
    if game_dir is None:
        game_dir = get_vic3_directory()

    # Get goods costs
    df_goods = goods(game_dir)
    goods_dict = dict(zip(df_goods["key"], df_goods["cost"]))

    # Get technology to era mapping
    df_tech = technology(game_dir)
    tech_era_dict = dict(zip(df_tech["tech_key"], df_tech["era"]))

    # Get production method groups to production methods mapping
    pmg_pm_dict = production_method_groups(game_dir)

    buildings_tree = BuildingsParser(game_dir)
    # Get building to production method groups mapping
    building_pmg_dict = buildings_tree.production_method_groups()
    # Get building construction costs
    building_cost_dict = {}
    for building_key, building_values in buildings_tree.items():
        if "required_construction_points" in building_values.keys():
            building_cost_dict[building_key] = building_values[
                "required_construction_points"
            ]
    # Get building group information
    building_group_dict = {}
    for building_key, building_values in buildings_tree.items():
        if "building_group" in building_values.keys():
            building_group_dict[building_key] = building_values["building_group"]

    # Get production method employment and production output
    df_pm = production_method()
    pm_dict = {}
    for _, row in df_pm.iterrows():
        if row["building"] not in building_cost_dict:
            continue  # Skip if building is not in building_cost_dict
        pm_dict[row["production_method"]] = ProductionUnit(
            era=tech_era_dict.get(row["unlocking_technologies"], 0),
            employment=row["employment"],
            production={good: row[good] for good in goods_dict.keys() if good in row},
        )

    possible_buildings = []
    for building_key in building_cost_dict.keys():
        # list all possible combinations of production methods for this building
        pm_lists = []
        for pmg in building_pmg_dict[building_key]:
            pm_lists.append(pmg_pm_dict[pmg])
        # iterate through all combinations of production methods for this building
        for combo in _all_combinations(pm_lists):
            building = ProductionUnit(production={})
            key = building_key + "(" + "+".join(combo) + ")"
            for pm in combo:
                building += pm_dict[pm]
            row_dict = {"key": key}
            row_dict["building_group"] = building_group_dict[building_key]
            row_dict["era"] = building["era"]
            row_dict["construction_cost"] = building_cost_dict[building_key]
            row_dict["profit"] = building.profit(goods_dict)
            row_dict.update(building)
            possible_buildings.append(row_dict)

    result = pd.DataFrame(possible_buildings)
    return result


class OptimizeResult:
    """Structured result of an optimisation run, including the optimal building levels and summary statistics."""

    def __init__(
        self,
        key_index: List[str],
        level: np.ndarray[tuple[int], np.dtype[np.float64]],
        goods_index: List[str],
        net_goods: np.ndarray,
        profit: float,
        employment: float,
        construction_cost: float,
    ):
        """Initialise the optimisation result.

        Args:
            level: Optimal building levels as a 1-D array of shape ``(n_buildings,)``.
            net_goods: Net goods flows for the optimal allocation.
            profit: Total profit for the optimal allocation.
            employment: Total employment for the optimal allocation.
            construction_cost: Total construction cost for the optimal allocation.
        """
        self.key_index = key_index
        self.level = level
        self.goods_index = goods_index
        self.net_goods = net_goods
        self.gdp = profit * 52  # Convert weekly profit to annual GDP
        self.employment = employment
        self.construction_cost = construction_cost

    def gdp_per_capita(self) -> float:
        """Calculate GDP per capita for the optimal allocation.

        Returns:
            GDP divided by employment, or ``float("inf")`` if employment is zero.
        """
        if self.employment == 0:
            return float("inf")
        return self.gdp / self.employment

    def level_to_df(self) -> pd.DataFrame:
        df = pd.DataFrame(
            {
                "building_key": self.key_index,
                "level": self.level,
            }
        )
        # remove rows with zero level
        df = df[df["level"] > 0].copy()
        # sort by optimized level in descending order
        df = df.sort_values(by="level", ascending=False)
        return df

    def net_goods_to_df(self) -> pd.DataFrame:
        goods_index = self.goods_index
        df = pd.DataFrame(
            {
                "goods": goods_index,
                "output": self.net_goods,
            }
        )
        # remove rows with zero level
        df = df[df["output"] > 0].copy()
        # sort by optimized level in descending order
        df = df.sort_values(by="output", ascending=False)
        return df

    def __str__(self) -> str:
        return (
            f"Optimal GDP: {self.gdp}\n"
            f"Optimal Employment: {self.employment}\n"
            f"Optimal GDP per Capita: {self.gdp_per_capita()}\n"
            f"Optimal Construction Cost: {self.construction_cost}\n"
            f"Optimal Building Levels:\n{self.level_to_df()}\n"
            f"Net Goods Output:\n{self.net_goods_to_df()}"
        )


class ProductionAnalyzer:
    """Wraps a production table DataFrame and provides analysis/optimisation helpers.

    Attributes:
        df: The active (potentially filtered) production table.
        df_raw: An unmodified copy of the original production table, used by
            :meth:`restore` to reset any applied filters.
    """

    def __init__(self, game_dir: str | None = None, df: pd.DataFrame | None = None):
        """Initialise the analyser.

        Args:
            game_dir: Path to the Victoria 3 ``game`` directory.  Ignored when
                *df* is provided.  If ``None`` the directory is located
                automatically via
                :func:`~vic3_analysis.utils.get_vic3_directory`.
            df: Pre-built production table DataFrame.  When provided,
                *game_dir* is not used.
        """
        if df is not None:
            self.df = df
        else:
            self.df = production_table(game_dir)
        self.df_raw = self.df.copy()  # Keep a copy of the raw DataFrame for reference

    def goods_index(self) -> List[str]:
        """Return the list of good-key column names in the active DataFrame.

        Returns:
            Column names that represent tradeable goods (i.e. all columns
            except ``"key"``, ``"building_group"``, ``"era"``,
            ``"construction_cost"``, ``"profit"``, and ``"employment"``).
        """
        return [
            col
            for col in self.df.columns
            if col
            not in [
                "key",
                "building_group",
                "era",
                "construction_cost",
                "profit",
                "employment",
            ]
        ]

    def goods_matrix(self) -> np.ndarray:
        """Return a NumPy matrix of goods flows for all active rows.

        Returns:
            A 2-D array of shape ``(n_buildings, n_goods)`` containing the net
            goods amounts for every building configuration.
        """
        goods_index = self.goods_index()
        return self.df[goods_index].to_numpy()

    def production_index(self) -> List[str]:
        """Return the list of production-related column names.

        Returns:
            Column names that represent production values (i.e. all columns
            except ``"key"``, ``"building_group"``, and ``"era"``).
        """
        return [
            col
            for col in self.df.columns
            if col not in ["key", "building_group", "era"]
        ]

    def production_matrix(self) -> np.ndarray:
        """Return a NumPy matrix of all production values for active rows.

        Returns:
            A 2-D array of shape ``(n_buildings, n_production_cols)``.
        """
        return self.df[self.production_index()].to_numpy()

    def key_index(self) -> List[str]:
        """Return the list of building-configuration keys for active rows.

        Returns:
            Values from the ``"key"`` column, in DataFrame order.
        """
        return self.df["key"].tolist()

    def profit_vector(self) -> np.ndarray:
        """Return a 1-D NumPy array of per-level profits for active rows.

        Returns:
            Array of shape ``(n_buildings,)`` containing the net profit value
            for each building configuration.
        """
        return self.df["profit"].to_numpy()

    def employment_vector(self) -> np.ndarray:
        """Return a 1-D NumPy array of per-level employment for active rows.

        Returns:
            Array of shape ``(n_buildings,)`` containing the employment count
            for each building configuration.
        """
        return self.df["employment"].to_numpy()

    def construction_cost_vector(self) -> np.ndarray:
        """Return a 1-D NumPy array of construction costs for active rows.

        Returns:
            Array of shape ``(n_buildings,)`` with the construction cost for
            each building configuration.
        """
        return self.df["construction_cost"].to_numpy()

    def era_vector(self) -> np.ndarray:
        """Return a 1-D NumPy array of era requirements for active rows.

        Returns:
            Array of shape ``(n_buildings,)`` with the minimum era required to
            unlock each building configuration.
        """
        return self.df["era"].to_numpy()

    def find_same_buildings(self, building_key: str) -> List[int]:
        """Return DataFrame indices of all configurations for a given building.

        Args:
            building_key: The building identifier prefix to search for (e.g.
                ``"building_iron_mine"``).

        Returns:
            List of integer row indices whose ``"key"`` column starts with
            *building_key*.
        """
        return self.df[self.df["key"].str.startswith(building_key)].index.tolist()

    def find_same_building_group(self, building_group: str) -> List[int]:
        """Return DataFrame indices of all configurations in a building group.

        Args:
            building_group: The building-group identifier to filter by.

        Returns:
            List of integer row indices whose ``"building_group"`` column
            matches *building_group* exactly.
        """
        return self.df[self.df["building_group"] == building_group].index.tolist()

    def restore(self):
        """Reset ``self.df`` to the original unfiltered production table."""
        self.df = self.df_raw.copy()

    def add_throughput_bonus(self, building_key: str, bonus_multiplier: float):
        """Add a throughput bonus to all configurations of a specific building.

        This method modifies the active DataFrame in-place, increasing the
        profit and net goods of all configurations of *building_key* by
        multiplying them by *bonus_multiplier*.

        Args:
            building_key: The building identifier prefix to search for (e.g.
                ``"building_iron_mine"``).
            bonus_multiplier: The factor by which to multiply the profit and
                net goods of the affected configurations (e.g. 1.5 for a 50%
                bonus).
        """
        indices = self.find_same_buildings(building_key)
        self.df.loc[indices, "profit"] *= bonus_multiplier
        goods_index = self.goods_index()
        self.df.loc[indices, goods_index] *= bonus_multiplier

    def filter_by_era(self, era: int):
        """Keep only building configurations unlocked before *era*.

        Args:
            era: Only rows with ``"era" < era`` are retained.
        """
        self.df = self.df[self.df["era"] < era].copy()

    def filter_by_building_group(self, building_group: str):
        """Remove all configurations belonging to *building_group*.

        Args:
            building_group: The building-group identifier to exclude.
        """
        self.df = self.df[self.df["building_group"] != building_group].copy()

    def filter_by_production_method(self, production_method_key: str):
        """Remove configurations that include a specific production method.

        Args:
            production_method_key: The production-method key that should be
                excluded.  Any configuration key matching
                ``"<building_key>(...<production_method_key>...)"`` is dropped.
        """
        pattern = re.compile(rf"\b{re.escape(production_method_key)}\b")
        self.df = self.df[~self.df["key"].str.contains(pattern)].copy()

    def constraint_limit_import(
        self, limit: float = 0.0
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Build an inequality constraint that caps net imports of each good.

        Returns a matrix–vector pair ``(A, b)`` such that ``A @ x <= b``
        enforces that the net import of every good does not exceed *limit*
        building levels.

        Args:
            limit: Maximum allowable net import per good.  Defaults to ``0.0``
                (no imports allowed).

        Returns:
            A tuple ``(A, b)`` where *A* has shape
            ``(n_goods, n_buildings)`` and *b* is a vector of *limit* values
            of length ``n_goods``.
        """
        A = -self.goods_matrix().T  # Negate to convert to <= 0 form
        b = (
            np.ones(self.goods_matrix().shape[1]) * limit
        )  # Vector of limits for <= constraints
        return A, b

    def constraint_limit_employment(
        self, limit: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Build an inequality constraint that caps total employment.

        Returns a row-vector–scalar pair ``(A, b)`` such that ``A @ x <= b``
        enforces that the dot product of the employment vector with the
        building-level vector does not exceed *limit*.

        Args:
            limit: Maximum total employment allowed.

        Returns:
            A tuple ``(A, b)`` where *A* is the transposed employment vector
            of shape ``(1, n_buildings)`` and *b* is ``[limit]``.
        """
        return self.employment_vector().T, np.array([limit])

    def constraint_limit_construction_cost(
        self, limit: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Build an inequality constraint that caps total construction cost.

        Returns a row-vector–scalar pair ``(A, b)`` such that ``A @ x <= b``
        enforces that the total construction cost of all selected buildings
        does not exceed *limit*.

        Args:
            limit: Maximum total construction cost allowed.

        Returns:
            A tuple ``(A, b)`` where *A* is the transposed construction-cost
            vector of shape ``(1, n_buildings)`` and *b* is ``[limit]``.
        """
        return self.construction_cost_vector().T, np.array([limit])

    def constraint_limit_building(
        self, building_key: str, limit: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Build an inequality constraint that limits levels of one building type.

        Returns a row-vector–scalar pair ``(A, b)`` such that ``A @ x <= b``
        limits the total levels of the specified building to at most *limit*.

        Args:
            building_key: The building identifier prefix to restrict.
            limit: Maximum combined level for all configurations of this
                building.

        Returns:
            A tuple ``(A, b)`` where *A* is a binary indicator vector of shape
            ``(1, n_buildings)`` and *b* is ``[limit]``.
        """
        indices = self.find_same_buildings(building_key)
        A = np.zeros(len(self.df))
        for idx in indices:
            A[idx] = 1
        b = np.array([limit])
        return A, b

    def constraint_produce(
        self, good_key: str, limit: float = 1
    ) -> Tuple[np.ndarray, np.ndarray]:
        """Build an inequality constraint requiring minimum production of a good.

        Returns a row-vector–scalar pair ``(A, b)`` such that ``A @ x <= b``
        enforces that the net production of *good_key* is at least *limit*.

        Args:
            good_key: The good identifier that must be produced.
            limit: Minimum required net production of the good.  Defaults to
                ``1``.

        Returns:
            A tuple ``(A, b)`` where *A* is the negated production column for
            *good_key* of shape ``(1, n_buildings)`` and *b* is ``[-limit]``.

        Raises:
            ValueError: If *good_key* is not present in the goods index.
        """
        goods_index = self.goods_index()
        if good_key not in goods_index:
            raise ValueError(f"Good '{good_key}' not found in goods index.")
        idx = goods_index.index(good_key)
        A = -self.goods_matrix()[:, idx].T  # Negate to convert to >= limit form
        b = np.array([-limit])  # Vector of limits for >= constraints
        return A, b

    def profit(self, level: np.ndarray[tuple[int], np.dtype[np.float64]]) -> float:
        """Calculate total profit for a given building-level allocation.

        Args:
            level: 1-D array of shape ``(n_buildings,)`` specifying the level
                of each building configuration.

        Returns:
            Total profit for the given allocation.
        """
        return float(np.dot(level, self.profit_vector()))

    def employment(self, level: np.ndarray[tuple[int], np.dtype[np.float64]]) -> float:
        """Calculate total employment for a given building-level allocation.

        Args:
            level: 1-D array of shape ``(n_buildings,)`` specifying the level
                of each building configuration.
        Returns:
            Total employment for the given allocation.
        """
        return float(np.dot(level, self.employment_vector()))

    def construction_cost(
        self, level: np.ndarray[tuple[int], np.dtype[np.float64]]
    ) -> float:
        """Calculate total construction cost for a given building-level allocation.

        Args:
            level: 1-D array of shape ``(n_buildings,)`` specifying the level
                of each building configuration.
        Returns:
            Total construction cost for the given allocation.
        """
        return float(np.dot(level, self.construction_cost_vector()))

    def net_goods(
        self, level: np.ndarray[tuple[int], np.dtype[np.float64]]
    ) -> np.ndarray:
        """Calculate net goods flows for a given building-level allocation.

        Args:
            level: 1-D array of shape ``(n_buildings,)`` specifying the level
                of each building configuration.
        Returns:
            Net goods flows for the given allocation.
        """
        return np.dot(level, self.goods_matrix())

    def profit_per_capita(
        self, level: np.ndarray[tuple[int], np.dtype[np.float64]]
    ) -> float:
        """Calculate profit per capita for a given building-level allocation.

        Args:
            level: 1-D array of shape ``(n_buildings,)`` specifying the level
                of each building configuration.

        Returns:
            Total profit divided by total employment, or ``float("inf")`` when
            total employment is zero.

        Raises:
            ValueError: If *level* is not 1-D or its length does not match the
                number of rows in ``self.df``.
        """
        if level.ndim != 1:
            raise ValueError("level must be a 1-D array.")
        if level.shape[0] != len(self.df):
            raise ValueError("level length must match the number of rows in self.df.")

        total_employment = self.employment(level)
        if total_employment == 0:
            return float("inf")  # Infinite profit per capita if no employment
        return self.profit(level) / total_employment

    def linprog(
        self,
        c: np.ndarray[tuple[int], np.dtype[np.float64]],
        inequality_constraints: List[Tuple[np.ndarray, np.ndarray]],
        equality_constraints: List[Tuple[np.ndarray, np.ndarray]] = [],
    ) -> OptimizeResult:
        """Solve a linear programme over building levels.

        Minimises ``c @ x`` subject to the given inequality and equality
        constraints, where ``x`` is the vector of building levels.

        Args:
            c: Objective coefficient vector of shape ``(n_buildings,)``.
                Pass the negated profit vector to *maximise* profit.
            inequality_constraints: List of ``(A, b)`` pairs representing
                ``A @ x <= b`` constraints (as produced by the
                ``constraint_*`` methods).
            equality_constraints: List of ``(A, b)`` pairs representing
                ``A @ x == b`` constraints.  Defaults to an empty list.

        Returns:
            A ``DataFrame`` with columns ``"building_key"`` and
            ``"optimized_level"``, sorted by ``"optimized_level"`` in
            descending order.

        Raises:
            ValueError: If ``scipy.optimize.linprog`` reports that the
                optimisation failed.
        """
        A_ub = (
            np.vstack([constraint[0] for constraint in inequality_constraints])
            if inequality_constraints
            else None
        )
        b_ub = (
            np.hstack([constraint[1] for constraint in inequality_constraints])
            if inequality_constraints
            else None
        )
        A_eq = (
            np.vstack([constraint[0] for constraint in equality_constraints])
            if equality_constraints
            else None
        )
        b_eq = (
            np.hstack([constraint[1] for constraint in equality_constraints])
            if equality_constraints
            else None
        )
        res = opt.linprog(c=c, A_ub=A_ub, b_ub=b_ub, A_eq=A_eq, b_eq=b_eq)
        if not res.success:
            raise ValueError(f"Optimization failed: {res.message}")
        return OptimizeResult(
            key_index=self.key_index(),
            level=res.x,
            goods_index=self.goods_index(),
            net_goods=self.net_goods(res.x),
            profit=self.profit(res.x),
            employment=self.employment(res.x),
            construction_cost=self.construction_cost(res.x),
        )
