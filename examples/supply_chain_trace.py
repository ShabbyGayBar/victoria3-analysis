import pandas as pd

from vic3_analysis import Economy, Scenario, upstream_tree
from __init__ import THIS_DIR

df_production_table = pd.read_csv(THIS_DIR / ".." / "tables" / "production_table.csv")
df_goods = pd.read_csv(THIS_DIR / ".." / "tables" / "goods.csv")
df_pop_types = pd.read_csv(THIS_DIR / ".." / "tables" / "pop_types.csv")

FIGURES_DIR = THIS_DIR / ".." / "figures"


def run_supply_chain_trace():
    economy = Economy(
        df_production=df_production_table, df_goods=df_goods, df_pop_types=df_pop_types
    )

    print("=== Recipe trace: automobiles supply-chain map (all producers) ===")
    recipe = upstream_tree(economy, "automobiles")
    recipe_mermaid = recipe.to_mermaid(title="Recipe: automobiles (all producers)")
    print(f"\n```mermaid\n{recipe_mermaid}\n```")
    (FIGURES_DIR / "supply_chain_recipe.mmd").write_text(
        recipe_mermaid, encoding="utf-8"
    )
    print("\nWritten to figures/supply_chain_recipe.mmd")

    print("\n=== Realised trace (1 automobile/wk, autarky, max automation) ===")
    state = Scenario(
        terminal_good="automobiles",
        target_amount=1.0,
        objective="automation",
    ).optimize(economy)
    realised = upstream_tree(economy, "automobiles", state)
    realised_mermaid = realised.to_mermaid(
        realized=True, title="Realised: automobiles (1/wk, autarky)"
    )
    print(f"\n```mermaid\n{realised_mermaid}\n```")
    (FIGURES_DIR / "supply_chain_realised.mmd").write_text(
        realised_mermaid, encoding="utf-8"
    )
    print("\nWritten to figures/supply_chain_realised.mmd")


if __name__ == "__main__":
    run_supply_chain_trace()
