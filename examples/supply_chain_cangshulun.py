"""Generate the cangshulun per-good supply-chain detail table.

The base basket contains one normalised, autarkic automation scenario for
every good that the current production table can produce.  A small set of
named variants is kept alongside it to make common PM choices comparable.
"""

from __future__ import annotations

from dataclasses import dataclass

import pandas as pd

from vic3_analysis import Economy, Scenario, compare_scenarios

from __init__ import (
    CANGSHULUN_THROUGHPUT_GROUPS,
    CANGSHULUN_VIDEO_BANNED_PMS,
    CANGSHULUN_BUILDING_LIMITS,
    DEFAULT_BANNED_BGS,
    TABLES_DIR,
)

NORMALIZED_VALUE = 100000.0
VIDEO_BAN_CONFIG = "cangshulun_video"


@dataclass(frozen=True)
class Variant:
    """A named product variant and its local PM/era constraints."""

    name: str
    good: str
    banned_pms: tuple[str, ...] = ()
    building_limits: tuple[tuple[str, float], ...] = ()
    era_cap: int = 5


_VARIANTS = (
    # The variant bans porcelain/ceramics and therefore selects the
    # disabled-ceramics glass route that remains in the video configuration.
    Variant(
        "glass_bone_china",
        "porcelain",
        banned_pms=(
            "pm_forest_glass",
            "pm_leaded_glass",
            "pm_crystal_glass",
        ),
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
        banned_pms=("pm_handsewn_clothes", "pm_dye_workshops", "pm_sewing_machines"),
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
    Variant(
        "coal_fired_plant",
        "electricity",
        banned_pms=("pm_oil-fired_plant",),
    ),
)


def _video_throughput_bonuses(economy: Economy) -> tuple[tuple[str, float], ...]:
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


def _scenario(
    *,
    name: str,
    good: str,
    target: float,
    throughput_bonuses: tuple[tuple[str, float], ...],
    banned_pms: tuple[str, ...] = CANGSHULUN_VIDEO_BANNED_PMS,
    building_limits: tuple[tuple[str, float], ...] = CANGSHULUN_BUILDING_LIMITS,
    era_cap: int = 5,
) -> Scenario:
    """Build one consistently constrained video scenario."""
    return Scenario(
        name=name,
        produce=((good, target),),
        objective="automation",
        import_limit=0.0,
        era_cap=era_cap,
        banned_building_groups=DEFAULT_BANNED_BGS,
        banned_pms=banned_pms,
        building_limits=building_limits,
        throughput_bonuses=throughput_bonuses,
    )


def main() -> pd.DataFrame:
    """Solve the detail basket and write ``supply_chain_cangshulun.csv``."""
    production = pd.read_csv(TABLES_DIR / "production_table.csv")
    goods = pd.read_csv(TABLES_DIR / "goods.csv")
    pop_types = pd.read_csv(TABLES_DIR / "pop_types.csv")
    economy = Economy(df_production=production, df_goods=goods, df_pop_types=pop_types)
    price_map = dict(zip(economy.goods_index(), economy.base_prices()))
    throughput_bonuses = _video_throughput_bonuses(economy)

    scenarios: list[Scenario] = []
    metadata: list[tuple[str, str, float]] = []
    for good in economy.producible_goods():
        target = NORMALIZED_VALUE / price_map[good]
        scenarios.append(
            _scenario(
                name="base",
                good=good,
                target=target,
                throughput_bonuses=throughput_bonuses,
            )
        )
        metadata.append(("base", good, target))
    for variant in _VARIANTS:
        if variant.good not in price_map:
            continue
        target = NORMALIZED_VALUE / price_map[variant.good]
        variant_bans = CANGSHULUN_VIDEO_BANNED_PMS + variant.banned_pms
        variant_limits = list(
            CANGSHULUN_BUILDING_LIMITS + variant.building_limits
        )
        if variant.name == "grain_wheat_no_secondary":
            # Grain is produced by several crop buildings.  A zero limit on
            # the alternatives makes the stable English name an actual wheat
            # farm comparison, without globally banning those buildings.
            grain_output = production.get("goods_grain")
            if grain_output is not None:
                grain_buildings = production.loc[
                    grain_output.fillna(0).astype(float) > 0, "building"
                ].astype(str)
                for building in grain_buildings.unique():
                    if building != "building_wheat_farm":
                        variant_limits.append((building, 0.0))
        scenarios.append(
            _scenario(
                name=variant.name,
                good=variant.good,
                target=target,
                throughput_bonuses=throughput_bonuses,
                banned_pms=variant_bans,
                building_limits=tuple(variant_limits),
                era_cap=variant.era_cap,
            )
        )
        metadata.append((variant.name, variant.good, target))

    result = compare_scenarios(economy, scenarios)
    result = result.rename(columns={"name": "scenario"})
    result["goods"] = [good for _name, good, _target in metadata]
    result["ban_config"] = VIDEO_BAN_CONFIG
    result["production"] = [target for _name, _good, target in metadata]
    result = result.drop(columns=["produce"])

    level_columns = [column for column in result.columns if column.startswith("level_")]
    per_10k_columns = [
        f"level_per_10k_{column.removeprefix('level_')}" for column in level_columns
    ]
    employment = result["employment"]
    for source, destination in zip(level_columns, per_10k_columns):
        # ``np.divide`` is deliberately avoided here: pandas' scalar division
        # preserves the desired 0/0 -> NaN and nonzero/0 -> inf semantics
        # without emitting a runtime warning for failed rows.
        result[destination] = result[source] / employment * 10000.0

    fixed_columns = [
        "scenario",
        "goods",
        "objective",
        "ban_config",
        "production",
        "base_price",
        "annual_gdp",
        "employment",
        "gdp_per_capita",
        "construction_cost",
        "gdp_per_construction",
        "era_cap",
        "arable_land_consumption",
    ]
    tail_columns = [
        "n_active_buildings",
        "chain_depth",
        "n_raw_inputs",
        "bottleneck_good",
        "bottleneck_cost_share",
        "bottleneck_marginal",
        "error",
    ]
    result = result.loc[
        :, fixed_columns + level_columns + per_10k_columns + tail_columns
    ]
    result = result.sort_values(
        "gdp_per_capita", ascending=False, kind="stable", na_position="last"
    ).reset_index(drop=True)
    result.to_csv(TABLES_DIR / "supply_chain_cangshulun.csv", index=False)
    return result


if __name__ == "__main__":
    main()
