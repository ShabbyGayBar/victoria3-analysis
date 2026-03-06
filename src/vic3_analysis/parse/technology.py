from vic3_analysis import VIC3_DIR, parse_merge
import os
import re
import pandas as pd
from pyradox import Tree

skip_keys = [
    "modifier",
    "ai_weight",
    "unlocking_technologies",
    "on_researched",
]


def technology(game_dir: str | None = None) -> pd.DataFrame:
    if game_dir is None:
        game_dir = VIC3_DIR

    parse_dir = os.path.join(game_dir, "common", "technology", "technologies")
    parse_tree = parse_merge(parse_dir)
    result = []
    for tech_key, subtree in parse_tree.items():
        tech_item = {"tech_key": tech_key}
        for key, value in subtree.items():
            if key in skip_keys:
                continue
            if isinstance(value, Tree):
                raise ValueError(f"Expected non-tree entry for {key}, got Tree")
            if key == "era":
                # Extract era number from string like "era_1"
                match = re.match(r"era_(\d+)", value)
                if match:
                    tech_item[key] = int(match.group(1))
                else:
                    raise ValueError(
                        f"Could not extract era number from string: {value}"
                    )
            else:
                tech_item[key] = value
        result.append(tech_item)

    return pd.DataFrame(result)
