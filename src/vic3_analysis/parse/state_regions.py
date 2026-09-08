"""
Parser for Victoria 3 state region definitions.

Reads state region data from the game's ``map_data/state_regions`` directory and exposes
it as a ``pyradox.Tree`` subclass with helper methods for DataFrame conversion
and state region look-ups.
"""

from collections.abc import Iterable
from pathlib import Path
from typing import Any

import numpy as np
import pandas as pd
from pyradox import Tree

from vic3_analysis import get_vic3_directory, parse_merge

_skip_keys = [
    "provinces",
    "impassable",
    "prime_land",
    "traits",
    "arable_resources",
    "resource",
    "capped_resources",
]


def _select_state_regions(
    state_regions_df: pd.DataFrame, state_region_keys: Iterable[str]
) -> pd.DataFrame:
    """Return requested state-region rows after validating their keys."""
    if "key" not in state_regions_df.columns:
        raise ValueError("state_regions_df must contain a 'key' column.")

    keys = tuple(dict.fromkeys(state_region_keys))
    known_keys = set(state_regions_df["key"].astype(str))
    unknown_keys = [key for key in keys if key not in known_keys]
    if unknown_keys:
        joined = ", ".join(repr(key) for key in unknown_keys)
        raise ValueError(f"Unknown state-region key(s): {joined}.")
    selected = state_regions_df[state_regions_df["key"].astype(str).isin(keys)]
    if not isinstance(selected, pd.DataFrame):
        raise TypeError("Expected state-region row selection to return a DataFrame.")
    return selected


def state_region_arable_land_limit(
    state_regions_df: pd.DataFrame, state_region_keys: Iterable[str]
) -> float:
    """Return total arable land across selected state regions.

    Args:
        state_regions_df: Parsed state-region DataFrame.
        state_region_keys: State-region keys to aggregate. Repeated keys are
            counted once.

    Returns:
        The sum of the selected regions' ``arable_land`` values.

    Raises:
        ValueError: If required columns are missing or a requested key is
            unknown.
    """
    selected = _select_state_regions(state_regions_df, state_region_keys)
    if "arable_land" not in selected.columns:
        raise ValueError("state_regions_df must contain an 'arable_land' column.")
    values = selected["arable_land"]
    if not isinstance(values, pd.Series):
        raise TypeError("Expected unique column 'arable_land'.")
    numeric = (
        pd.to_numeric(values, errors="coerce")
        .fillna(0)  # pyright: ignore[reportAttributeAccessIssue]
        .to_numpy(dtype=np.float64)
    )
    return float(np.sum(numeric))


def state_region_resource_limits(
    state_regions_df: pd.DataFrame, state_region_keys: Iterable[str]
) -> dict[str, float]:
    """Aggregate state-region resource capacity into building-level limits.

    The input is the flattened output of `StateRegionsParser.to_dataframe`.
    Only total-potential ``resource_*`` columns are used; discovered and
    undiscovered component columns and arable-land data are intentionally
    excluded.  Every resource building represented by the DataFrame is returned,
    including a zero limit when it is absent from the selected regions.

    Gold fields are a discoverable precursor to gold mines.  For long-run
    nominal optimisation their potential is added to ``building_gold_mine`` and
    ``building_gold_field`` is assigned a zero limit.

    Args:
        state_regions_df: Parsed state-region DataFrame.
        state_region_keys: State-region keys to aggregate. Repeated keys are
            counted once.

    Returns:
        An insertion-ordered mapping suitable for
        ``Scenario(building_limits=tuple(limits.items()))``.

    Raises:
        ValueError: If the DataFrame has no ``key`` column or a requested state
            region is unknown.
    """
    selected = _select_state_regions(state_regions_df, state_region_keys)
    resource_columns = [
        column
        for column in state_regions_df.columns
        if isinstance(column, str) and column.startswith("resource_")
    ]

    limits: dict[str, float] = {}
    for column in resource_columns:
        building = column.removeprefix("resource_")
        column_values = selected[column]
        if not isinstance(column_values, pd.Series):
            raise TypeError(f"Expected unique column {column!r}.")
        values = (
            pd.to_numeric(column_values, errors="coerce")
            .fillna(0)  # pyright: ignore[reportAttributeAccessIssue]
            .to_numpy(dtype=np.float64)
        )
        capacity = float(np.sum(values))
        if building == "building_gold_field":
            limits.setdefault("building_gold_field", 0.0)
            limits["building_gold_mine"] = (
                limits.get("building_gold_mine", 0.0) + capacity
            )
        elif building == "building_gold_mine":
            limits[building] = limits.get(building, 0.0) + capacity
        else:
            limits[building] = capacity
    return limits


