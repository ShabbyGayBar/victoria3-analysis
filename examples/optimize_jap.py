# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

import pandas as pd

if __package__:
    from . import DEFAULT_BANNED_BGS, JAPAN_DIR, PARSED_DIR, PRODUCTION_DIR
else:
    from __init__ import DEFAULT_BANNED_BGS, JAPAN_DIR, PARSED_DIR, PRODUCTION_DIR

from vic3_analysis import (
    Economy,
    NominalOptimizer,
    Scenario,
    state_region_arable_land_limit,
    state_region_resource_limits,
)

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

df_production_table = pd.read_csv(PRODUCTION_DIR / "production_table.csv")
df_goods = pd.read_csv(PARSED_DIR / "goods.csv")
df_pop_types = pd.read_csv(PARSED_DIR / "pop_types.csv")
df_state_regions = pd.read_csv(PARSED_DIR / "state_regions.csv")

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
            default_min_goods_output=0.0,
            banned_building_groups=DEFAULT_BANNED_BGS,
            building_level_caps=tuple(resource_limits.items()),
            employment_cap=employment_cap,
            arable_land_cap=arable_land_cap,
            era_cap=5,
        ),
    )

rows: list[dict[str, object]] = []
for employment_cap, scenario in zip(employment_caps, scenarios):
    optimizer = NominalOptimizer(economy)
    try:
        state = optimizer.solve(scenario)
        rows.append(
            {
                "employment_cap": employment_cap,
                "status": "success",
                "annual_gdp": state.gdp(annual=True),
                "employment": state.total_population,
                "construction_cost": economy.construction_cost(state),
                "gdp_per_capita": state.gdp_per_capita(annual=True),
                "arable_land_consumption": economy.arable_land_consumption(state),
                "error": "",
            }
        )
    except ValueError as exc:
        rows.append(
            {
                "employment_cap": employment_cap,
                "status": "failure",
                "annual_gdp": float("nan"),
                "employment": float("nan"),
                "construction_cost": float("nan"),
                "gdp_per_capita": float("nan"),
                "arable_land_consumption": float("nan"),
                "error": str(exc),
            }
        )

state_comparison = pd.DataFrame(rows)
JAPAN_DIR.mkdir(parents=True, exist_ok=True)
state_comparison.to_csv(JAPAN_DIR / "employment_sweep.csv", index=False)
