# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Production coefficients, throughput, and resource accounting."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np

from vic3_analysis.analysis.economy._utils import (
    _readonly_array,
)
from vic3_analysis.analysis.economy.states import (
    EconomyState,
)

if TYPE_CHECKING:
    from vic3_analysis.analysis.economy.model import Economy


_ARABLE_LAND_BUILDING_GROUPS: frozenset[str] = frozenset(
    {
        "bg_staple_crops",
        "bg_ranching",
        "bg_agriculture",
        "bg_plantations",
        "bg_subsistence_agriculture",
        "bg_subsistence_ranching",
    }
)


_METADATA_DEFAULTS: dict[str, str | bool] = {
    "building_group": "",
    "parent_group": "",
    "land_usage": "",
    "is_subsistence": False,
    "discoverable_resource": False,
    "depletable_resource": False,
}


def building_index(economy: Economy) -> tuple[str, ...]:
    """Return production-configuration keys in production-table row order.

    Each key combines the row's building and production-method strings with
    ``"+"``. The resulting order defines the alignment of building-level
    vectors and the rows of building matrices.
    """
    return tuple(
        f"{b}+{pm}"
        for b, pm in zip(
            economy.df_production["building"],
            economy.df_production["production_method"],
        )
    )


def goods_index(economy: Economy) -> tuple[str, ...]:
    """Return good keys in goods-table row order.

    This order defines the alignment of goods vectors and the columns of
    goods matrices.
    """
    return tuple(economy.df_goods["key"].tolist())


def producible_goods(economy: Economy) -> tuple[str, ...]:
    """Return goods that have at least one producer configuration.

    Returns:
        A tuple of good keys that can be produced by at least one building
        configuration in the production table.
    """
    out_mat = economy.goods_output_matrix_unscaled
    goods_index = economy.goods_index
    return tuple(g for j, g in enumerate(goods_index) if (out_mat[:, j] > 0).any())


def pop_index(economy: Economy) -> tuple[str, ...]:
    """Return profession keys in pop-types-table row order.

    This order defines the alignment of profession vectors and employment
    matrix columns.
    """
    return tuple(economy.df_pop_types["key"].tolist())


def base_prices(economy: Economy) -> np.ndarray:
    """Return Victoria 3 base prices aligned to `goods_index`."""
    return _readonly_array(economy.df_goods["cost"].to_numpy(dtype=np.float64))


def _apply_throughput_multipliers(
    economy: Economy,
    matrix: np.ndarray,
    throughput_multipliers: (np.ndarray[tuple[int], np.dtype[np.float64]] | None),
) -> np.ndarray:
    """Scale matrix rows by optional per-configuration multipliers."""
    if throughput_multipliers is None:
        return matrix.copy()
    _validate_throughput_multipliers(economy, throughput_multipliers)
    return matrix * throughput_multipliers[:, None]


def _validate_throughput_multipliers(
    economy: Economy,
    throughput_multipliers: np.ndarray[tuple[int], np.dtype[np.float64]],
) -> None:
    """Validate a production-row-aligned throughput multiplier vector."""
    if throughput_multipliers.ndim != 1:
        raise ValueError("throughput_multipliers must be a 1-D array.")
    if throughput_multipliers.shape[0] != len(economy.building_index):
        raise ValueError(
            "throughput_multipliers length must match the number of rows "
            "in the production table."
        )


def economy_of_scale_bonuses(
    economy: Economy,
    building_levels: np.ndarray[tuple[int], np.dtype[np.float64]],
    level_cap: float = 20.0,
) -> np.ndarray:
    """Return per-configuration economy-of-scale throughput bonuses.

    Levels are summed across all production-method configurations of each
    building. Eligible configurations receive one percentage point of
    throughput per total building level, capped by *level_cap*. Returned
    values are additive bonuses (for example, ``0.2`` for +20%), not full
    multipliers.

    Args:
        building_levels: Production-row-aligned building levels.
        level_cap: Maximum number of levels contributing to the bonus.

    Returns:
        A 1-D bonus vector aligned to the production table.

    Raises:
        ValueError: If *building_levels* is not aligned to the production
            table or *level_cap* is negative or non-finite.
    """
    expected_shape = (len(economy.df_production),)
    if building_levels.shape != expected_shape:
        raise ValueError("building_levels shape must match the production table.")
    if not np.isfinite(level_cap) or level_cap < 0:
        raise ValueError("level_cap must be a non-negative finite number.")
    if "economy_of_scale" not in economy.df_production.columns:
        return np.zeros(expected_shape, dtype=np.float64)

    buildings = economy.df_production["building"].astype(str).to_numpy()
    totals = _levels_by_building(economy, building_levels)

    eligible = (
        economy.df_production["economy_of_scale"]
        .fillna(False)
        .eq(True)
        .to_numpy(dtype=bool)
    )
    bonuses = np.zeros(expected_shape, dtype=np.float64)
    for i, building in enumerate(buildings):
        if eligible[i]:
            bonuses[i] = 0.01 * min(max(totals[building], 0.0), level_cap)
    return bonuses


def _goods_matrices_unscaled(economy: Economy) -> tuple[np.ndarray, np.ndarray]:
    """Extract signed coefficients once and return owned input/output matrices."""
    goods_columns = [f"goods_{good}" for good in economy.goods_index]
    matrix = economy.df_production.reindex(
        columns=goods_columns, fill_value=0
    ).to_numpy(dtype=np.float64)
    return (
        _readonly_array(np.maximum(-matrix, 0)),
        _readonly_array(np.maximum(matrix, 0)),
    )


def goods_input_matrix_unscaled(economy: Economy) -> np.ndarray:
    """Cached read-only gross inputs per level, without throughput scaling."""
    return economy._goods_matrices_unscaled[0]


