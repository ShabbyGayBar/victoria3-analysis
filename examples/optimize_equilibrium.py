# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Search equilibrium GDP using production units from era_5_automation chains."""

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

if __package__:
    from . import (
        BUY_PACKAGES_DIR,
        DEFAULT_BANNED_BGS,
        EQUILIBRIUM_DIR,
        PARSED_DIR,
        PRODUCTION_DIR,
        SUPPLY_CHAINS_DIR,
    )
else:
    from __init__ import (
        BUY_PACKAGES_DIR,
        DEFAULT_BANNED_BGS,
        EQUILIBRIUM_DIR,
        PARSED_DIR,
        PRODUCTION_DIR,
        SUPPLY_CHAINS_DIR,
    )

from vic3_analysis import Economy, EconomyState, EquilibriumOptimizer, Scenario


def load_production_units(production_path: Path, analysis_dir: Path) -> pd.DataFrame:
    """Keep the union of active configurations in the saved supply-chain reports."""
    reports = sorted(analysis_dir.glob("*/processes.csv"))
    if not reports:
        raise FileNotFoundError(
            f"No supply-chain process reports found in {analysis_dir}. "
            "Run `uv run python -m examples.supply_chain_compare` first."
        )
    configs: set[str] = set()
    for path in reports:
        processes = pd.read_csv(
            path,
            usecols=["config", "active"],
            dtype={"config": str, "active": bool},
            encoding="utf-8",
        )
        configs.update(processes.loc[processes["active"].eq(True), "config"])
    if not configs:
        raise ValueError(f"No active production units found in {analysis_dir}.")

    production = pd.read_csv(production_path, encoding="utf-8")
    keys = production["building"] + "+" + production["production_method"]
    missing = configs.difference(keys)
    if missing:
        raise ValueError(
            "Supply-chain configurations missing from the production table: "
            + ", ".join(sorted(missing))
        )
    return pd.DataFrame(production.loc[keys.isin(configs)]).reset_index(drop=True)


def _initial_levels(economy: Economy) -> np.ndarray:
    """Supply enough infrastructure in an allowed mix scaled to one million workers."""
    allowed = ~economy.df_production["building_group"].isin(DEFAULT_BANNED_BGS)
    levels = allowed.to_numpy(dtype=np.float64)
    infrastructure = economy.infrastructure_vector
    if float(levels @ infrastructure) > 0:
        suppliers = infrastructure < 0
        usage = float(levels[~suppliers] @ infrastructure[~suppliers])
        supply = -float(levels[suppliers] @ infrastructure[suppliers])
        if supply <= 0:
            raise ValueError(
                "The starting mix consumes infrastructure but has no active supplier."
            )
        levels[suppliers] *= usage / supply
    workers = float(levels @ economy.employment_vector)
    if not np.isfinite(workers) or workers <= 0:
        raise ValueError("The allowed configurations must employ workers.")
    levels *= 1_000_000 / workers
    return levels


def run(
    max_evaluations: int = 20_000, *, log_every: int = 100
) -> tuple[Economy, EconomyState]:
    """Optimize, export the verified result, and return its model and state.

    A budget-limited search still writes its best verified equilibrium. Model
    errors and searches without a feasible converged state propagate to callers.
    Callers configure logging; this function does not install handlers.
    """
    economy = Economy(
        df_production=load_production_units(
            PRODUCTION_DIR / "production_table.csv",
            SUPPLY_CHAINS_DIR / "era_5_automation",
        ),
        df_goods=pd.read_csv(PARSED_DIR / "goods.csv"),
        df_pop_types=pd.read_csv(PARSED_DIR / "pop_types.csv"),
        df_pop_needs=pd.read_csv(PARSED_DIR / "pop_needs.csv"),
        df_buy_packages=pd.read_csv(BUY_PACKAGES_DIR / "buy_packages.csv"),
    )
    scenario = Scenario(
        objective="average_wealth",
        employment_cap=1_000_000,
        workforce_ratio=0.4,
        banned_building_groups=DEFAULT_BANNED_BGS,
        min_net_infrastructure=0.0,
        default_min_goods_output=None,
        throughput_multipliers=(),
    )
    optimizer = EquilibriumOptimizer(economy)
    problem = optimizer.compile(scenario)

    # A broad seed supplies consumption goods as well as industrial inputs.
    # Increase infrastructure suppliers if needed, then scale to the worker cap.
    levels = _initial_levels(economy)
    initial_state = problem.evaluate(levels)
    print(f"Initial annual equilibrium GDP: {initial_state.gdp(annual=True):,.2f}")

    # Fixed multipliers are all 1.0; level-dependent economy of scale is also
    # disabled by the optimizer. No trade, resource, land, or era caps are added.
    state = optimizer.solve_problem(
        problem, x0=levels, options={"maxiter": max_evaluations}, log_every=log_every
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
                "min_net_infrastructure": scenario.min_net_infrastructure,
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
    reports = {
        "summary": summary,
        "buildings": economy.df_buildings(state),
        "market": economy.df_market(state),
        "pop": economy.df_pop(state),
        "goods_buy_packages": economy.df_goods_buy_packages(state).reset_index(),
    }
    EQUILIBRIUM_DIR.mkdir(parents=True, exist_ok=True)
    for name, report in reports.items():
        report.to_csv(EQUILIBRIUM_DIR / f"{name}.csv", index=False, encoding="utf-8")
    print(f"Best annual equilibrium GDP found: {state.gdp(annual=True):,.2f}")
    print(
        f"Workers: {state.total_employment:,.2f}; population: {state.total_population:,.2f}"
    )
    print(f"Search success: {result.success}; {result.message}")
    print(f"Household equilibrium: {diagnostics.status}; trials: {result.nfev}")
    for name in reports:
        print(f"Saved {EQUILIBRIUM_DIR / f'{name}.csv'}")
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
    parser.add_argument(
        "--log-every",
        type=int,
        default=100,
        help="Emit an INFO progress summary every N trials (default: 100).",
    )
    parser.add_argument(
        "--log-level",
        choices=("WARNING", "INFO", "DEBUG"),
        default="INFO",
        help="Progress verbosity; DEBUG includes individual trials (default: INFO).",
    )
    args = parser.parse_args()
    if args.max_evaluations <= 0:
        parser.error("--max-evaluations must be positive")
    if args.log_every <= 0:
        parser.error("--log-every must be positive")
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run(args.max_evaluations, log_every=args.log_every)


if __name__ == "__main__":
    main()
