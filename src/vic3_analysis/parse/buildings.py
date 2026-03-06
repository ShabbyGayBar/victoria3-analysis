from vic3_analysis import VIC3_DIR, parse_merge
import os
import pandas as pd
from pyradox import Tree


class BuildingsParser(Tree):
    def __init__(self, game_dir: str | None = None):
        super().__init__()
        if game_dir is None:
            game_dir = VIC3_DIR

        parse_dir = os.path.join(game_dir, "common", "buildings")
        parse_tree = parse_merge(parse_dir)
        self.update(parse_tree.to_python())

    def to_dataframe(self) -> pd.DataFrame:
        results = []
        for building_key, building_values in self.items():
            building = {"building": building_key}
            for attribute_key, attribute_value in building_values.items():
                if isinstance(attribute_value, (list, dict, Tree)):
                    continue
                building[attribute_key] = attribute_value
            results.append(building)
        return pd.DataFrame(results)

    def production_method_groups(self) -> dict[str, list[str]]:
        result = {}
        for building_key, building_values in self.items():
            if isinstance(building_values, Tree):
                pmg = building_values.to_python().get("production_method_groups")
            elif isinstance(building_values, dict):
                pmg = building_values.get("production_method_groups")
            else:
                continue  # Skip non-dict entries
            if isinstance(pmg, list):
                result[building_key] = pmg
            else:
                result[building_key] = [pmg]
        return result
