"""
Parser for Victoria 3 pop-type definitions.

Reads pop-type data from the game's ``common/pop_types`` directory and exposes
it as a ``pyradox.Tree`` subclass with helper methods for DataFrame conversion
and boolean-flag look-ups.
"""

from vic3_analysis import get_vic3_directory, parse_merge
from pathlib import Path
import pandas as pd
from pyradox import Tree
from typing import Any


class PopTypesParser(Tree):
    """A ``pyradox.Tree`` populated with Victoria 3 pop-type definitions.

    On construction the parser reads all pop-type ``.txt`` files from the
    game's ``common/pop_types`` directory and stores the parsed entries.
    """

    def __init__(self, game_dir: str | Path | None = None):
        """Initialise and populate the pop-types tree.

        Args:
            game_dir: Path to the Victoria 3 ``game`` directory. If ``None``
                the directory is located automatically via
                :func:`~vic3_analysis.utils.get_vic3_directory`.
        """
        super().__init__()
        self._python_cache: dict[str, dict[str, Any]] = {}
        if game_dir is None:
            game_dir = get_vic3_directory()

        parse_dir = Path(game_dir) / "common" / "pop_types"
        parse_tree = parse_merge(parse_dir)
        self.update(parse_tree)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert the pop-types tree to a flat ``pandas.DataFrame``.

        Scalar attributes of each pop type are preserved as columns; nested
        ``Tree`` and ``dict`` values are omitted, and ``list`` values are
        concatenated into a ``+``-joined string.

        Returns:
            A ``DataFrame`` with one row per pop type and one column per scalar
            attribute.
        """
        results: list[dict[str, Any]] = []
        for pop_type_key, pop_type_values in self.items():
            py: dict[str, Any] = self._pop_type_to_python(pop_type_key, pop_type_values)
            pop_type: dict[str, Any] = {"pop_type": pop_type_key}
            for attribute_key, attribute_value in py.items():
                if isinstance(attribute_value, list):
                    pop_type[attribute_key] = "+".join(str(v) for v in attribute_value)
                elif isinstance(attribute_value, (dict, Tree)):
                    continue  # Skip nested containers
                else:
                    pop_type[attribute_key] = attribute_value
            results.append(pop_type)
        return pd.DataFrame(results)

    def _pop_type_to_python(
        self, pop_type_key: str, pop_type_values: Any
    ) -> dict[str, Any]:
        """Return a plain dict view of a pop-type entry, caching the result.

        ``pyradox.Tree`` values are converted via ``to_python()`` once and
        memoised per pop-type key; subsequent look-ups reuse the cached dict.
        Plain ``dict`` values are returned as-is.  Non-container entries yield
        an empty dict.
        """
        if isinstance(pop_type_values, Tree):
            cached = self._python_cache.get(pop_type_key)
            if cached is None:
                cached = pop_type_values.to_python()
                self._python_cache[pop_type_key] = cached
            return cached
        if isinstance(pop_type_values, dict):
            return pop_type_values
        return {}

    def flags(self) -> dict[str, list[str]]:
        """Return a mapping of boolean-flag names to the pop types that set them.

        Scans each pop type for boolean attributes whose value is ``True`` and
        groups pop-type keys by flag name (e.g. ``"is_slave"``,
        ``"military"``, ``"unemployment"``).

        Returns:
            A dict where each key is a boolean attribute name and each value is
            a list of pop-type identifiers for which that flag is set to
            ``True``.
        """
        result: dict[str, list[str]] = {}
        for pop_type_key, pop_type_values in self.items():
            py: dict[str, Any] = self._pop_type_to_python(pop_type_key, pop_type_values)
            for attribute_key, attribute_value in py.items():
                if attribute_value is True:
                    result.setdefault(attribute_key, []).append(pop_type_key)
        return result
