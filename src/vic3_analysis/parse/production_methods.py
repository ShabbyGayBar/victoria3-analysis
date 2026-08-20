"""
Parser for Victoria 3 production-method definitions.

Reads all ``.txt`` files under ``common/production_methods`` and exposes them
as a :class:`ProductionMethodParser` (a ``pyradox.Tree`` subclass) that
supports raw per-method iteration, per-profession employment look-ups, and
flat ``pandas.DataFrame`` conversion combining building and
production-method-group data with per-method attributes and appended
employment and goods-flow columns.
"""

from vic3_analysis import (
    get_vic3_directory,
    parse_merge,
    BuildingsParser,
    goods,
    production_method_groups,
)
from pathlib import Path
import re
import pandas as pd
from pyradox import Tree
from typing import Any, Iterator


class ProductionMethodParser(Tree):
    """A ``pyradox.Tree`` populated with Victoria 3 production-method definitions.

    On construction the parser reads all production-method ``.txt`` files from
    the game's ``common/production_methods`` directory.  Raw entries can be
    iterated via :meth:`items` (inherited from ``Tree``); per-method employment
    (total and broken down by profession) is available via :meth:`employment`;
    and a flat per-configuration table of production-method attributes plus
    appended employment and goods-flow columns is built by
    :meth:`to_dataframe`.
    """

    def __init__(self, game_dir: str | Path | None = None):
        """Initialise and populate the production-methods tree.

        Args:
            game_dir: Path to the Victoria 3 ``game`` directory. If ``None``
                the directory is located automatically via
                :func:`~vic3_analysis.utils.get_vic3_directory`.
        """
        super().__init__()
        self._python_cache: dict[str, dict[str, Any]] = {}
        if game_dir is None:
            game_dir = get_vic3_directory()
        self._game_dir = game_dir

        parse_dir = Path(game_dir) / "common" / "production_methods"
        parse_tree = parse_merge(parse_dir)
        self.update(parse_tree)

    def _pm_to_python(self, pm_key: str, pm_values: Any) -> dict[str, Any]:
        """Return a plain dict view of a production-method entry, caching it.

        ``pyradox.Tree`` values are converted via ``to_python()`` once and
        memoised per production-method key; subsequent look-ups reuse the
        cached dict.  Plain ``dict`` values are returned as-is.  Non-container
        entries yield an empty dict.
        """
        if isinstance(pm_values, Tree):
            cached = self._python_cache.get(pm_key)
            if cached is None:
                cached = pm_values.to_python()
                self._python_cache[pm_key] = cached
            return cached
        if isinstance(pm_values, dict):
            return pm_values
        return {}

    def _iter_building_modifiers(
        self,
    ) -> Iterator[tuple[str, dict[str, Any]]]:
        """Yield ``(pm_key, building_modifiers)`` for each method defining them."""
        for key, subtree in self.items():
            if not isinstance(subtree, Tree):
                continue  # Skip non-tree entries
            building_modifiers = self._pm_to_python(key, subtree).get(
                "building_modifiers"
            )
            if isinstance(building_modifiers, dict):
                yield key, building_modifiers

    def employment(self) -> dict[str, dict[str, Any]]:
        """Return per-method employment broken down by profession.

        Iterates every production method in the tree and, for each one that
        defines ``building_modifiers``, reads its ``level_scaled`` modifiers to
        compute the total employment and one ``employment_<profession>``
        value per profession (e.g. ``employment_laborers``).  Methods without
        ``level_scaled`` employment modifiers still appear with a zero total.

        Returns:
            A dict mapping each production-method key to a dict containing an
            ``"employment"`` value (total across all professions) and one
            ``"employment_<profession>"`` value per profession that the method
            employs.
        """
        result: dict[str, dict[str, Any]] = {}
        for key, building_modifiers in self._iter_building_modifiers():
            pm_entry: dict[str, Any] = {"employment": 0}
            level_scaled = building_modifiers.get("level_scaled")
            if isinstance(level_scaled, dict):
                for level_str, value in level_scaled.items():
                    if level_str.startswith("building_employment_"):
                        pm_entry["employment"] += value
                        match = re.match(r"building_employment_(.+)_add$", level_str)
                        if match:
                            pm_entry[f"employment_{match.group(1)}"] = value
            result[key] = pm_entry
        return result

    def _goods_io(self, goods_dict: dict[str, Any]) -> dict[str, dict[str, Any]]:
        """Return per-method net goods flows from ``workforce_scaled`` modifiers.

        Iterates every production method in the tree and, for each one that
        defines ``building_modifiers``, reads its ``workforce_scaled`` modifiers
        to compute the net flow of each good (positive for output, negative for
        input).  Methods without ``workforce_scaled`` still appear with an empty
        flows dict.

        Args:
            goods_dict: Mapping of good keys to their base costs, used to
                identify which modifier strings correspond to known goods.

        Returns:
            A dict mapping each production-method key to a dict that maps good
            keys to their signed net amounts (positive = output, negative =
            input).

        Raises:
            ValueError: If a goods modifier string cannot be classified as
                either an input or an output, or if the associated good key
                cannot be identified.
        """
        result: dict[str, dict[str, Any]] = {}
        for key, building_modifiers in self._iter_building_modifiers():
            result[key] = {}
            workforce_scaled = building_modifiers.get("workforce_scaled")
            if not isinstance(workforce_scaled, dict):
                continue
            for goods_str, value in workforce_scaled.items():
                match = re.match(r"goods_(output|input)_(.+)_add$", goods_str)
                if not match:
                    continue
                good = match.group(2)
                if good not in goods_dict:
                    raise ValueError(
                        f"Could not determine goods type from string: {goods_str}"
                    )
                result[key][good] = value if match.group(1) == "output" else -value
        return result

    def to_dataframe(self) -> pd.DataFrame:
        """Build a flat DataFrame of per-configuration production-method stats.

        Combines the parsed production methods with building and
        production-method-group data into one row per
        (building, production-method-group, production-method) combination.
        The production method's scalar attributes are preserved as columns,
        ``list`` values are concatenated into ``+``-joined strings, and nested
        ``dict``/``Tree`` values (such as ``building_modifiers``) are omitted.
        Total and per-profession employment and per-good net flows (positive =
        output, negative = input) are appended as columns at the end.  Goods
        columns are prefixed with ``goods_`` to distinguish them from
        attribute columns.

        Returns:
            A ``DataFrame`` with ``"building"``,
            ``"production_method_group"`` and ``"production_method"`` key
            columns, the production method's scalar/list attributes, and
            appended ``"employment"`` (total), ``"employment_<profession>"``
            and ``"goods_<good>"`` columns.  Employment and goods columns are
            zero-filled; scalar-attribute columns are left missing (``NaN``)
            when a method does not define them, matching
            :meth:`BuildingsParser.to_dataframe`.

        Raises:
            ValueError: If a goods modifier string cannot be classified as
                either an input or an output, if the associated good key
                cannot be identified, or if a production-method-group referenced
                by a building is not found.
        """
        game_dir = self._game_dir

        df_goods = goods(game_dir)
        goods_dict = dict(zip(df_goods["key"], df_goods["cost"]))

        buildings_tree = BuildingsParser(game_dir)
        buildings_pmg_dict = buildings_tree.production_method_groups()

        pmg_dict = production_method_groups(game_dir)

        employment_dict = self.employment()
        goods_flows = self._goods_io(goods_dict)

        # Collect every per-profession employment key (e.g. "employment_laborers")
        employment_profession_keys: set[str] = {
            k
            for pm_data in employment_dict.values()
            for k in pm_data
            if k.startswith("employment_") and k != "employment"
        }

        # Precompute per-method scalar/list attributes (skip dict/Tree), cached
        pm_attrs: dict[str, dict[str, Any]] = {}
        for pm_key, pm_values in self.items():
            py = self._pm_to_python(pm_key, pm_values)
            attrs: dict[str, Any] = {}
            for attribute_key, attribute_value in py.items():
                if isinstance(attribute_value, list):
                    attrs[attribute_key] = "+".join(str(v) for v in attribute_value)
                elif isinstance(attribute_value, (dict, Tree)):
                    continue  # Skip nested containers
                else:
                    attrs[attribute_key] = attribute_value
            pm_attrs[pm_key] = attrs

        data: list[dict[str, Any]] = []
        for building, pmg_list in buildings_pmg_dict.items():
            for pmg in pmg_list:
                if pmg not in pmg_dict:
                    raise ValueError(
                        f"Production method group {pmg} not found for building {building}"
                    )
                for pm in pmg_dict[pmg]:
                    emp = employment_dict.get(pm, {})
                    flows = goods_flows.get(pm, {})
                    row: dict[str, Any] = {
                        "building": building,
                        "production_method_group": pmg,
                        "production_method": pm,
                        **pm_attrs.get(pm, {}),
                        "employment": emp.get("employment", 0),
                        **{k: emp.get(k, 0) for k in employment_profession_keys},
                        **{f"goods_{gk}": flows.get(gk, 0) for gk in goods_dict.keys()},
                    }
                    data.append(row)

        return pd.DataFrame(data)
