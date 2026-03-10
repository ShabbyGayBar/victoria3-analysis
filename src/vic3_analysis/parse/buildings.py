"""
Parser for Victoria 3 building definitions.

Reads building data from the game's ``common/buildings`` directory and exposes
it as a ``pyradox.Tree`` subclass with helper methods for DataFrame conversion
and production-method-group look-ups.
"""
from vic3_analysis import get_vic3_directory, parse_merge
import os
import pandas as pd
from pyradox import Tree


class BuildingsParser(Tree):
    """A ``pyradox.Tree`` populated with Victoria 3 building definitions.

    On construction the parser reads all building ``.txt`` files from the game
    directory, resolves ``required_construction`` keys to their numeric point
    values using the game's ``script_values``, and stores the resolved value
    under the ``required_construction_points`` key for each building entry.

    Attributes:
        cost_modifiers: Mapping of construction-cost script-value names (e.g.
            ``"construction_cost_urban"``) to their integer values, extracted
            from ``common/script_values``.
    """

    def __init__(self, game_dir: str | None = None):
        """Initialise and populate the buildings tree.

        Args:
            game_dir: Path to the Victoria 3 ``game`` directory. If ``None``
                the directory is located automatically via
                :func:`~vic3_analysis.utils.get_vic3_directory`.
        """
        super().__init__()
        if game_dir is None:
            game_dir = get_vic3_directory()

        parse_dir = os.path.join(game_dir, "common", "buildings")
        parse_tree = parse_merge(parse_dir)
        self.update(parse_tree.to_python())

        parse_dir = os.path.join(game_dir, "common", "script_values")
        parse_tree = parse_merge(parse_dir)
        self.cost_modifiers = {}
        for key, value in parse_tree.to_python().items():
            if key.startswith("construction_cost_"):
                self.cost_modifiers[key] = int(value)

        for building_key, building_values in self.items():
            if "required_construction" not in building_values.keys():
                continue
            cost_modifier = building_values["required_construction"]
            building_values.append(
                "required_construction_points", self.cost_modifiers[cost_modifier]
            )

    def to_dataframe(self) -> pd.DataFrame:
        """Convert the buildings tree to a flat ``pandas.DataFrame``.

        Scalar attributes of each building are preserved as columns; nested
        ``Tree``, ``list``, and ``dict`` values are omitted.

        Returns:
            A ``DataFrame`` with one row per building and one column per scalar
            attribute.
        """
        results = []
        for building_key, building_values in self.items():
            building = {"building": building_key}
            for attribute_key, attribute_value in building_values.items():
                if isinstance(attribute_value, (list, dict, Tree)):
                    continue
                building[attribute_key] = attribute_value
            results.append(building)
        return pd.DataFrame(results)

    def production_method_groups(self) -> dict[str, list[str]]:
        """Return a mapping of building keys to their production-method-group lists.

        Returns:
            A dict where each key is a building identifier and each value is a
            list of production-method-group keys associated with that building.
        """
        result = {}
        for building_key, building_values in self.items():
            if isinstance(building_values, Tree):
                pmg = building_values.to_python().get("production_method_groups")
            elif isinstance(building_values, dict):
                pmg = building_values.get("production_method_groups")
            else:
                continue  # Skip non-dict entries
            if isinstance(pmg, list):
                result[building_key] = pmg
            else:
                result[building_key] = [pmg]
        return result

    def building_groups(self) -> dict[str, list[str]]:
        """Return a mapping of building group keys to their member building keys.

        Returns:
            A dict where each key is a building group identifier and each value
            is a list of building identifiers that belong to that group.
        """
        result = {}
        for building_key, building_values in self.items():
            if isinstance(building_values, Tree):
                group = building_values.to_python().get("building_group")
            elif isinstance(building_values, dict):
                group = building_values.get("building_group")
            else:
                continue  # Skip non-dict entries
            if group is not None:
                if group not in result:
                    result[group] = []
                result[group].append(building_key)
        return result
