# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

import pandas as pd
from __init__ import FIGURES_DIR, TABLES_DIR

from vic3_analysis import Economy, Scenario, SupplyChainAnalyzer

df_production_table = pd.read_csv(TABLES_DIR / "production_table.csv")
df_goods = pd.read_csv(TABLES_DIR / "goods.csv")
df_pop_types = pd.read_csv(TABLES_DIR / "pop_types.csv")


def run_supply_chain_trace():
    economy = Economy(
        df_production=df_production_table, df_goods=df_goods, df_pop_types=df_pop_types
    )

    scenario = Scenario(
        produce=(("automobiles", 1.0),),
        objective="automation",
        name="automobiles",
    )
    result = SupplyChainAnalyzer(economy, scenario, "automobiles").run()

    print("=== Allowed automobiles supply-chain map ===")
    allowed_mermaid = result.to_mermaid(view="allowed")
    print(f"\n```mermaid\n{allowed_mermaid}\n```")
    recipe_path = FIGURES_DIR / "supply_chain_recipe.mmd"
    recipe_path.write_text(allowed_mermaid, encoding="utf-8")
    print(f"\nWritten to {recipe_path}")

    print("\n=== Realised trace (1 automobile/wk, autarky, max automation) ===")
    realised_mermaid = result.to_mermaid()
    print(f"\n```mermaid\n{realised_mermaid}\n```")
    realised_path = FIGURES_DIR / "supply_chain_realised.mmd"
    realised_path.write_text(realised_mermaid, encoding="utf-8")
    print(f"\nWritten to {realised_path}")


if __name__ == "__main__":
    run_supply_chain_trace()
