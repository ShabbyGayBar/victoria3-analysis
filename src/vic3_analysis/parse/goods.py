from vic3_analysis import VIC3_DIR, parse_merge
import os
import pandas as pd
from pyradox import Tree


def goods(file_dir: str | None = None) -> pd.DataFrame:
    if file_dir is None:
        file_dir = VIC3_DIR

    parse_dir = os.path.join(file_dir, "common", "goods")
    parse_tree = parse_merge(parse_dir)
    result = []
    for key, value in parse_tree.to_python().items():
        if not isinstance(value, dict):
            raise ValueError(f"Expected dict for {key}, got {type(value)}")
        result.append(
            {
                "key": key,
                **value,
            }
        )
    return pd.DataFrame(result)
