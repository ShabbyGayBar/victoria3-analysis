import pandas as pd

from vic3_analysis import Economy, Scenario, compare_scenarios
from __init__ import THIS_DIR

df_production_table = pd.read_csv(THIS_DIR / ".." / "tables" / "production_table.csv")
df_goods = pd.read_csv(THIS_DIR / ".." / "tables" / "goods.csv")
df_pop_types = pd.read_csv(THIS_DIR / ".." / "tables" / "pop_types.csv")


def run_supply_chain_compare():

    economy = Economy(
        df_production=df_production_table, df_goods=df_goods, df_pop_types=df_pop_types
    )
    scenarios = [
        Scenario(
            name="auto-automation",
            terminal_good="automobiles",
            target_amount=1.0,
            objective="automation",
            autarky=True,
        ),
        Scenario(
            name="auto-automation-bonus",
            terminal_good="automobiles",
            target_amount=1.0,
            objective="automation",
            autarky=True,
            throughput_bonuses=(("building_automotive_industry", 2.45),),
        ),
        Scenario(
            name="auto-min-construction",
            terminal_good="automobiles",
            target_amount=1.0,
            objective="construction_cost",
            autarky=True,
        ),
    ]
    df = compare_scenarios(economy, scenarios)
    print(df.to_string(index=False))


if __name__ == "__main__":
    run_supply_chain_compare()
