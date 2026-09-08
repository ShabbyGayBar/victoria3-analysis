"""
Parser for Victoria 3 building-group definitions.

Reads building-group data from the game's ``common/building_groups`` directory
and exposes it as a `BuildingGroupParser` (a ``pyradox.Tree`` subclass)
with helper methods for flat ``pandas.DataFrame`` conversion and for resolving
attributes inherited along the ``parent_group`` chain.
"""

from pathlib import Path
from typing import Any
import warnings

import pandas as pd
from pyradox import Tree

from vic3_analysis import get_vic3_directory, parse_merge

#: Attributes that are inherited from the parent building group when unset on a
#: child. Each entry maps the attribute name to whether an explicit ``0`` value
#: should be treated as "unset" and thus also inherited.
_inherited_attrs: dict[str, bool] = {
    "land_usage": False,
    "cash_reserves_max": True,  # vanilla comment: inherits if "unspecified or set to 0"
    "economy_of_scale": False,
}


class BuildingGroupParser(Tree):
    """A ``pyradox.Tree`` populated with Victoria 3 building-group definitions.

    On construction the parser reads all building-group ``.txt`` files from the
    game's ``common/building_groups`` directory.  Raw entries can be iterated
    via `items` (inherited from ``Tree``); a flat per-group table is
    built by `to_dataframe`; and a per-group attribute dict with
    ``land_usage`` and ``cash_reserves_max`` inheritance resolved is returned
    by `resolved_attributes`.
    """

    def __init__(self, game_dir: str | Path | None = None):
        """Initialise and populate the building-groups tree.

        Args:
            game_dir: Path to the Victoria 3 ``game`` directory. If ``None``
                the directory is located automatically via
                `get_vic3_directory`.
        """
        super().__init__()
        self._python_cache: dict[str, dict[str, Any]] = {}
        if game_dir is None:
            game_dir = get_vic3_directory()

        parse_dir = Path(game_dir) / "common" / "building_groups"
        parse_tree = parse_merge(parse_dir)
        self.update(parse_tree)

    def _group_to_python(self, group_key: str, group_values: Any) -> dict[str, Any]:
        """Return a plain dict view of a building-group entry, caching it.

        ``pyradox.Tree`` values are converted via ``to_python()`` once and
        memoised per group key; subsequent look-ups reuse the cached dict.
        Plain ``dict`` values are returned as-is.  Non-container entries yield
        an empty dict.
        """
        if isinstance(group_values, Tree):
            cached = self._python_cache.get(group_key)
            if cached is None:
                cached = group_values.to_python()
                self._python_cache[group_key] = cached
            return cached
        if isinstance(group_values, dict):
            return group_values
        return {}

    def to_dataframe(self) -> pd.DataFrame:
        """Convert the building-groups tree to a flat ``pandas.DataFrame``.

        Each row is one building group; scalar attributes are preserved as
        columns, ``list`` values are concatenated into a ``+``-joined string,
        and nested ``Tree``/``dict`` values (such as ``should_auto_expand``
        trigger blocks) are omitted.  No parent-chain inheritance is applied
        here — use `resolved_attributes` for inherited values.

        Returns:
            A ``DataFrame`` with one row per building group (``"key"`` column)
            and one column per scalar attribute declared on that group.
        """
        results: list[dict[str, Any]] = []
        for group_key, group_values in self.items():
            py: dict[str, Any] = self._group_to_python(group_key, group_values)
            row: dict[str, Any] = {"key": group_key}
            for attribute_key, attribute_value in py.items():
                if isinstance(attribute_value, list):
                    row[attribute_key] = "+".join(str(v) for v in attribute_value)
                elif isinstance(attribute_value, (dict, Tree)):
                    continue  # Skip nested containers
                else:
                    row[attribute_key] = attribute_value
            results.append(row)
        return pd.DataFrame(results)

    def resolved_attributes(self) -> dict[str, dict[str, Any]]:
        """Return per-group attribute dicts with inherited attrs resolved.

        For each building group, a copy of its raw scalar attributes is
        returned with the following inherited attributes filled by walking the
        ``parent_group`` chain when they are unset on the group itself:

        - ``land_usage`` — inherited when missing.
        - ``cash_reserves_max`` — inherited when missing *or* explicitly ``0``
          (per the vanilla file comment: "If unspecified or set to 0, it will
          use the value from the parent group").
        - ``economy_of_scale`` — inherited when missing because the vanilla
          rule applies to buildings in a flagged group or any child group.

        Non-inherited attributes keep their raw, group-local values (including
        ``None``/missing, which are simply absent from the dict).  Cycle guards
        prevent infinite loops on malformed ``parent_group`` loops.

        Returns:
            A dict mapping each building-group key to a dict of its resolved
            scalar attributes.
        """
        raw: dict[str, dict[str, Any]] = {}
        for group_key, group_values in self.items():
            py = self._group_to_python(group_key, group_values)
            scalar: dict[str, Any] = {}
            for attribute_key, attribute_value in py.items():
                if isinstance(attribute_value, (list, dict, Tree)):
                    continue
                scalar[attribute_key] = attribute_value
            raw[group_key] = scalar

        resolved: dict[str, dict[str, Any]] = {}
        for group_key, attrs in raw.items():
            merged = dict(attrs)
            for attr, skip_zero in _inherited_attrs.items():
                current = merged.get(attr)
                if current is None or (skip_zero and current == 0):
                    inherited = _inherit_attr(group_key, raw, attr, skip_zero=skip_zero)
                    if inherited is not None:
                        merged[attr] = inherited
            resolved[group_key] = merged
        return resolved


