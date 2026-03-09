"""
Parser for Victoria 3 technology definitions.

Reads all ``.txt`` files under ``common/technology/technologies`` and returns
each technology's key attributes (including its numeric era) as a
``pandas.DataFrame``.
"""
from vic3_analysis import get_vic3_directory, parse_merge
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
        ``"tech_key"`` column and an ``"era"`` column (integer), plus any
        additional scalar attributes defined in the game files.

    Raises:
        ValueError: If a technology entry contains a nested ``Tree`` value for
            an unexpected key, or if the ``"era"`` value cannot be parsed.
    """
    if game_dir is None:
        game_dir = get_vic3_directory()

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
