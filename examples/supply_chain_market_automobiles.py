"""Optimize an automobiles export supply chain using endogenous prices."""

import pandas as pd

from vic3_analysis import Economy, MarketOptimizer, Scenario
from vic3_analysis.analysis.economy import EconomyState

from __init__ import DEFAULT_BANNED_BGS, TABLES_DIR

AUTOMOBILE_EXPORTS = 100.0
EMPLOYMENT_CAP = 1_000_000.0
FIXED_COLUMNS = (
    "scenario",
    "goods",
    "objective",
    "ban_config",
    "production",
    "base_price",
    "annual_gdp",
    "employment",
    "gdp_per_capita",
    "construction_cost",
    "gdp_per_construction",
    "era_cap",
    "arable_land_consumption",
)


def main() -> EconomyState:
    """Solve and print the fixed-column automobile market metrics."""
    production = pd.read_csv(TABLES_DIR / "production_table.csv")
    goods = pd.read_csv(TABLES_DIR / "goods.csv")
    pop_types = pd.read_csv(TABLES_DIR / "pop_types.csv")
    economy = Economy(
        df_production=production,
        df_goods=goods,
        df_pop_types=pop_types,
    )
    scenario = Scenario(
        name="automobiles_market",
        produce=(("automobiles", AUTOMOBILE_EXPORTS),),
        objective="gdp_per_capita",
        import_limit=None,
        exports=(("automobiles", AUTOMOBILE_EXPORTS),),
        banned_building_groups=DEFAULT_BANNED_BGS,
        employment_cap=EMPLOYMENT_CAP,
    )
    state = MarketOptimizer(economy).solve(scenario)

    goods_index = economy.goods_index()
    annual_gdp = state.gdp(annual=True)
    employment = state.total_population
    construction_cost = economy.construction_cost(state)
    information: dict[str, object] = {
        "scenario": scenario.display_name(),
        "goods": "automobiles",
        "objective": scenario.objective,
        "ban_config": "default",
        "production": AUTOMOBILE_EXPORTS,
        "base_price": economy.base_prices()[goods_index.index("automobiles")],
        "annual_gdp": annual_gdp,
        "employment": employment,
        "gdp_per_capita": state.gdp_per_capita(annual=True),
        "construction_cost": construction_cost,
        "gdp_per_construction": (
            annual_gdp / construction_cost if construction_cost > 0 else 0.0
        ),
        "era_cap": scenario.era_cap,
        "arable_land_consumption": economy.arable_land_consumption(state),
    }
    for column in FIXED_COLUMNS:
        print(f"{column}: {information[column]}")
    return state


if __name__ == "__main__":
    main()
