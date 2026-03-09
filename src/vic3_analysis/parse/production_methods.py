"""
Parser for Victoria 3 production-method definitions.

Reads all ``.txt`` files under ``common/production_methods``, combines them
with building and goods data, and exposes per-production-method employment and
goods-flow values as a flat ``pandas.DataFrame``.
"""
from vic3_analysis import (
    get_vic3_directory,
    parse_merge,
    BuildingsParser,
    goods,
    production_method_groups,
)
import os
import re
import pandas as pd
from pyradox import Tree
from typing import Any


def _parse_pm(
    goods_dict: dict[str, Any], game_dir: str | None = None
) -> dict[str, Any]:
    """Parse raw production-method data from the game files.

    Reads all ``.txt`` files under ``common/production_methods`` and extracts
    per-method goods flows (positive for output, negative for input) and
    employment.  Methods that do not define ``workforce_scaled`` building
    modifiers are skipped.

    Args:
        goods_dict: Mapping of good keys to their base costs, used to identify
            which modifier strings correspond to known goods.
        game_dir: Path to the Victoria 3 ``game`` directory.  If ``None`` the
            directory is located automatically via
            :func:`~vic3_analysis.utils.get_vic3_directory`.

    Returns:
        A dict mapping each production-method key to another dict that contains
        numeric values for each good key (positive = output, negative = input),
        an ``"employment"`` value, and optionally an
        ``"unlocking_technologies"`` string.

    Raises:
        ValueError: If a goods modifier string cannot be classified as either
            an input or an output, or if the associated good key cannot be
            identified.
    """
    if game_dir is None:
        game_dir = get_vic3_directory()

    parse_dir = os.path.join(game_dir, "common", "production_methods")
    parse_tree = parse_merge(parse_dir)
    result = {}
    for key, subtree in parse_tree.items():
        if not isinstance(subtree, Tree):
            continue  # Skip non-tree entries
        building_modifiers = subtree.to_python().get("building_modifiers")
        if not isinstance(building_modifiers, dict):
            continue  # Skip if building_modifiers is not a dict
        if "workforce_scaled" not in building_modifiers.keys():
            continue  # Skip if workforce_scaled is not a key in building_modifiers
        result[key] = {}
        for goods_str, value in building_modifiers["workforce_scaled"].items():
            if not goods_str.startswith("goods_"):
                continue
            # Determine goods type
            for goods_key in goods_dict.keys():
                if re.search(goods_key, goods_str):
                    if goods_str.startswith("goods_output_"):
                        result[key][goods_key] = value
                        break
                    elif goods_str.startswith("goods_input_"):
                        result[key][goods_key] = -value
                        break
                    else:
                        raise ValueError(
                            f"Could not determine if goods is input or output from string: {goods_str}"
                        )
            else:
                raise ValueError(
                    f"Could not determine goods type from string: {goods_str}"
                )
        result[key]["employment"] = 0
        if "level_scaled" not in building_modifiers.keys():
            continue  # Skip if level_scaled is not a key in building_modifiers
        for level_str, value in building_modifiers["level_scaled"].items():
            if level_str.startswith("building_employment_"):
                result[key]["employment"] += value
        if "unlocking_technologies" in subtree.keys():
            result[key]["unlocking_technologies"] = str(
                subtree["unlocking_technologies"]
            )
    return result


def _to_dataframe(
    buildings_pmg_dict: dict[str, list[str]],
    pmg_dict: dict[str, list[str]],
    pm_dict: dict[str, Any],
    goods_dict: dict[str, Any],
    buildings_tech_dict: dict = {},
) -> pd.DataFrame:
    """Assemble a flat DataFrame from pre-parsed building/PM/goods mappings.

    Iterates over every building → production-method-group → production-method
    combination and creates one row per combination, filling in employment,
    goods flows, and unlocking-technology information.

    Args:
        buildings_pmg_dict: Mapping of building keys to their ordered lists of
            production-method-group keys.
        pmg_dict: Mapping of production-method-group keys to their ordered
            lists of production-method keys.
        pm_dict: Mapping of production-method keys to their stats dicts (as
            returned by :func:`_parse_pm`).
        goods_dict: Mapping of good keys to their base costs.
        buildings_tech_dict: Optional mapping of building keys to their
            unlocking-technology strings.  Defaults to an empty dict.

    Returns:
        A ``DataFrame`` with columns ``"building"``,
        ``"production_method_group"``, ``"production_method"``,
        ``"unlocking_technologies"``, ``"employment"``, and one column per
        good key.  Missing numeric values are filled with ``0``.

    Raises:
        ValueError: If a production-method-group referenced by a building is
            not found in *pmg_dict*.
    """
    data = []
    for building, pmg_list in buildings_pmg_dict.items():
        for pmg in pmg_list:
            if pmg not in pmg_dict:
                raise ValueError(
                    f"Production method group {pmg} not found for building {building}"
                )
            for pm in pmg_dict[pmg]:
                if pm not in pm_dict:
                    goods_output = {}
                    employment = 0
                    tech = str(buildings_tech_dict.get(building, ""))
                else:
                    goods_output = {}
                    for goods_key in goods_dict.keys():
                        goods_output[goods_key] = pm_dict[pm].get(goods_key, 0)
                    employment = pm_dict[pm]["employment"]
                    if "unlocking_technologies" in pm_dict[pm].keys():
                        tech = str(pm_dict[pm]["unlocking_technologies"])
                    elif building in buildings_tech_dict:
                        tech = str(buildings_tech_dict[building])
                    else:
                        tech = ""
                data.append(
                    {
                        "building": building,
                        "production_method_group": pmg,
                        "production_method": pm,
                        "unlocking_technologies": tech,
                        "employment": employment,
                        **goods_output,
                    }
                )
    result = pd.DataFrame(data)
    result["unlocking_technologies"] = result["unlocking_technologies"].fillna("None")
    result["unlocking_technologies"] = result["unlocking_technologies"].replace("", "None")
    result = result.fillna(0)
    return result


def production_method(game_dir: str | None = None) -> pd.DataFrame:
    """Parse all Victoria 3 production-method data into a flat DataFrame.

    Combines buildings, production-method-groups, production-methods, and
    goods data from the game files into a single table.

    Args:
        game_dir: Path to the Victoria 3 ``game`` directory.  If ``None`` the
            directory is located automatically via
            :func:`~vic3_analysis.utils.get_vic3_directory`.

    Returns:
        A ``DataFrame`` with one row per (building, production-method-group,
        production-method) combination, containing employment numbers, goods
        flows, and unlocking-technology information.
    """
    if game_dir is None:
        game_dir = get_vic3_directory()

    df_goods = goods(game_dir)
    goods_dict = dict(zip(df_goods["key"], df_goods["cost"]))

    buildings_tree = BuildingsParser(game_dir)
    buildings_pmg_dict = buildings_tree.production_method_groups()
    # Get building technology information
    buildings_tech_dict = {}
    for building_key, building_values in buildings_tree.items():
        if "unlocking_technologies" in building_values.keys():
            buildings_tech_dict[building_key] = str(
                building_values["unlocking_technologies"]
            )
        else:
            buildings_tech_dict[building_key] = "buildings_pmg_dict"

    pmg_dict = production_method_groups(game_dir)

    pm_dict = _parse_pm(goods_dict, game_dir)

    return _to_dataframe(
        buildings_pmg_dict, pmg_dict, pm_dict, goods_dict, buildings_tech_dict
    )
