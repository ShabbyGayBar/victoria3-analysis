"""
Parser for Victoria 3 building definitions.

Reads building data from the game's ``common/buildings`` directory and exposes
it as a ``pyradox.Tree`` subclass with helper methods for DataFrame conversion
and production-method-group look-ups.
"""

from vic3_analysis import get_vic3_directory, parse_merge
from pathlib import Path
import warnings
import pandas as pd
from pyradox import Tree
from typing import Any, cast


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

    cost_modifiers: dict[str, int]

    def __init__(self, game_dir: str | Path | None = None):
        """Initialise and populate the buildings tree.

        Args:
            game_dir: Path to the Victoria 3 ``game`` directory. If ``None``
                the directory is located automatically via
                :func:`~vic3_analysis.utils.get_vic3_directory`.
        """
        super().__init__()
        self._python_cache: dict[str, dict[str, Any]] = {}
        if game_dir is None:
            game_dir = get_vic3_directory()

        parse_dir = Path(game_dir) / "common" / "buildings"
        parse_tree = parse_merge(parse_dir)
        self.update(parse_tree)

        self._resolve_construction_costs(game_dir)

    def _resolve_construction_costs(self, game_dir: str | Path) -> None:
        """Load construction-cost script values and resolve building costs.

        Reads ``common/script_values`` to build a mapping of
        ``construction_cost_*`` names to their integer values, then resolves
        each building's ``required_construction`` reference into a numeric
        ``required_construction_points`` attribute.

        Args:
            game_dir: Path to the Victoria 3 ``game`` directory.
        """
        parse_dir = Path(game_dir) / "common" / "script_values"
        parse_tree = parse_merge(parse_dir)
        self.cost_modifiers = {}
        for key, value in parse_tree.to_python().items():
            if key.startswith("construction_cost_"):
                self.cost_modifiers[key] = int(value)

        for building_key, building_values in self.items():
            if "required_construction" not in building_values:
                continue
            cost_modifier = cast(str, building_values["required_construction"])
            if cost_modifier not in self.cost_modifiers:
                warnings.warn(
                    f"Building {building_key!r} references unknown construction "
                    f"cost {cost_modifier!r}; skipping required_construction_points."
                )
                continue
            building_values.append(
                "required_construction_points", self.cost_modifiers[cost_modifier]
            )

    def to_dataframe(self) -> pd.DataFrame:
        """Convert the buildings tree to a flat ``pandas.DataFrame``.

        Scalar attributes of each building are preserved as columns; nested
        ``Tree`` and ``dict`` values are omitted, and ``list`` values are
        concatenated into a ``+``-joined string.

        Returns:
            A ``DataFrame`` with one row per building and one column per scalar
            attribute.
        """
        results: list[dict[str, Any]] = []
        for building_key, building_values in self.items():
            py: dict[str, Any] = self._building_to_python(building_key, building_values)
            building: dict[str, Any] = {"building": building_key}
            for attribute_key, attribute_value in py.items():
                if isinstance(attribute_value, list):
                    building[attribute_key] = "+".join(str(v) for v in attribute_value)
                elif isinstance(attribute_value, (dict, Tree)):
                    continue  # Skip nested containers
                else:
                    building[attribute_key] = attribute_value
            results.append(building)
        return pd.DataFrame(results)

    def _building_to_python(
        self, building_key: str, building_values: Any
    ) -> dict[str, Any]:
        """Return a plain dict view of a building entry, caching the result.

        ``pyradox.Tree`` values are converted via ``to_python()`` once and
        memoised per building key; subsequent look-ups reuse the cached dict.
        Plain ``dict`` values are returned as-is.  Non-container entries yield
        an empty dict.
        """
        if isinstance(building_values, Tree):
            cached = self._python_cache.get(building_key)
            if cached is None:
                cached = building_values.to_python()
                self._python_cache[building_key] = cached
            return cached
        if isinstance(building_values, dict):
            return building_values
        return {}

    def production_method_groups(self) -> dict[str, list[str]]:
        """Return a mapping of building keys to their production-method-group lists.

        Returns:
            A dict where each key is a building identifier and each value is a
            list of production-method-group keys associated with that building.
            Buildings without ``production_method_groups`` are omitted.
        """
        result: dict[str, list[str]] = {}
        for building_key, building_values in self.items():
            py: dict[str, Any] = self._building_to_python(building_key, building_values)
            pmg: list[str] | str | None = py.get("production_method_groups")
            if pmg is None:
                continue
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
        result: dict[str, list[str]] = {}
        for building_key, building_values in self.items():
            py: dict[str, Any] = self._building_to_python(building_key, building_values)
            group: str | None = py.get("building_group")
            if group is not None:
                if group not in result:
                    result[group] = []
                result[group].append(building_key)
        return result
