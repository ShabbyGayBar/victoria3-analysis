import numpy as np
import pandas as pd

from vic3_analysis import Economy, Scenario, build_optimizer
from __init__ import THIS_DIR

df_production_table = pd.read_csv(THIS_DIR / ".." / "tables" / "production_table.csv")
df_goods = pd.read_csv(THIS_DIR / ".." / "tables" / "goods.csv")
df_pop_types = pd.read_csv(THIS_DIR / ".." / "tables" / "pop_types.csv")

# Oil is reserved for mining and automobile manufacturing: every other
# oil-consuming production method is banned (mirrors cangshulun_1).
CANGSHULUN_BANNED_PMS = (
    "pm_vacuum_canning",
    "pm_vacuum_canning_principle_3",
    "pm_assembly_lines_building_furniture_manufactory",
    "pm_houseware_plastics",
    "pm_automatic_bottle_blowers",
    "pm_assembly_lines_building_tooling_workshop",
    "pm_nitrogen_fixation",
    "pm_diesel_engines",
    "pm_assembly_lines_building_motor_industry",
    "pm_bolt_action_rifles",
    "pm_assembly_lines_building_arms_industry",
    "pm_recoiled_barrels",
    "pm_assembly_lines_building_arms_industry",
    "pm_assembly_lines_building_munition_plant",
    "pm_compression_ignition_tractors",
    "pm_oil-fired_plant",
    "pm_chainsaws",
    "pm_modern_port",
    "pm_diesel_trains",
    "pm_diesel_trains_principle_transport_3",
)


def run_supply_chain_optimize():
    economy = Economy(
        df_production=df_production_table, df_goods=df_goods, df_pop_types=df_pop_types
    )
    scenario = Scenario(
        terminal_good="automobiles",
        target_amount=10e6 / 5200.0,
        objective="automation",
        autarky=True,
        banned_pms=CANGSHULUN_BANNED_PMS,
        banned_buildings=("building_dye_plantation",),
    )

    optimizer = build_optimizer(economy, scenario)
    state = optimizer.linprog()

    annual_gdp = float(np.dot(state.building_levels, optimizer.gdp_vector())) * 52
    employment = float(np.sum(state.pops))
    construction_cost = economy.construction_cost(state)
    gdp_per_capita = annual_gdp / employment if employment else float("inf")

    print(f"Optimal GDP: {annual_gdp}")
    print(f"Optimal Employment: {employment}")
    print(f"Optimal GDP per Capita: {gdp_per_capita}")
    print(f"Optimal Construction Cost: {construction_cost}")
    print(f"GDP per construction cost: {annual_gdp / construction_cost}")

    print("\nOptimal Building Levels:")
    print(economy.df_buildings(state))

    print("\nNet Goods Output:")
    net_goods = state.building_levels @ optimizer.goods_matrix
    for good, value in zip(optimizer.goods_index(), net_goods):
        if abs(value) > 1e-10:
            print(f"  {good}: {value}")


if __name__ == "__main__":
    run_supply_chain_optimize()
