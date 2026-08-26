"""
Parser for Victoria 3 technology definitions.

Reads all ``.txt`` files under ``common/technology/technologies`` and returns
each technology's key attributes (including its numeric era) as a
``pandas.DataFrame``.
"""

from pathlib import Path
from typing import Any

import re

import pandas as pd
from pyradox import Tree

from vic3_analysis import get_vic3_directory, parse_merge


def technology(game_dir: str | Path | None = None) -> pd.DataFrame:
    """Parse Victoria 3 technology definitions into a DataFrame.

    Reads all ``.txt`` files from ``common/technology/technologies``, skipping
    keys that are not useful for analysis (``modifier``, ``ai_weight``,
    ``unlocking_technologies``, ``on_researched``), and converts ``era_N``
    strings to their integer era numbers.

    Args:
        game_dir: Path to the Victoria 3 ``game`` directory.  If ``None`` the
            directory is located automatically via
            :func:`~vic3_analysis.utils.get_vic3_directory`.

    Returns:
        A ``DataFrame`` with one row per technology.  Always contains a
        ``"key"`` column and an ``"era"`` column (integer), plus any
        additional scalar attributes defined in the game files.

    Raises:
        ValueError: If a technology entry contains a nested ``Tree`` value for
            an unexpected key, or if the ``"era"`` value cannot be parsed.
    """
    if game_dir is None:
        game_dir = get_vic3_directory()

    parse_dir = Path(game_dir) / "common" / "technology" / "technologies"
    parse_tree = parse_merge(parse_dir)
    results: list[dict[str, Any]] = []
    for tech_key, subtree in parse_tree.items():
        tech_item: dict[str, Any] = {"key": tech_key}
        for key, value in subtree.items():
            if isinstance(value, list):
                value = "+".join(str(v) for v in value)
            elif isinstance(value, (dict, Tree)):
                continue
            elif key == "era":
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
        results.append(tech_item)

    return pd.DataFrame(results)
