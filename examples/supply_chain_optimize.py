import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt
import numpy as np
import pandas as pd

from vic3_analysis import (
    Economy,
    Scenario,
    bottleneck,
    build_optimizer,
    value_added_breakdown,
)
from __init__ import THIS_DIR

df_production_table = pd.read_csv(THIS_DIR / ".." / "tables" / "production_table.csv")
df_goods = pd.read_csv(THIS_DIR / ".." / "tables" / "goods.csv")
df_pop_types = pd.read_csv(THIS_DIR / ".." / "tables" / "pop_types.csv")

FIGURES_DIR = THIS_DIR / ".." / "figures"

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


def _save_building_levels(state, economy):
    df = economy.df_buildings(state)
    df = df.sort_values("level")
    fig, ax = plt.subplots(figsize=(10, max(6, len(df) * 0.35)))
    ax.barh(df["key"], df["level"], color="steelblue")
    ax.set_xlabel("Building Level")
    ax.set_title("Optimal Building Levels")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "building_levels.png", dpi=150)
    plt.close(fig)


def _save_net_goods(state, optimizer):
    net_goods = state.building_levels @ optimizer.goods_matrix
    goods_idx = optimizer.goods_index()
    pairs = [(g, float(v)) for g, v in zip(goods_idx, net_goods) if abs(v) > 1e-10]
    pairs.sort(key=lambda x: x[1])
    labels = [p[0] for p in pairs]
    values = [p[1] for p in pairs]
    colors = ["#2ca02c" if v > 0 else "#d62728" for v in values]
    fig, ax = plt.subplots(figsize=(10, max(6, len(pairs) * 0.35)))
    ax.barh(labels, values, color=colors)
    ax.set_xlabel("Net Goods Output (per week)")
    ax.set_title("Net Goods Output")
    ax.axvline(0, color="black", linewidth=0.5)
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "net_goods.png", dpi=150)
    plt.close(fig)


def _save_value_added(state, economy):
    df = value_added_breakdown(economy, state, by="good")
    df = df.sort_values("gdp")
    fig, ax = plt.subplots(figsize=(10, max(6, len(df) * 0.35)))
    ax.barh(df["good"], df["gdp"], color="darkorange")
    ax.set_xlabel("GDP (per week)")
    ax.set_title("Value-Added by Good")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "value_added.png", dpi=150)
    plt.close(fig)


def _save_bottleneck(state, economy, optimizer):
    df = bottleneck(economy, state, optimizer=optimizer)
    if df.empty:
        return
    df = df.sort_values("input_cost")
    colors = ["#d62728" if m < 0 else "#1f77b4" for m in df["import_marginal"]]
    fig, ax = plt.subplots(figsize=(10, max(6, len(df) * 0.35)))
    ax.barh(df["good"], df["input_cost"], color=colors)
    ax.set_xlabel("Input Cost (per week)")
    ax.set_title("Bottleneck: Input Cost by Good (red = binding import cap)")
    fig.tight_layout()
    fig.savefig(FIGURES_DIR / "bottleneck.png", dpi=150)
    plt.close(fig)


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

    _save_building_levels(state, economy)
    print("\nSaved figures/building_levels.png")
    _save_net_goods(state, optimizer)
    print("Saved figures/net_goods.png")
    _save_value_added(state, economy)
    print("Saved figures/value_added.png")
    _save_bottleneck(state, economy, optimizer)
    print("Saved figures/bottleneck.png")


if __name__ == "__main__":
    run_supply_chain_optimize()
