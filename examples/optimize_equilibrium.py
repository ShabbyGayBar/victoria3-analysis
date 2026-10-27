# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Search equilibrium GDP with up to one million workers and a 40% workforce."""

import argparse

import numpy as np
import pandas as pd

if __package__:
    from . import (
        BUY_PACKAGES_DIR,
        DEFAULT_BANNED_BGS,
        EQUILIBRIUM_DIR,
        PARSED_DIR,
        PRODUCTION_DIR,
    )
else:
    from __init__ import (
        BUY_PACKAGES_DIR,
        DEFAULT_BANNED_BGS,
        EQUILIBRIUM_DIR,
        PARSED_DIR,
        PRODUCTION_DIR,
    )

from vic3_analysis import Economy, EconomyState, EquilibriumOptimizer, Scenario


def run(max_evaluations: int = 20_000) -> tuple[Economy, EconomyState]:
    """Optimize, export the verified result, and return its model and state.

    A budget-limited search still writes its best verified equilibrium. Model
    errors and searches without a feasible converged state propagate to callers.
    """
    economy = Economy(
        df_production=pd.read_csv(PRODUCTION_DIR / "production_table.csv"),
        df_goods=pd.read_csv(PARSED_DIR / "goods.csv"),
        df_pop_types=pd.read_csv(PARSED_DIR / "pop_types.csv"),
        df_pop_needs=pd.read_csv(PARSED_DIR / "pop_needs.csv"),
        df_buy_packages=pd.read_csv(BUY_PACKAGES_DIR / "buy_packages.csv"),
    )
    scenario = Scenario(
        objective="gdp",
        employment_cap=1_000_000,
        workforce_ratio=0.4,
        banned_building_groups=DEFAULT_BANNED_BGS,
        min_net_infrastructure_usage=0.0,
        default_min_goods_output=None,
        throughput_multipliers=(),
    )
    optimizer = EquilibriumOptimizer(economy)
    problem = optimizer.compile(scenario)

    # A broad seed supplies consumption goods as well as industrial inputs.
    # Equal allowed levels are scaled to the worker cap, excluding dependents.
    allowed = ~economy.df_production["building_group"].isin(DEFAULT_BANNED_BGS)
    levels = allowed.to_numpy(dtype=np.float64)
    workers = float(levels @ economy.employment_vector)
    if not np.isfinite(workers) or workers <= 0:
        raise ValueError("The allowed configurations must employ workers.")
    levels *= 1_000_000 / workers
    initial_state = problem.evaluate(levels)
    print(f"Initial annual equilibrium GDP: {initial_state.gdp(annual=True):,.2f}")

    # Fixed multipliers are all 1.0; level-dependent economy of scale is also
    # disabled by the optimizer. No trade, resource, land, or era caps are added.
    state = optimizer.solve_problem(
        problem, x0=levels, options={"maxiter": max_evaluations}
    )
    result = optimizer.result
    diagnostics = state.equilibrium_diagnostics
    if result is None or diagnostics is None:
        raise RuntimeError("The equilibrium optimizer did not retain diagnostics.")

    summary = pd.DataFrame(
        [
            {
                "objective": scenario.objective,
                "employment_cap": scenario.employment_cap,
                "workforce_ratio": scenario.workforce_ratio,
                "banned_building_groups": ";".join(scenario.banned_building_groups),
                "min_net_infrastructure_usage": scenario.min_net_infrastructure_usage,
                "default_min_goods_output": scenario.default_min_goods_output,
                "throughput_multiplier": 1.0,
                "economy_of_scale_level_cap": 0.0,
                "max_evaluations": max_evaluations,
                "initial_gdp_weekly": initial_state.gdp_weekly,
                "initial_annual_gdp": initial_state.gdp(annual=True),
                "gdp_weekly": state.gdp_weekly,
                "annual_gdp": state.gdp(annual=True),
                "employment": state.total_employment,
                "population": state.total_population,
                "gdp_per_capita": state.gdp_per_capita(annual=True),
                "average_wealth": state.average_wealth,
                "net_infrastructure_usage": float(
                    state.building_levels @ economy.infrastructure_vector
                ),
                "search_success": bool(result.success),
                "search_status": int(result.status),
                "search_message": str(result.message),
                "trial_evaluations": int(result.nfev),
                "equilibrium_evaluations": int(result.equilibrium_evaluations),
                "failed_equilibrium_evaluations": sum(
                    result.equilibrium_failures.values()
                ),
                "equilibrium_status": diagnostics.status,
                "equilibrium_iterations": diagnostics.iterations,
                "loss_buildings_count": len(diagnostics.loss_buildings),
                "unaffordable_floor_cells_count": len(
                    diagnostics.unaffordable_floor_cells
                ),
            }
        ]
    )
    EQUILIBRIUM_DIR.mkdir(parents=True, exist_ok=True)
    summary.to_csv(EQUILIBRIUM_DIR / "summary.csv", index=False, encoding="utf-8")
    economy.df_buildings(state).to_csv(
        EQUILIBRIUM_DIR / "buildings.csv", index=False, encoding="utf-8"
    )
    print(f"Best annual equilibrium GDP found: {state.gdp(annual=True):,.2f}")
    print(
        f"Workers: {state.total_employment:,.2f}; population: {state.total_population:,.2f}"
    )
    print(f"Search success: {result.success}; {result.message}")
    print(f"Household equilibrium: {diagnostics.status}; trials: {result.nfev}")
    print(f"Saved {EQUILIBRIUM_DIR / 'summary.csv'}")
    print(f"Saved {EQUILIBRIUM_DIR / 'buildings.csv'}")
    return economy, state


def main() -> None:
    """Parse the optional hard evaluation budget and run the example."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--max-evaluations",
        type=int,
        default=20_000,
        help="Hard trial-evaluation budget (default: 20000).",
    )
    args = parser.parse_args()
    if args.max_evaluations <= 0:
        parser.error("--max-evaluations must be positive")
    run(args.max_evaluations)


if __name__ == "__main__":
    main()