class StateRegionsParser(Tree):
    """A ``pyradox.Tree`` subclass for parsing Victoria 3 state region definitions.

    Reads all ``.txt`` files from the game's ``map_data/state_regions`` directory
    and stores the parsed data in a tree structure that mirrors the original
    file hierarchy.  Provides helper methods for converting to a flat
    ``pandas.DataFrame`` and for looking up state region attributes & resources.
    """

    def __init__(self, game_dir: str | Path | None = None):
        """Initialise and populate the state regions tree.

        Args:
            game_dir: Path to the Victoria 3 ``game`` directory. If ``None``
                the directory is located automatically via
                `get_vic3_directory`.
        """
        super().__init__()
        if game_dir is None:
            game_dir = get_vic3_directory()

        parse_dir = Path(game_dir) / "map_data" / "state_regions"
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
        results: list[dict[str, Any]] = []
        for state_region_key, state_region_values in self.items():
            state_region: dict[str, Any] = {"key": state_region_key}
            state_region["province_count"] = len(
                list(state_region_values.find_all("provinces"))
            )
            for attribute_key, attribute_value in state_region_values.items():
                if attribute_key == "capped_resources":
                    for resource_key, resource_value in attribute_value.items():
                        state_region[f"resource_{resource_key}"] = resource_value
                    continue
                if attribute_key == "resource":
                    if not isinstance(attribute_value, Tree):
                        raise TypeError(
                            f"Expected 'resource' attribute to be a Tree, got {type(attribute_value).__name__}"
                        )
                    resource_key = attribute_value["type"]
                    undiscovered_raw = attribute_value.find("undiscovered_amount", 0)
                    if not isinstance(undiscovered_raw, (int, float)):
                        raise TypeError(
                            f"Expected numeric undiscovered_amount, got {type(undiscovered_raw).__name__}"
                        )
                    undiscovered_amount = int(undiscovered_raw)
                    discovered_raw = attribute_value.find("discovered_amount", 0)
                    if not isinstance(discovered_raw, (int, float)):
                        raise TypeError(
                            f"Expected numeric discovered_amount, got {type(discovered_raw).__name__}"
                        )
                    discovered_amount = int(discovered_raw)
                    state_region[f"resource_{resource_key}"] = (
                        undiscovered_amount + discovered_amount
                    )
                    state_region[f"undiscovered_amount_resource_{resource_key}"] = (
                        undiscovered_amount
                    )
                    state_region[f"discovered_amount_resource_{resource_key}"] = (
                        discovered_amount
                    )
                    continue
                if attribute_key in _skip_keys or isinstance(
                    attribute_value, (list, dict, Tree)
                ):
                    continue
                state_region[attribute_key] = attribute_value
            results.append(state_region)
        df = pd.DataFrame(results)
        # For every column whose name starts with "resource_" or "undiscovered_amount_resource_" or "discovered_amount_resource_",
        # convert the column to numeric, coercing errors to NaN, and then fill NaN values with 0
        for column in df.columns:
            if (
                column.startswith("resource_")
                or column.startswith("undiscovered_amount_resource_")
                or column.startswith("discovered_amount_resource_")
            ):
                df[column] = (
                    pd.to_numeric(df[column], errors="coerce").fillna(0).astype(int)  # pyright: ignore[reportAttributeAccessIssue]
                )
        return df