def _inherit_attr(
    group_key: str,
    raw: dict[str, dict[str, Any]],
    attr: str,
    skip_zero: bool = False,
    _seen: set[str] | None = None,
) -> Any | None:
    """Walk the ``parent_group`` chain to resolve an inherited attribute.

    Args:
        group_key: The group to resolve *attr* for.
        raw: Mapping of group key → raw scalar attribute dict (as produced by
            `BuildingGroupParser.resolved_attributes` before resolution).
        attr: Attribute name to resolve.
        skip_zero: When ``True``, an explicit ``0`` on an ancestor is treated
            as "unset" and the walk continues further up the chain.
        _seen: Internal cycle-guard set of already-visited group keys.

    Returns:
        The first inherited value found, or ``None`` if the attribute is not
        set on any reachable ancestor.
    """
    if _seen is None:
        _seen = set()
    _seen.add(group_key)

    attrs = raw.get(group_key)
    if attrs is None:
        return None
    parent = attrs.get("parent_group")
    if not isinstance(parent, str) or parent not in raw:
        return None
    if parent in _seen:
        return None
    value = raw[parent].get(attr)
    if value is None or (skip_zero and value == 0):
        return _inherit_attr(parent, raw, attr, skip_zero=skip_zero, _seen=_seen)
    return value


def _join_group_attrs(
    building_rows: list[dict[str, Any]],
    group_attrs: dict[str, dict[str, Any]],
) -> None:
    """Join resolved building-group attributes onto building row dicts.

    For each building row that declares a ``building_group``, the group's
    resolved scalar attributes are merged into the row.  Attribute names that
    collide with an existing building-level column are prefixed with
    ``building_group_`` to avoid clobbering building data; non-colliding names
    are joined under their raw attribute name.  Nested ``dict``/``Tree`` group
    values are skipped and ``list`` values are ``+``-joined into strings.

    Args:
        building_rows: List of building row dicts (mutated in place).
        group_attrs: Mapping of group key → resolved attribute dict, as
            returned by `BuildingGroupParser.resolved_attributes`.
    """
    for row in building_rows:
        group_key = row.get("building_group")
        if not isinstance(group_key, str):
            continue
        attrs = group_attrs.get(group_key)
        if attrs is None:
            warnings.warn(
                f"Building {row.get('key')!r} references unknown building "
                f"group {group_key!r}; skipping group-attribute join."
            )
            continue
        for attr_key, attr_value in attrs.items():
            if isinstance(attr_value, (dict, Tree)):
                continue
            if isinstance(attr_value, list):
                value: Any = "+".join(str(v) for v in attr_value)
            else:
                value = attr_value
            column = f"building_group_{attr_key}" if attr_key in row else attr_key
            row[column] = value
