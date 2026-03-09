"""
Parser for Victoria 3 tradeable-goods definitions.

Reads all ``.txt`` files under ``common/goods`` and returns their data as a
``pandas.DataFrame``.
"""
from vic3_analysis import get_vic3_directory, parse_merge
import os
import pandas as pd
from pyradox import Tree


def goods(file_dir: str | None = None) -> pd.DataFrame:
    """Parse Victoria 3 goods definitions and return them as a DataFrame.

    Args:
        file_dir: Path to the Victoria 3 ``game`` directory.  If ``None`` the
            directory is located automatically via
            :func:`~vic3_analysis.utils.get_vic3_directory`.

    Returns:
        A ``DataFrame`` with one row per tradeable good, where the ``"key"``
        column holds the good's identifier and remaining columns represent its
        attributes (e.g. ``"cost"``).

    Raises:
        ValueError: If any entry in the goods tree is not a ``dict``.
    """
    if file_dir is None:
        file_dir = get_vic3_directory()

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
