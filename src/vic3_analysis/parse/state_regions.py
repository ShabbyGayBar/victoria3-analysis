"""
Parser for Victoria 3 state region definitions.

Reads state region data from the game's ``map_data/state_regions`` directory and exposes
it as a ``pyradox.Tree`` subclass with helper methods for DataFrame conversion
and state region look-ups.
"""
from vic3_analysis import get_vic3_directory, parse_merge
import os
import pandas as pd
from pyradox import Tree

_skip_keys = [
    "provinces",
    "impassable",
    "prime_land",
    "traits",
    "arable_resources",
    "resource",
    "capped_resources",
]

class StateRegionsParser(Tree):
    """A ``pyradox.Tree`` subclass for parsing Victoria 3 state region definitions.

    Reads all ``.txt`` files from the game's ``map_data/state_regions`` directory
    and stores the parsed data in a tree structure that mirrors the original
    file hierarchy.  Provides helper methods for converting to a flat
    ``pandas.DataFrame`` and for looking up state region attributes & resources.
    """

    def __init__(self, game_dir: str | None = None):
        """Initialise and populate the state regions tree.

        Args:
            game_dir: Path to the Victoria 3 ``game`` directory. If ``None``
                the directory is located automatically via
                :func:`~vic3_analysis.utils.get_vic3_directory`.
        """
        super().__init__()
        if game_dir is None:
            game_dir = get_vic3_directory()

        parse_dir = os.path.join(game_dir, "map_data", "state_regions")
        parse_tree = parse_merge(parse_dir)
        self.update(parse_tree)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert the state regions tree to a flat ``pandas.DataFrame``.

        Scalar attributes of each state region are preserved as columns; nested
        ``Tree``, ``list``, and ``dict`` values are omitted.

        Returns:
            A ``DataFrame`` with one row per state region and one column per scalar
            attribute.
        """
        results = []
        for state_region_key, state_region_values in self.items():
            state_region = {"key": state_region_key}
            state_region["province_count"] = len(self.provinces_of(state_region_key))
            for attribute_key, attribute_value in state_region_values.items():
                if attribute_key == "capped_resources":
                    for resource_key, resource_value in attribute_value.items():
                        state_region[f"resource_{resource_key}"] = resource_value
                elif attribute_key == "resource":
                    if not isinstance(attribute_value, Tree):
                        raise ValueError(
                            f"Expected 'resource' attribute to be a Tree, got {type(attribute_value)}"
                        )
                    resource_key = attribute_value["type"]
                    undiscovered_amount = int(attribute_value.find("undiscovered_amount", 0)) # pyright: ignore[reportArgumentType]
                    discovered_amount = int(attribute_value.find("discovered_amount", 0)) # pyright: ignore[reportArgumentType]
                    state_region[f"resource_{resource_key}"] = undiscovered_amount + discovered_amount
                    state_region[f"undiscovered_amount_resource_{resource_key}"] = undiscovered_amount
                    state_region[f"discovered_amount_resource_{resource_key}"] = discovered_amount
                if attribute_key in _skip_keys or isinstance(attribute_value, (list, dict, Tree)):
                    continue
                state_region[attribute_key] = attribute_value
            results.append(state_region)
        results = pd.DataFrame(results)
        # For every column whose name starts with "resource_" or "undiscovered_amount_resource_" or "discovered_amount_resource_",
        # convert the column to numeric, coercing errors to NaN, and then fill NaN values with 0
        for column in results.columns:
            if column.startswith("resource_") or column.startswith("undiscovered_amount_resource_") or column.startswith("discovered_amount_resource_"):
                results[column] = pd.to_numeric(results[column], errors="coerce").fillna(0).astype(int)
        return results

    def provinces_of(self, state_region_key: str | None = None) -> list[str]:
        """Return a list of all province keys that belong to any state region."""
        provinces = []
        state_region_values = self[state_region_key]
        if not isinstance(state_region_values, Tree):
            raise ValueError(
                f"State region '{state_region_key}' does not exist or is not a valid Tree."
            )
        for attribute_key, attribute_value in state_region_values.items():
            if attribute_key == "provinces":
                provinces.append(attribute_value)
        return provinces

    def traits_of(self, state_region_key: str | None = None) -> list[str]:
        """Return a list of all trait keys that belong to any state region."""
        traits = []
        state_region_values = self[state_region_key]
        if not isinstance(state_region_values, Tree):
            raise ValueError(
                f"State region '{state_region_key}' does not exist or is not a valid Tree."
            )
        for attribute_key, attribute_value in state_region_values.items():
            if attribute_key == "traits":
                traits.append(attribute_value)
        return traits

    def arable_resources_of(self, state_region_key: str | None = None) -> list[str]:
        """Return a list of all arable resource keys that belong to any state region."""
        arable_resources = []
        state_region_values = self[state_region_key]
        if not isinstance(state_region_values, Tree):
            raise ValueError(
                f"State region '{state_region_key}' does not exist or is not a valid Tree."
            )
        for attribute_key, attribute_value in state_region_values.items():
            if attribute_key == "arable_resources":
                arable_resources.append(attribute_value)
        return arable_resources
