"""
Economic production analysis for Victoria 3.

Provides :class:`ProductionUnit` for representing per-building-level
production data and :func:`production_table` for building a comprehensive
DataFrame of all possible building configurations.
"""

from vic3_analysis import (
    get_vic3_directory,
    BuildingsParser,
    goods,
    production_method_groups,
    ProductionMethodParser,
    technology,
)
from pathlib import Path
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

    Stores goods flows (positive = output, negative = input), total and
    per-profession employment, and the earliest era at which this
    configuration becomes available.  Supports addition (``+``) to aggregate
    multiple production methods.

    """

    def __init__(
        self,
        production: dict[str, int],
        employment: int = 0,
        era: int = 0,
        employment_by_profession: dict[str, int] | None = None,
    ):
        """Initialise a :class:`ProductionUnit`.

        Args:
            production: Mapping of good keys to their net amounts per building
                level (positive = output, negative = input).
            employment: Number of pops employed per building level.
            era: Minimum era required to unlock this production configuration.
            employment_by_profession: Mapping of ``"<profession>"`` keys to the
                number of pops of that profession employed per building level.
                Stored as ``"employment_<profession>"`` entries.
        """
        super().__init__()
        self["era"] = era
        self["employment"] = employment
        self.update(production)
        if employment_by_profession:
            for profession, amount in employment_by_profession.items():
                self[f"employment_{profession}"] = amount

    def __add__(self, other):
        """Combine two :class:`ProductionUnit` instances into one.

        Goods amounts, employment (total and per-profession) are summed;
        ``"era"`` is set to the maximum of the two units.

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

    def profit_nominal(self, goods_cost: dict[str, int]) -> int:
        """Calculate the net nominal profit per building level.

        Args:
            goods_cost: Mapping of good keys to their base market prices.

        Returns:
            The net monetary value of all goods flows (revenues from outputs
            minus costs of inputs).
        """
        profit = 0
        for good, amount in self.items():
            if good == "era" or good.startswith("employment"):
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
        return self.profit_nominal(goods_cost) / self["employment"]


def production_table(game_dir: str | Path | None = None) -> pd.DataFrame:
    """Build a DataFrame of all possible building configurations and their stats.

    For every building that has a construction cost, enumerates every
    combination of production methods (one per production-method-group) and
    records the aggregated employment (total and per profession), goods flows,
    nominal profit, era, and construction cost.

    Args:
        game_dir: Path to the Victoria 3 ``game`` directory.  If ``None`` the
            directory is located automatically via
            :func:`~vic3_analysis.utils.get_vic3_directory`.

    Returns:
        A ``DataFrame`` where each row represents one specific building
        configuration (a unique combination of production methods).  The
        ``"building"`` column holds the building key and the
        ``"production_method"`` column holds the concatenated production
        methods (``"<pm1>+<pm2>+..."``); other columns include
        ``"building_group"``, ``"era"``, ``"construction_cost"``,
        ``"profit_nominal"``, ``"employment"``, ``"employment_<profession>"`` (one
        per profession), and one ``"goods_<good>"`` column per tradeable good.
    """
    if game_dir is None:
        game_dir = get_vic3_directory()

    # Get goods costs
    df_goods = goods(game_dir)
    goods_dict = dict(zip(df_goods["key"], df_goods["cost"]))

    # Get technology to era mapping
    df_tech = technology(game_dir)
    tech_era_dict = dict(zip(df_tech["key"], df_tech["era"]))

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
    df_pm = ProductionMethodParser(game_dir).to_dataframe()
    employment_profession_keys = [
        col for col in df_pm.columns if col.startswith("employment_")
    ]
    pm_dict = {}
    for _, row in df_pm.iterrows():
        if row["building"] not in building_cost_dict:
            continue  # Skip if building is not in building_cost_dict
        pm_dict[row["production_method"]] = ProductionUnit(
            era=tech_era_dict.get(row["unlocking_technologies"], 0),
            employment=row["employment"],
            production={
                good: row[f"goods_{good}"]
                for good in goods_dict.keys()
                if f"goods_{good}" in row
            },
            employment_by_profession={
                col[len("employment_") :]: row[col]
                for col in employment_profession_keys
            },
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
            for pm in combo:
                building += pm_dict[pm]
            row_dict = {
                "building": building_key,
                "production_method": "+".join(combo),
            }
            row_dict["building_group"] = building_group_dict[building_key]
            row_dict["era"] = building["era"]
            row_dict["employment"] = building["employment"]
            row_dict["construction_cost"] = building_cost_dict[building_key]
            row_dict["profit_nominal"] = building.profit_nominal(goods_dict)
            for key, amount in building.items():
                if key in ("era", "employment"):
                    continue
                if key.startswith("employment_"):
                    row_dict[key] = amount
                else:
                    row_dict[f"goods_{key}"] = amount
            possible_buildings.append(row_dict)

    result = pd.DataFrame(possible_buildings)
    return result
