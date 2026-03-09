from vic3_analysis import get_vic3_directory
import os
import re
import pandas as pd
from pyradox import parse_file

GAME_FILE_PATH = os.path.join(get_vic3_directory(), "common", "buy_packages", "00_buy_packages.txt")


def _wealth_number(key: str):
    match = re.fullmatch(r"wealth_(\d+)", key)
    return int(match.group(1)) if match else None


def _parse_rows(tree):
    rows = []
    popneed_columns = []
    popneed_seen = set()

    for wealth_key, wealth_tree in tree.items():
        if not isinstance(wealth_key, str):
            continue

        wealth_number = _wealth_number(wealth_key)
        if wealth_number is None:
            continue

        political_strength = wealth_tree.find("political_strength")
        goods = wealth_tree.find("goods")

        row = {
            "wealth": wealth_number,
            "political_strength": political_strength,
        }

        for key, value in goods.items():
            if isinstance(key, str) and key.startswith("popneed_"):
                row[key] = value
                if key not in popneed_seen:
                    popneed_seen.add(key)
                    popneed_columns.append(key)

        rows.append(row)

    rows.sort(key=lambda row: row["wealth"])
    return rows, popneed_columns


def buy_packages(file_path: str | None = None) -> pd.DataFrame:
    if file_path is None:
        file_path = GAME_FILE_PATH

    if not os.path.isfile(file_path):
        raise FileNotFoundError(
            f"Could not find the file at {file_path}. Please check the path and try again."
        )

    tree = parse_file(file_path, game="HoI4", path_relative_to_game=False)
    rows, popneed_columns = _parse_rows(tree)

    fieldnames = ["wealth", "political_strength", *popneed_columns]
    normalized_rows = []
    for row in rows:
        normalized_row = {
            "wealth": row["wealth"],
            "political_strength": row["political_strength"],
        }
        for column in popneed_columns:
            normalized_row[column] = row.get(column, 0)
        normalized_rows.append(normalized_row)

    return pd.DataFrame(normalized_rows, columns=fieldnames)
