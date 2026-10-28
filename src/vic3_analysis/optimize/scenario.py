# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Declarative optimization scenarios for Victoria 3 economies."""

from dataclasses import dataclass
from math import isfinite

_OBJECTIVES = (
    "gdp",
    "gdp_per_capita",
    "average_wealth",
    "employment",
    "automation",
    "construction_cost",
)


@dataclass(frozen=True)
class Scenario:
    """An immutable optimization recipe expressed as data.

    The optimizer interpreting a scenario owns all economy-dependent
    compilation. This object records assumptions interpreted by the nominal,
    market, and equilibrium formulations.

    ``min_goods_balance`` sets the minimum weekly balance for every good:
    building output plus imports minus building inputs and exports. Household
    consumption is excluded. The default of ``0.0`` requires nonnegative
    balances; negative floors allow deficits, and ``None`` disables the floor.

    ``min_net_infrastructure`` sets minimum infrastructure generation minus
    consumption, weighted by building levels. ``0.0`` prevents a deficit;
    positive minima require spare capacity, negative minima allow a bounded
    deficit, and ``None`` leaves infrastructure unconstrained.

    ``goods_import`` and ``goods_export`` record fixed weekly ``(good, amount)``
    pairs with non-negative amounts. Imports add sell orders; exports add buy
    orders. Repeated entries are summed, and a good may be both imported and
    exported. These orders enter the goods-balance constraint when enabled.

    ``workforce_ratio`` is the uniform worker share of total population.
    It defaults to ``1.0``; employment constraints still count only workers.
    """

    objective: str = "automation"
    min_goods_balance: float | None = 0.0
    banned_pms: tuple[str, ...] = ()
    building_level_caps: tuple[tuple[str, float], ...] = ()
    banned_building_groups: tuple[str, ...] = ()
    throughput_multipliers: tuple[tuple[str, float], ...] = ()
    era_cap: int | None = None
    construction_cost_cap: float | None = None
    employment_cap: float | None = None
    arable_land_cap: float | None = None
    min_net_infrastructure: float | None = None
    urbanization_per_center: float | None = None
    name: str | None = None
    goods_import: tuple[tuple[str, float], ...] = ()
    goods_export: tuple[tuple[str, float], ...] = ()
    workforce_ratio: float = 1.0

    def __post_init__(self) -> None:
        """Validate values that are independent of an economy or optimizer."""
        if self.objective not in _OBJECTIVES:
            raise ValueError(f"Unknown objective: {self.objective!r}")
        if self.min_goods_balance is not None and not isfinite(self.min_goods_balance):
            raise ValueError("min_goods_balance must be finite or None.")
        if not isfinite(self.workforce_ratio) or not 0 < self.workforce_ratio <= 1:
            raise ValueError("workforce_ratio must be finite and in (0, 1].")

    def display_name(self) -> str:
        """Return the explicit name or one derived from the export goods basket."""
        if self.name is not None:
            return self.name
        if self.goods_export:
            return "+".join(dict.fromkeys(good for good, _amount in self.goods_export))
        return "unnamed"
