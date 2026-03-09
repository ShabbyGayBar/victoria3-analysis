from vic3_analysis import get_vic3_directory, parse_merge
import os
from pyradox import Tree


def production_method_groups(game_dir: str | None = None) -> dict[str, list[str]]:
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
