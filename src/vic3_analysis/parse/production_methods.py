from vic3_analysis import (
    VIC3_DIR,
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
    if game_dir is None:
        game_dir = VIC3_DIR

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
    return result


def _to_dataframe(
    buildings_dict: dict[str, list[str]],
    pmg_dict: dict[str, list[str]],
    pm_dict: dict[str, Any],
    goods_dict: dict[str, Any],
) -> pd.DataFrame:
    data = []
    for building, pmg_list in buildings_dict.items():
        for pmg in pmg_list:
            if pmg not in pmg_dict:
                raise ValueError(
                    f"Production method group {pmg} not found for building {building}"
                )
            for pm in pmg_dict[pmg]:
                if pm not in pm_dict:
                    goods_output = {}
                    for goods_key in goods_dict.keys():
                        goods_output[goods_key] = 0
                    employment = 0
                else:
                    goods_output = {}
                    for goods_key in goods_dict.keys():
                        if goods_key in pm_dict[pm]:
                            goods_output[goods_key] = pm_dict[pm][goods_key]
                        else:
                            goods_output[goods_key] = 0
                    employment = pm_dict[pm]["employment"]
                data.append(
                    {
                        "building": building,
                        "production_method_group": pmg,
                        "production_method": pm,
                        "employment": employment,
                        **goods_output,
                    }
                )
    return pd.DataFrame(data)


def production_method(game_dir: str | None = None) -> pd.DataFrame:
    if game_dir is None:
        game_dir = VIC3_DIR

    df_goods = goods(game_dir)
    goods_dict = dict(zip(df_goods["key"], df_goods["cost"]))

    buildings_dict = BuildingsParser(game_dir).production_method_groups()

    pmg_dict = production_method_groups(game_dir)

    pm_dict = _parse_pm(goods_dict, game_dir)

    return _to_dataframe(buildings_dict, pmg_dict, pm_dict, goods_dict)
