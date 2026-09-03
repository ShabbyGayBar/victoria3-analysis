import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import pandas as pd

from vic3_analysis import Economy, Scenario, compare_scenarios
from __init__ import THIS_DIR

df_production_table = pd.read_csv(THIS_DIR / ".." / "tables" / "production_table.csv")
df_goods = pd.read_csv(THIS_DIR / ".." / "tables" / "goods.csv")
df_pop_types = pd.read_csv(THIS_DIR / ".." / "tables" / "pop_types.csv")

FIGURES_DIR = THIS_DIR / ".." / "figures"

NORMALIZED_VALUE = 100.0


def run_supply_chain_compare():
    economy = Economy(
        df_production=df_production_table, df_goods=df_goods, df_pop_types=df_pop_types
    )
    goods_index = economy.goods_index()
    prices = economy.base_prices()
    price_map = dict(zip(goods_index, prices))

    producible = economy.producible_goods()
    print(
        f"Sweeping {len(producible)} producible goods "
        f"(normalized value = {NORMALIZED_VALUE})\n"
    )

    scenarios = [
        Scenario(
            name=good,
            produce=((good, NORMALIZED_VALUE / price_map[good]),),
            objective="construction_cost",
            import_limit=0.0,
        )
        for good in producible
    ]

    df = compare_scenarios(economy, scenarios)
    df = df.sort_values("construction_cost", ascending=True).reset_index(drop=True)

    print("\n=== Supply Chain Sweep (sorted by construction_cost) ===")
    print(df.to_string(index=False))

    output_csv = THIS_DIR / ".." / "tables" / "supply_chain_sweep.csv"
    df.to_csv(output_csv, index=False)
    print("\nWritten to tables/supply_chain_sweep.csv")

    _save_sweep_charts(df)
    print("Saved figures/supply_chain_sweep_cost.png")
    print("Saved figures/supply_chain_sweep_efficiency.png")


def _save_sweep_charts(df: pd.DataFrame) -> None:
    ok = df[df["error"] == ""].copy()
    assert isinstance(ok, pd.DataFrame)

    fig, ax = plt.subplots(figsize=(12, max(8, len(ok) * 0.3)))
    ok_sorted = ok.sort_values("construction_cost", ascending=True)
    colors = [
        "#d62728" if c < 0 else "#1f77b4" for c in ok_sorted["bottleneck_marginal"]
    ]
    ax.barh(ok_sorted["name"], ok_sorted["construction_cost"], color=colors)
    ax.set_xlabel("Construction Cost (minimised)")
    ax.set_title(
        f"Supply Chain Sweep: Construction Cost by Terminal Good "
        f"(normalised value = {NORMALIZED_VALUE})"
    )
    fig.tight_layout()
    fig.savefig(str(FIGURES_DIR / "supply_chain_sweep_cost.png"), dpi=150)
    plt.close(fig)

    fig, ax = plt.subplots(figsize=(12, max(8, len(ok) * 0.3)))
    ok_sorted = ok.sort_values("gdp_per_construction", ascending=True)
    ax.barh(
        ok_sorted["name"],
        ok_sorted["gdp_per_construction"],
        color="darkorange",
    )
    ax.set_xlabel("GDP per Construction Cost")
    ax.set_title("Supply Chain Sweep: GDP Efficiency by Terminal Good")
    fig.tight_layout()
    fig.savefig(str(FIGURES_DIR / "supply_chain_sweep_efficiency.png"), dpi=150)
    plt.close(fig)


if __name__ == "__main__":
    run_supply_chain_compare()
