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

    def __init__(self, production: dict[str, int], employment: int = 0, era: int = 0):
        super().__init__()
        self["era"] = era
        self["employment"] = employment
        self.update(production)

    def __add__(self, other):
        result = self.copy()
        for key in other.keys():
            if key in self.keys():
                result[key] += other[key]
            else:
                result[key] = other[key]
        result["era"] = max(self["era"], other["era"])
        return ProductionUnit(production=result)

    def profit(self, goods_cost: dict[str, int]) -> int:
        profit = 0
        for good, amount in self.items():
            if good in ["employment", "era"]:
                continue
            profit += goods_cost[good] * amount
        return profit

    def profit_per_employment(self, goods_cost: dict[str, int]) -> float:
        if self["employment"] == 0:
            return float("inf")  # Infinite profit per employment if employment is zero
        return self.profit(goods_cost) / self["employment"]


def production_table(game_dir: str | None = None) -> pd.DataFrame:
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


class ProductionAnalyzer:
    def __init__(self, game_dir: str | None = None, df: pd.DataFrame | None = None):
        if df is not None:
            self.df = df
        else:
            self.df = production_table(game_dir)
        self.df_raw = self.df.copy()  # Keep a copy of the raw DataFrame for reference

    def goods_index(self) -> List[str]:
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
        goods_index = self.goods_index()
        return self.df[goods_index].to_numpy()

    def production_index(self) -> List[str]:
        return [
            col
            for col in self.df.columns
            if col not in ["key", "building_group", "era"]
        ]

    def production_matrix(self) -> np.ndarray:
        return self.df[self.production_index()].to_numpy()

    def key_index(self) -> List[str]:
        return self.df["key"].tolist()

    def profit_vector(self) -> np.ndarray:
        return self.df["profit"].to_numpy()

    def employment_vector(self) -> np.ndarray:
        return self.df["employment"].to_numpy()

    def construction_cost_vector(self) -> np.ndarray:
        return self.df["construction_cost"].to_numpy()

    def era_vector(self) -> np.ndarray:
        return self.df["era"].to_numpy()

    def find_same_buildings(self, building_key: str) -> List[int]:
        return self.df[self.df["key"].str.startswith(building_key)].index.tolist()

    def find_same_building_group(self, building_group: str) -> List[int]:
        return self.df[self.df["building_group"] == building_group].index.tolist()

    def restore(self):
        self.df = self.df_raw.copy()

    def filter_by_era(self, era: int):
        self.df = self.df[self.df["era"] < era].copy()

    def filter_by_building_group(self, building_group: str):
        self.df = self.df[self.df["building_group"] != building_group].copy()

    def filter_by_production_method(
        self, building_key: str, production_method_key: str
    ):
        pattern = re.compile(rf"{building_key}\((?=.*{production_method_key}).*\)")
        matches = self.df["key"].apply(lambda x: bool(pattern.match(x)))
        self.df = self.df[~matches].copy()

    def constraint_limit_import(
        self, limit: float = 0.0
    ) -> Tuple[np.ndarray, np.ndarray]:
        # Constraint: No imports more than the limit (default is 0, meaning no imports allowed)
        A = -self.goods_matrix().T  # Negate to convert to <= 0 form
        b = (
            np.ones(self.goods_matrix().shape[1]) * limit
        )  # Vector of limits for <= constraints
        return A, b

    def constraint_limit_employment(
        self, limit: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        # Constraint: Total employment must be less than or equal to the limit
        return self.employment_vector().T, np.array([limit])

    def constraint_limit_construction_cost(
        self, limit: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        # Constraint: Total construction cost must be less than or equal to the limit
        return self.construction_cost_vector().T, np.array([limit])

    def constraint_limit_building(
        self, building_key: str, limit: float
    ) -> Tuple[np.ndarray, np.ndarray]:
        # Constraint: Cannot build specific building more than the limit
        indices = self.find_same_buildings(building_key)
        A = np.zeros(len(self.df))
        for idx in indices:
            A[idx] = 1
        b = np.array([limit])
        return A, b

    def constraint_produce(
        self, good_key: str, limit: float = 1
    ) -> Tuple[np.ndarray, np.ndarray]:
        # Constraint: Must produce at least a certain amount of a specific good
        goods_index = self.goods_index()
        if good_key not in goods_index:
            raise ValueError(f"Good '{good_key}' not found in goods index.")
        idx = goods_index.index(good_key)
        A = -self.goods_matrix()[:, idx].T  # Negate to convert to >= limit form
        b = np.array([-limit])  # Vector of limits for >= constraints
        return A, b

    def gdp_per_capita(
        self, level: np.ndarray[tuple[int], np.dtype[np.float64]]
    ) -> float:
        if level.ndim != 1:
            raise ValueError("level must be a 1-D array.")
        if level.shape[0] != len(self.df):
            raise ValueError("level length must match the number of rows in self.df.")

        total_profit = float(np.dot(level, self.profit_vector()))
        total_employment = float(np.dot(level, self.employment_vector()))
        if total_employment == 0:
            return float("inf")  # Infinite GDP per capita if no employment
        return total_profit / total_employment

    def linprog(
        self,
        c: np.ndarray[tuple[int], np.dtype[np.float64]],
        inequality_constraints: List[Tuple[np.ndarray, np.ndarray]],
        equality_constraints: List[Tuple[np.ndarray, np.ndarray]] = [],
    ) -> pd.DataFrame:
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
        df = pd.DataFrame(
            {
                "building_key": self.key_index(),
                "optimized_level": res.x,
            }
        )
        # sort by optimized level in descending order
        df = df.sort_values(by="optimized_level", ascending=False)
        return df
