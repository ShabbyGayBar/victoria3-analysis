import pandas as pd
from __init__ import (
    CANGSHULUN_BANNED_PMS,
    CANGSHULUN_BUILDING_LIMITS,
    DEFAULT_BANNED_BGS,
    TABLES_DIR,
)

from vic3_analysis import Economy, Scenario, sweep_supply_chains

df_production_table = pd.read_csv(TABLES_DIR / "production_table.csv")
df_goods = pd.read_csv(TABLES_DIR / "goods.csv")
df_pop_types = pd.read_csv(TABLES_DIR / "pop_types.csv")

NORMALIZED_VALUE = 100000.0


economy = Economy(
    df_production=df_production_table, df_goods=df_goods, df_pop_types=df_pop_types
)
producible = economy.producible_goods()
print(
    f"Sweeping {len(producible)} producible goods across 4 configurations "
    f"(normalized value = {NORMALIZED_VALUE})\n"
)

templates = (
    (
        "era_2_construction",
        Scenario(
            name="era_2_construction",
            objective="construction_cost",
            banned_building_groups=DEFAULT_BANNED_BGS,
            era_cap=2,
        ),
        "",
    ),
    (
        "era_3_construction",
        Scenario(
            name="era_3_construction",
            objective="construction_cost",
            banned_building_groups=DEFAULT_BANNED_BGS,
            era_cap=3,
        ),
        "",
    ),
    (
        "era_5_automation",
        Scenario(
            name="era_5_automation",
            objective="automation",
            banned_building_groups=DEFAULT_BANNED_BGS,
            era_cap=5,
        ),
        "",
    ),
    (
        "cangshulun",
        Scenario(
            name="cangshulun",
            objective="automation",
            banned_building_groups=DEFAULT_BANNED_BGS,
            era_cap=5,
            banned_pms=CANGSHULUN_BANNED_PMS,
            building_limits=CANGSHULUN_BUILDING_LIMITS,
        ),
        "cangshulun",
    ),
)

frames: list[pd.DataFrame] = []
for configuration, template, ban_config in templates:
    frame = sweep_supply_chains(
        economy,
        template,
        goods=producible,
        target_value=NORMALIZED_VALUE,
    ).summary
    frame.insert(1, "configuration", configuration)
    frame.insert(2, "ban_config", ban_config)
    frames.append(frame)

df = pd.concat(frames, ignore_index=True)

df.to_csv(TABLES_DIR / "supply_chain_sweep.csv", index=False)
