import pandas as pd

from vic3_analysis import Economy, Scenario, compare_scenarios
from __init__ import (
    CANGSHULUN_BANNED_PMS,
    CANGSHULUN_BUILDING_LIMITS,
    DEFAULT_BANNED_BGS,
    TABLES_DIR,
)

df_production_table = pd.read_csv(TABLES_DIR / "production_table.csv")
df_goods = pd.read_csv(TABLES_DIR / "goods.csv")
df_pop_types = pd.read_csv(TABLES_DIR / "pop_types.csv")

NORMALIZED_VALUE = 100000.0


economy = Economy(
    df_production=df_production_table, df_goods=df_goods, df_pop_types=df_pop_types
)
goods_index = economy.goods_index()
prices = economy.base_prices()
price_map = dict(zip(goods_index, prices))

producible = economy.producible_goods()
print(
    f"Sweeping {len(producible)} producible goods across 4 configurations "
    f"(normalized value = {NORMALIZED_VALUE})\n"
)

scenarios: list[Scenario] = []
for good in producible:
    target = NORMALIZED_VALUE / price_map[good]
    scenarios.extend(
        (
            Scenario(
                name=good,
                produce=((good, target),),
                objective="construction_cost",
                banned_building_groups=DEFAULT_BANNED_BGS,
                import_limit=0.0,
            ),
            Scenario(
                name=good,
                produce=((good, target),),
                objective="automation",
                banned_building_groups=DEFAULT_BANNED_BGS,
                import_limit=0.0,
            ),
            Scenario(
                name=good,
                produce=((good, target),),
                objective="construction_cost",
                banned_building_groups=DEFAULT_BANNED_BGS,
                import_limit=0.0,
                banned_pms=CANGSHULUN_BANNED_PMS,
                building_limits=CANGSHULUN_BUILDING_LIMITS,
            ),
            Scenario(
                name=good,
                produce=((good, target),),
                objective="automation",
                banned_building_groups=DEFAULT_BANNED_BGS,
                import_limit=0.0,
                banned_pms=CANGSHULUN_BANNED_PMS,
                building_limits=CANGSHULUN_BUILDING_LIMITS,
            ),
        )
    )

df = compare_scenarios(economy, scenarios)
ban_configs = [
    (
        "cangshulun"
        if scenario.banned_pms == CANGSHULUN_BANNED_PMS
        and scenario.building_limits == CANGSHULUN_BUILDING_LIMITS
        else ""
    )
    for scenario in scenarios
]
production = [scenario.produce[0][1] for scenario in scenarios]
df = df.drop(columns="produce").rename(columns={"name": "goods"})
df.insert(2, "ban_config", ban_configs)
df.insert(3, "production", production)
df = df.sort_values("gdp_per_capita", ascending=False).reset_index(drop=True)

df.to_csv(TABLES_DIR / "supply_chain_sweep.csv", index=False)
