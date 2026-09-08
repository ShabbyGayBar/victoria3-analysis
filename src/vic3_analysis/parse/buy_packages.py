"""
Parser for Victoria 3 pop buy-package definitions.

Reads all ``.txt`` files under ``common/buy_packages`` and exposes each wealth
level's political strength and good-consumption values as a
``pandas.DataFrame``.
"""

from pathlib import Path
from typing import Any

import re

import pandas as pd
from pyradox import Tree

from vic3_analysis import get_vic3_directory, parse_merge


def _wealth_number(key: str) -> int | None:
    """Extract the numeric wealth level from a ``wealth_N`` key string.

    Args:
        key: A string of the form ``"wealth_<number>"``.

    Returns:
        The integer wealth level, or ``None`` if *key* does not match the
        expected pattern.
    """
    match = re.fullmatch(r"wealth_(\d+)", key)
    return int(match.group(1)) if match else None


def _parse_rows(tree: Tree) -> tuple[list[dict[str, Any]], list[str]]:
    """Parse a buy-packages ``pyradox.Tree`` into row dicts and column names.

    Iterates over all ``wealth_N`` entries in *tree*, extracting political
    strength and per-good consumption values.

    Args:
        tree: A ``pyradox.Tree`` representing the parsed buy-packages file.

    Returns:
        A tuple of:
        - ``rows``: A list of dicts, one per wealth level, sorted by wealth
          number.  Each dict contains ``"wealth"``, ``"political_strength"``,
          and one key per ``popneed_*`` good consumed at that wealth level.
        - ``popneed_columns``: An ordered list of the ``popneed_*`` column
          names encountered while parsing, in first-seen order.
    """
    rows: list[dict[str, Any]] = []
    popneed_columns: list[str] = []
    popneed_seen: set[str] = set()

    for wealth_key, wealth_tree in tree.items():
        if not isinstance(wealth_key, str):
            continue

        wealth_number = _wealth_number(wealth_key)
        if wealth_number is None:
            continue

        political_strength = wealth_tree.find("political_strength")
        goods = wealth_tree.find("goods")
        if not isinstance(goods, Tree):
            raise ValueError(f"Expected Tree for goods, got {type(goods).__name__}")

        row: dict[str, Any] = {
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


def buy_packages(game_dir: str | Path | None = None) -> pd.DataFrame:
    """Parse Victoria 3 buy-packages files into a ``pandas.DataFrame``.

    Args:
        game_dir: Path to the Victoria 3 ``game`` directory.  If ``None`` the
            directory is located automatically via
            `get_vic3_directory`.

    Returns:
        A ``DataFrame`` with one row per wealth level and columns for
        ``"wealth"``, ``"political_strength"``, ``"total_popneeds"``, and one
        column per ``popneed_*`` good.  Missing consumption values are filled
        with ``0``.
    """
    if game_dir is None:
        game_dir = get_vic3_directory()

    parse_dir = Path(game_dir) / "common" / "buy_packages"
    tree = parse_merge(parse_dir)
    rows, popneed_columns = _parse_rows(tree)

    fieldnames = ["wealth", "political_strength", "total_popneeds", *popneed_columns]
    results: list[dict[str, Any]] = []
    for row in rows:
        normalized_row: dict[str, Any] = {
            "wealth": row["wealth"],
            "political_strength": row["political_strength"],
        }
        total_popneeds = 0
        for column in popneed_columns:
            value = row.get(column, 0)
            normalized_row[column] = value
            total_popneeds += value
        normalized_row["total_popneeds"] = total_popneeds
        results.append(normalized_row)

    return pd.DataFrame(results, columns=fieldnames)
