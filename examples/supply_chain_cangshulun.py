# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Generate the cangshulun per-good supply-chain detail table."""

from __future__ import annotations

from dataclasses import dataclass
from pathlib import Path

import pandas as pd

if __package__:
    from . import (
        ARTIFACTS_DIR,
        CANGSHULUN_BUILDING_LIMITS,
        CANGSHULUN_THROUGHPUT_GROUPS,
        CANGSHULUN_VIDEO_BANNED_PMS,
        DATASETS_DIR,
        DEFAULT_BANNED_BGS,
    )
    from .supply_chain_compare import load_economy
else:
    from __init__ import (
        ARTIFACTS_DIR,
        CANGSHULUN_BUILDING_LIMITS,
        CANGSHULUN_THROUGHPUT_GROUPS,
        CANGSHULUN_VIDEO_BANNED_PMS,
        DATASETS_DIR,
        DEFAULT_BANNED_BGS,
    )
    from supply_chain_compare import load_economy

from vic3_analysis import Economy, Scenario, sweep_supply_chains

NORMALIZED_VALUE = 100000.0
VIDEO_BAN_CONFIG = "cangshulun_video"


@dataclass(frozen=True)
class Variant:
    """A named product variant and its local PM/era constraints."""

    name: str
    good: str
    banned_pms: tuple[str, ...] = ()
    building_level_caps: tuple[tuple[str, float], ...] = ()
    era_cap: int = 5


_VARIANTS = (
    Variant(
        "glass_bone_china",
        "porcelain",
        banned_pms=("pm_forest_glass", "pm_leaded_glass", "pm_crystal_glass"),
    ),
    Variant(
        "luxury_furniture",
        "luxury_furniture",
        banned_pms=(
            "pm_handcrafted_furniture",
            "pm_lathe",
            "pm_no_luxuries",
            "pm_luxury_furniture",
        ),
    ),
    Variant(
        "logging_hardwood",
        "hardwood",
        banned_pms=("pm_simple_forestry", "pm_saw_mills"),
    ),
    Variant(
        "groceries_with_liquor",
        "liquor",
        banned_pms=(
            "pm_bakery",
            "pm_sweeteners",
            "pm_disabled_canning",
            "pm_cannery",
            "pm_cannery_fish",
            "pm_vacuum_canning",
            "pm_disabled_distillery",
            "pm_pot_stills",
        ),
    ),
    Variant(
        "luxury_clothes",
        "luxury_clothes",
        banned_pms=(
            "pm_handsewn_clothes",
            "pm_dye_workshops",
            "pm_sewing_machines",
        ),
    ),
    Variant(
        "urban_center_transportation",
        "services",
        banned_pms=(
            "pm_market_stalls",
            "pm_market_squares",
            "pm_covered_markets",
            "pm_no_street_lighting",
            "pm_gas_streetlights",
            "pm_no_public_transport",
            "pm_public_trams",
        ),
    ),
    Variant("coal_fired_plant", "electricity", banned_pms=("pm_oil-fired_plant",)),
)


def _video_throughput_multipliers(economy: Economy) -> tuple[tuple[str, float], ...]:
    """Expand group bonuses to each distinct building in table order."""
    group_multipliers = dict(CANGSHULUN_THROUGHPUT_GROUPS)
    if "building_group" not in economy.df_production.columns:
        return ()
    bonuses: list[tuple[str, float]] = []
    seen: set[str] = set()
    for building, group in zip(
        economy.df_production["building"], economy.df_production["building_group"]
    ):
        building_key = str(building)
        multiplier = group_multipliers.get(str(group))
        if multiplier is not None and building_key not in seen:
            bonuses.append((building_key, multiplier))
            seen.add(building_key)
    return tuple(bonuses)


def _template(
    *,
    name: str,
    throughput_multipliers: tuple[tuple[str, float], ...],
    banned_pms: tuple[str, ...] = CANGSHULUN_VIDEO_BANNED_PMS,
    building_level_caps: tuple[tuple[str, float], ...] = CANGSHULUN_BUILDING_LIMITS,
    era_cap: int = 5,
) -> Scenario:
    return Scenario(
        name=name,
        default_min_goods_output=0.0,
        objective="automation",
        era_cap=era_cap,
        banned_building_groups=DEFAULT_BANNED_BGS,
        banned_pms=banned_pms,
        building_level_caps=building_level_caps,
        throughput_multipliers=throughput_multipliers,
    )


def main(
    *, datasets_dir: Path = DATASETS_DIR, output_dir: Path = ARTIFACTS_DIR
) -> pd.DataFrame:
    """Solve the detail basket and save one configuration-level summary."""
    economy = load_economy(datasets_dir)
    bonuses = _video_throughput_multipliers(economy)

    base = sweep_supply_chains(
        economy,
        _template(name="base", throughput_multipliers=bonuses),
        target_value=NORMALIZED_VALUE,
    ).summary
    base.insert(1, "variant", "base")
    frames = [base]

    for variant in _VARIANTS:
        if variant.good not in economy.goods_index:
            continue
        frame = sweep_supply_chains(
            economy,
            _template(
                name=variant.name,
                throughput_multipliers=bonuses,
                banned_pms=CANGSHULUN_VIDEO_BANNED_PMS + variant.banned_pms,
                building_level_caps=(
                    CANGSHULUN_BUILDING_LIMITS + variant.building_level_caps
                ),
                era_cap=variant.era_cap,
            ),
            goods=[variant.good],
            target_value=NORMALIZED_VALUE,
        ).summary
        frame.insert(1, "variant", variant.name)
        frames.append(frame)

    result = pd.concat(frames, ignore_index=True)
    result.insert(2, "ban_config", VIDEO_BAN_CONFIG)
    root = output_dir / "analyses" / "supply_chains"
    index_dir = root / VIDEO_BAN_CONFIG
    index_dir.mkdir(parents=True, exist_ok=True)
    result.to_csv(index_dir / "summary.csv", index=False, encoding="utf-8")
    return result


if __name__ == "__main__":
    main()
