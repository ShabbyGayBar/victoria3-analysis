from vic3_analysis import (
    VIC3_DIR,
    BuildingsParser,
    goods,
    production_method_groups,
    production_method,
    technology,
)
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


def production_analysis(game_dir: str | None = None) -> pd.DataFrame:
    if game_dir is None:
        game_dir = VIC3_DIR

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
