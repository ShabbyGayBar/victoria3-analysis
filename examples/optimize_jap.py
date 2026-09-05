import pandas as pd

from vic3_analysis import (
    Economy,
    Scenario,
    compare_scenarios,
    state_region_arable_land_limit,
    state_region_resource_limits,
)
from __init__ import DEFAULT_BANNED_BGS, TABLES_DIR

JAPAN_STATES = (
    "STATE_HOKKAIDO",
    "STATE_TOHOKU",
    "STATE_KANTO",
    "STATE_TOKAI",
    "STATE_HOKUSHINETSU",
    "STATE_KANSAI",
    "STATE_KYOTO",
    "STATE_KYUSHU",
    "STATE_RYUKYU_ISLANDS",
    "STATE_CHUGOKU",
    "STATE_SHIKOKU",
)

df_production_table = pd.read_csv(TABLES_DIR / "production_table.csv")
df_goods = pd.read_csv(TABLES_DIR / "goods.csv")
df_pop_types = pd.read_csv(TABLES_DIR / "pop_types.csv")
df_state_regions = pd.read_csv(TABLES_DIR / "state_regions.csv")

economy = Economy(
    df_production=df_production_table, df_goods=df_goods, df_pop_types=df_pop_types
)

resource_limits = state_region_resource_limits(df_state_regions, JAPAN_STATES)
arable_land_cap = state_region_arable_land_limit(df_state_regions, JAPAN_STATES)
employment_caps = range(1_000_000, 100_000_001, 1_000_000)
scenarios: list[Scenario] = []
for employment_cap in employment_caps:
    scenarios.append(
        Scenario(
            objective="gdp",
            import_limit=0.0,
            banned_building_groups=DEFAULT_BANNED_BGS,
            building_limits=tuple(resource_limits.items()),
            employment_cap=employment_cap,
            arable_land_cap=arable_land_cap,
            era_cap=5,
        ),
    )

state_comparison = compare_scenarios(economy, scenarios)
state_comparison.insert(0, "employment_cap", employment_caps)
state_comparison = state_comparison.drop(
    columns=[
        "name",
        "produce",
        "base_price",
        "n_active_buildings",
        "chain_depth",
        "n_raw_inputs",
        "bottleneck_good",
        "bottleneck_cost_share",
        "bottleneck_marginal",
    ]
)
state_comparison.to_csv(TABLES_DIR / "optimize_jap.csv", index=False)
