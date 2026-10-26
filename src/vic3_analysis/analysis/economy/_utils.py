# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Shared array ownership and validation helpers."""

from __future__ import annotations

from typing import TYPE_CHECKING

import numpy as np
import pandas as pd

if TYPE_CHECKING:
    from vic3_analysis.analysis.economy.model import Economy
    from vic3_analysis.analysis.economy.states import EconomyContext, EconomyState


def _readonly_array(value: np.ndarray) -> np.ndarray:
    """Return an owned, read-only float64 copy of an array."""
    result = np.array(value, dtype=np.float64, copy=True)
    result.setflags(write=False)
    return result


def _readonly_wealth(value: np.ndarray, name: str) -> np.ndarray:
    """Copy non-negative integer wealth to read-only int64 without truncation."""
    value = np.asarray(value)
    if value.dtype.kind not in "iuf" or not np.isfinite(value).all():
        raise ValueError(f"{name} must contain finite non-negative int64 values.")
    if value.dtype.kind == "f":
        invalid = (value != np.trunc(value)) | (value >= 2**63)
    else:
        invalid = value > np.iinfo(np.int64).max
    if (value < 0).any() or invalid.any():
        raise ValueError(f"{name} must contain finite non-negative int64 values.")
    result = np.array(value, dtype=np.int64, copy=True)
    result.setflags(write=False)
    return result


def _validate_nonnegative_values(value: np.ndarray, name: str) -> np.ndarray:
    """Validate finite, non-negative numeric values and return a float64 array."""
    try:
        result = np.asarray(value, dtype=np.float64)
    except (TypeError, ValueError) as exc:
        raise ValueError(f"{name} must contain numeric values.") from exc
    if not np.isfinite(result).all() or (result < 0).any():
        raise ValueError(f"{name} must contain finite non-negative values.")
    return result


def _validate_columns(frame: pd.DataFrame, columns: set[str], name: str) -> None:
    """Require unambiguous columns before compiling population coefficients."""
    if not frame.columns.is_unique or not columns.issubset(frame.columns):
        raise ValueError(
            f"{name} must have unique columns including {sorted(columns)}."
        )


def _validate_index_keys(keys: tuple[str, ...], name: str) -> None:
    """Require unique, non-empty string keys at coefficient validation time."""
    if any(not isinstance(key, str) or not key for key in keys) or len(
        set(keys)
    ) != len(keys):
        raise ValueError(f"{name} must contain unique non-empty keys.")


def _validate_worker_counts(
    economy: Economy, state: EconomyState | EconomyContext
) -> np.ndarray:
    """Validate household alignment and return non-negative worker counts."""
    # Imported lazily because snapshot classes use the array helpers above.
    from vic3_analysis.analysis.economy.states import EconomyState

    expected_shape = (len(economy.building_index), len(economy.pop_index))
    names = ("pops", "pop_wealth") if isinstance(state, EconomyState) else ("pops",)
    for name in names:
        if getattr(state, name).shape != expected_shape:
            raise ValueError(
                f"state.{name} shape must match building_index and pop_index."
            )
    return _validate_nonnegative_values(state.pops, "state.pops")


def _validate_building_goods_flow(
    economy: Economy, state: EconomyState | EconomyContext
) -> None:
    """Require finite signed flows aligned to this economy's configurations/goods."""
    if state.building_goods_flow.shape != (
        len(economy.building_index),
        len(economy.goods_index),
    ):
        raise ValueError(
            "state.building_goods_flow shape must match building_index and goods_index."
        )
    if not np.isfinite(state.building_goods_flow).all():
        raise ValueError("state.building_goods_flow must contain finite values.")


def _validate_goods_vector(
    economy: Economy,
    vector: np.ndarray,
    name: str,
    *,
    nonnegative: bool = True,
) -> np.ndarray:
    """Validate a finite goods vector, optionally allowing signed quantities."""
    if vector.ndim != 1:
        raise ValueError(f"{name} must be a 1-D array.")
    if vector.shape[0] != len(economy.goods_index):
        raise ValueError(f"{name} length must match the number of goods.")
    if not np.isfinite(vector).all():
        raise ValueError(f"{name} must contain only finite values.")
    if nonnegative and (vector < 0).any():
        raise ValueError(f"{name} must contain only non-negative values.")
    return vector.astype(np.float64, copy=False)
