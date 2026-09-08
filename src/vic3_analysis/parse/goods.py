"""
Parser for Victoria 3 tradeable-goods definitions.

Reads all ``.txt`` files under ``common/goods`` and returns their data as a
``pandas.DataFrame``.
"""

from pathlib import Path
from typing import Any

import pandas as pd

from vic3_analysis import get_vic3_directory, parse_merge


def goods(game_dir: str | Path | None = None) -> pd.DataFrame:
    """Parse Victoria 3 goods definitions and return them as a DataFrame.

    Args:
        game_dir: Path to the Victoria 3 ``game`` directory.  If ``None`` the
            directory is located automatically via
            `get_vic3_directory`.

    Returns:
        A ``DataFrame`` with one row per tradeable good, where the ``"key"``
        column holds the good's identifier and remaining columns represent its
        attributes (e.g. ``"cost"``).

    Raises:
        ValueError: If any entry in the goods tree is not a ``dict``.
    """
    if game_dir is None:
        game_dir = get_vic3_directory()

    parse_dir = Path(game_dir) / "common" / "goods"
    parse_tree = parse_merge(parse_dir)
    results: list[dict[str, Any]] = []
    for key, value in parse_tree.to_python().items():
        if not isinstance(value, dict):
            raise TypeError(f"Expected dict for {key}, got {type(value)}")
        results.append(
            {
                "key": key,
                **value,
            }
        )
    return pd.DataFrame(results)
