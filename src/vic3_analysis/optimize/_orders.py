# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validation and aggregation of fixed goods orders."""

import numpy as np


def goods_order_vector(
    goods_index: tuple[str, ...], entries: tuple[tuple[str, float], ...], name: str
) -> np.ndarray:
    """Translate named fixed market context into a goods-aligned vector."""
    positions = {good: i for i, good in enumerate(goods_index)}
    vector = np.zeros(len(positions), dtype=np.float64)
    amount_rule = "finite non-negative numbers"
    for entry in entries:
        if not isinstance(entry, tuple) or len(entry) != 2:
            raise ValueError(f"{name} entries must be (good, amount) pairs.")
        good, amount = entry
        if not isinstance(good, str):
            raise TypeError(f"{name} good keys must be strings.")
        if good not in positions:
            raise ValueError(f"Good '{good}' in {name} was not found in goods index.")
        try:
            value = float(amount)
        except (TypeError, ValueError) as exc:
            raise ValueError(f"{name} amounts must be {amount_rule}.") from exc
        if not np.isfinite(value) or value < 0:
            raise ValueError(f"{name} amounts must be {amount_rule}.")
        position = positions[good]
        previous = float(vector[position])
        if abs(value) > np.finfo(np.float64).max - abs(previous):
            raise ValueError(f"{name} totals must remain finite.")
        vector[position] += value
    return vector
