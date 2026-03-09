"""
Parser for Victoria 3 production-method-group definitions.

Reads all ``.txt`` files under ``common/production_method_groups`` and returns
a mapping of group keys to their ordered list of production-method keys.
"""
from vic3_analysis import get_vic3_directory, parse_merge
import os
from pyradox import Tree


def production_method_groups(game_dir: str | None = None) -> dict[str, list[str]]:
    """Parse Victoria 3 production-method-group data into a dict.

    Args:
        game_dir: Path to the Victoria 3 ``game`` directory.  If ``None`` the
            directory is located automatically via
            :func:`~vic3_analysis.utils.get_vic3_directory`.

    Returns:
        A dict mapping each production-method-group key to its ordered list of
        production-method keys.
    """
    if game_dir is None:
        game_dir = get_vic3_directory()

    parse_dir = os.path.join(game_dir, "common", "production_method_groups")
    parse_tree = parse_merge(parse_dir)
    result = {}
    for key, subtree in parse_tree.items():
        if not isinstance(subtree, Tree):
            continue  # Skip non-tree entries
        production_methods = subtree.to_python().get("production_methods")
        if isinstance(production_methods, list):
            result[key] = production_methods
        else:
            result[key] = [production_methods]

    return result