def goods_output_matrix_unscaled(economy: Economy) -> np.ndarray:
    """Cached read-only gross outputs per level, without throughput scaling."""
    return economy._goods_matrices_unscaled[1]


def goods_input_matrix(
    economy: Economy,
    throughput_multipliers: (
        np.ndarray[tuple[int], np.dtype[np.float64]] | None
    ) = None,
) -> np.ndarray:
    """Return writable gross inputs using the cached unscaled matrix."""
    return _apply_throughput_multipliers(
        economy, economy.goods_input_matrix_unscaled, throughput_multipliers
    )


def goods_output_matrix(
    economy: Economy,
    throughput_multipliers: (
        np.ndarray[tuple[int], np.dtype[np.float64]] | None
    ) = None,
) -> np.ndarray:
    """Return writable gross outputs using the cached unscaled matrix."""
    return _apply_throughput_multipliers(
        economy, economy.goods_output_matrix_unscaled, throughput_multipliers
    )


def employment_matrix(economy: Economy) -> np.ndarray:
    """Return employment by production configuration and profession.

    Rows align to `building_index` and columns align to
    `pop_index`. Values are the number of employees per building
    level; missing profession columns are filled with zero.
    """
    employment_columns = [f"employment_{pop}" for pop in economy.pop_index]

    return _readonly_array(
        economy.df_production.reindex(
            columns=employment_columns, fill_value=0
        ).to_numpy(dtype=np.float64)
    )


def employment_vector(economy: Economy) -> np.ndarray:
    """Total employment per building level, aligned to production-table rows.

    Returns:
        A 1-D array of shape ``(n_buildings,)`` giving the total employment
        of each building configuration per level (``"employment"`` column,
        missing values zero-filled).
    """
    return _readonly_array(
        economy.df_production["employment"].fillna(0).to_numpy(dtype=np.float64)
    )


def construction_cost_vector(economy: Economy) -> np.ndarray:
    """Return per-level construction cost aligned to `building_index`."""
    return _readonly_array(
        economy.df_production["construction_cost"].to_numpy(dtype=np.float64)
    )


def infrastructure_vector(economy: Economy) -> np.ndarray:
    """Cached infrastructure usage per level; missing values default to zero."""
    if "infrastructure_usage_per_level" not in economy.df_production.columns:
        return _readonly_array(np.zeros(len(economy.df_production)))
    return _readonly_array(
        economy.df_production["infrastructure_usage_per_level"]
        .fillna(0)
        .to_numpy(dtype=np.float64)
    )


def _fill_production_metadata_defaults(economy: Economy) -> None:
    """Fill missing columns and null metadata in the owned production table."""
    production = economy.df_production
    for column, default in _METADATA_DEFAULTS.items():
        if column not in production.columns:
            production[column] = default
        else:
            production[column] = production[column].fillna(default)


def construction_cost(economy: Economy, state: EconomyState) -> float:
    """Calculate the total construction cost for an `EconomyState`.

    Args:
        state: The `EconomyState` to evaluate (as produced by
            `solve`).

    Returns:
        The dot product of ``building_levels`` with the per-configuration
        construction cost vector.
    """
    return float(np.dot(state.building_levels, economy.construction_cost_vector))


def arable_land_vector(economy: Economy) -> np.ndarray:
    """Return arable-land consumption per production configuration.

    Returns:
        A float vector aligned to the production table, with ``1.0`` for
        agricultural, plantation, ranching, and subsistence land-use
        configurations and ``0.0`` otherwise.
    """
    if "building_group" not in economy.df_production.columns:
        return _readonly_array(np.zeros(len(economy.df_production)))
    return _readonly_array(
        economy.df_production["building_group"]
        .isin(tuple(_ARABLE_LAND_BUILDING_GROUPS))
        .to_numpy(dtype=np.float64)
    )


def arable_land_consumption(economy: Economy, state: EconomyState) -> float:
    """Return the total arable land consumed by an economy state.

    Each building level consumes one unit of arable land when its building
    group is agricultural, plantation, ranching, or subsistence land use.

    Args:
        state: The `EconomyState` whose land consumption is summed.

    Returns:
        The sum of building-configuration levels in arable-land-consuming
        building groups.

    Raises:
        ValueError: If the state's building-level vector is not aligned to
            the production table.
    """
    expected_shape = (len(economy.df_production),)
    if state.building_levels.shape != expected_shape:
        raise ValueError("state.building_levels shape must match the production table.")

    return float(np.dot(state.building_levels, economy.arable_land_vector))


def _levels_by_building(
    economy: Economy, building_levels: np.ndarray
) -> dict[str, float]:
    """Sum aligned configuration levels in building first-appearance order."""
    totals: dict[str, float] = {}
    for building, level in zip(economy.df_production["building"], building_levels):
        key = str(building)
        totals[key] = totals.get(key, 0.0) + float(level)
    return totals


def levels_per_building(economy: Economy, state: EconomyState) -> dict[str, float]:
    """Return total levels per building across all PM configurations.

    Building levels in `EconomyState` are aligned to production-table
    rows, where one building can appear in many production-method
    configurations.  This method aggregates those configuration levels by
    building key while preserving the buildings' first-appearance order in
    `df_production`.

    Args:
        state: The `EconomyState` whose levels are aggregated.

    Returns:
        A mapping from every building key in the production table to its
        total level.  Unused buildings are included with value ``0.0``.

    Raises:
        ValueError: If the state's building-level vector is not aligned to
            the production table.
    """
    expected_shape = (len(economy.df_production),)
    if state.building_levels.shape != expected_shape:
        raise ValueError("state.building_levels shape must match the production table.")

    return _levels_by_building(economy, state.building_levels)
