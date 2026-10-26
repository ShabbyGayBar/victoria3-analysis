# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""
General-equilibrium economy model for Victoria 3.

Separates fixed `EconomyContext` inputs, `MarketState` prices and building
finances, and `PopState` household results inside a complete `EconomyState`.
`Economy` prepares consumption data and derives nominal, market, or equilibrium snapshots.
"""

from vic3_analysis.analysis.economy.model import Economy
from vic3_analysis.analysis.economy.states import (
    EconomyContext,
    EconomyState,
    EquilibriumDiagnostics,
    EquilibriumError,
    MarketState,
    PopState,
)

__all__ = [
    "Economy",
    "EconomyContext",
    "EconomyState",
    "EquilibriumDiagnostics",
    "EquilibriumError",
    "MarketState",
    "PopState",
]
