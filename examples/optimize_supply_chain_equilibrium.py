# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Optimize GDP over saved era_5_automation supply-chain levels."""

import argparse
import logging
from pathlib import Path

import numpy as np
import pandas as pd

if __package__:
    from . import (
        BUY_PACKAGES_DIR,
        DEFAULT_BANNED_BGS,
        PARSED_DIR,
        PRODUCTION_DIR,
        SUPPLY_CHAIN_EQUILIBRIUM_DIR,
        SUPPLY_CHAINS_DIR,
    )
else:
    from __init__ import (
        BUY_PACKAGES_DIR,
        DEFAULT_BANNED_BGS,
        PARSED_DIR,
        PRODUCTION_DIR,
        SUPPLY_CHAIN_EQUILIBRIUM_DIR,
        SUPPLY_CHAINS_DIR,
    )

from vic3_analysis import (
    Economy,
    EconomyState,
    Scenario,
    SupplyChainEquilibriumOptimizer,
    SupplyChainEquilibriumProblem,
)

ALLOWED_CHAIN_GOODS = (
    "clothes",
    "furniture",
    "groceries",
    "coal",
    "oil",
    "electricity",
    "glass",
    "services",
    "liquor",
    "tobacco",
    "opium",
    "wine",
    "tea",
    "coffee",
    "transportation",
    "automobiles",
    "luxury_clothes",
    "luxury_furniture",
    "porcelain",
    "small_arms",
)


def load_recipes(
    production_path: Path,
    analysis_dir: Path,
) -> tuple[pd.DataFrame, pd.DataFrame]:
    """Load trusted recipes in ALLOWED_CHAIN_GOODS order.

    The saved building-level matrix includes supporting processes outside the
    terminal graph. Units unused by all selected recipes are filtered out.
    Production-table order defines the matrix rows. Each saved recipe is one
    chain level; no coefficients are renormalized or inferred from graph edges.
    """
    production = pd.read_csv(production_path, encoding="utf-8")
    keys = production["building"] + "+" + production["production_method"]
    levels = pd.read_csv(
        analysis_dir / "building_levels.csv",
        encoding="utf-8",
        float_precision="round_trip",
        index_col="config",
    )
    matrix = levels.loc[keys, list(ALLOWED_CHAIN_GOODS)]
    used = (matrix > 0).any(axis=1).to_numpy()
    selected = pd.DataFrame(production.loc[used]).reset_index(drop=True)
    matrix = pd.DataFrame(matrix.loc[used])
    return selected, matrix


def _initial_levels(optimizer: SupplyChainEquilibriumOptimizer) -> np.ndarray:
    """Scale equal chain levels to one million workers, preserving recipes."""
    levels = np.ones(len(optimizer.chain_index), dtype=float)
    workers = float(
        optimizer.to_building_levels(levels) @ optimizer.model.employment_vector
    )
    if not np.isfinite(workers) or workers <= 0:
        raise ValueError("The initial chain mix must employ workers.")
    levels *= 1_000_000 / workers
    return levels


def _resume_levels(
    problem: SupplyChainEquilibriumProblem,
    directory: Path,
    loss_reduction: float,
) -> tuple[np.ndarray, pd.DataFrame]:
    """Resume saved levels, reducing loss-making terminal producers' chains.

    Profitability is the recipe-attributed operating surplus of configurations
    producing the terminal good, including their coproduct revenue. Upstream
    profits do not hide terminal-producer losses. Other chain levels are kept.
    """
    if not np.isfinite(loss_reduction) or not 0 <= loss_reduction < 1:
        raise ValueError("loss_reduction must be finite, at least 0 and less than 1.")
    saved = pd.read_csv(
        directory / "chains.csv", encoding="utf-8", float_precision="round_trip"
    )
    if not {"good", "level"}.issubset(saved.columns):
        raise ValueError("Saved chains must contain good and level columns.")
    if saved["good"].duplicated().any() or set(saved["good"]) != set(
        problem.chain_index
    ):
        raise ValueError("Saved chain goods must match the current recipes exactly.")
    previous = (
        saved.set_index("good")
        .loc[list(problem.chain_index), "level"]
        .to_numpy(dtype=float)
    )
    problem.to_building_levels(previous)
    matrix = pd.read_csv(
        directory / "chain_matrix.csv",
        encoding="utf-8",
        float_precision="round_trip",
        index_col="config",
    )
    if (
        not matrix.index.is_unique
        or set(matrix.index) != set(problem.economy.building_index)
        or set(matrix.columns) != set(problem.chain_index)
        or not np.array_equal(
            matrix.loc[
                list(problem.economy.building_index), list(problem.chain_index)
            ].to_numpy(dtype=float),
            problem.chain_matrix,
        )
    ):
        raise ValueError("Saved recipe matrix must match the current recipes exactly.")
    state = problem.evaluate(previous)
    prices = state.market_prices
    unit_surplus = problem.net_matrix @ prices
    unit_inputs = problem.input_matrix @ prices
    unit_outputs = problem.output_matrix @ prices
    surpluses = np.zeros(len(previous))
    losses = np.zeros(len(previous), dtype=bool)
    for column, good in enumerate(problem.chain_index):
        good_index = problem.economy.goods_index.index(good)
        producers = problem.net_matrix[:, good_index] > 0
        attributed = problem.chain_matrix[producers, column] * previous[column]
        surpluses[column] = attributed @ unit_surplus[producers]
        scale = max(
            float(attributed @ unit_inputs[producers]),
            float(attributed @ unit_outputs[producers]),
        )
        losses[column] = surpluses[column] < -(problem.atol + problem.rtol * scale)
    initial = previous.copy()
    initial[losses] *= 1 - loss_reduction
    details = pd.DataFrame(
        {"previous_level": previous, "previous_terminal_surplus": surpluses}
    )
    print(f"Saved solution annual equilibrium GDP: {state.gdp(annual=True):,.2f}")
    for good in np.asarray(problem.chain_index)[losses & (loss_reduction > 0)]:
        print(f"Reducing {good} starting chain level by {loss_reduction:.0%}")
    return initial, details


def run(
    max_evaluations: int = 20_000,
    *,
    log_every: int = 100,
    resume: bool = False,
    loss_reduction: float = 0.5,
) -> tuple[Economy, EconomyState]:
    """Search saved chain recipes and export the best verified equilibrium."""
    production, df_building_levels = load_recipes(
        PRODUCTION_DIR / "production_table.csv",
        SUPPLY_CHAINS_DIR / "era_5_automation",
    )
    economy = Economy(
        df_production=production,
        df_goods=pd.read_csv(PARSED_DIR / "goods.csv", encoding="utf-8"),
        df_pop_types=pd.read_csv(PARSED_DIR / "pop_types.csv", encoding="utf-8"),
        df_pop_needs=pd.read_csv(PARSED_DIR / "pop_needs.csv", encoding="utf-8"),
        df_buy_packages=pd.read_csv(
            BUY_PACKAGES_DIR / "buy_packages.csv", encoding="utf-8"
        ),
    )
    scenario = Scenario(
        objective="gdp",
        employment_cap=1_000_000,
        workforce_ratio=0.4,
        banned_building_groups=DEFAULT_BANNED_BGS,
        min_net_infrastructure=0.0,
        default_min_goods_output=None,
        throughput_multipliers=(),
    )
    optimizer = SupplyChainEquilibriumOptimizer(economy, df_building_levels)
    base_prices = pd.Series(economy.base_prices, index=economy.goods_index)
    chains = pd.DataFrame(
        {
            "good": optimizer.chain_index,
            "target_quantity": 100_000.0
            / base_prices.loc[list(optimizer.chain_index)].to_numpy(),
            "target_base_value": 100_000.0,
        }
    )
    problem = optimizer.compile(scenario)
    if resume:
        initial, previous = _resume_levels(
            problem, SUPPLY_CHAIN_EQUILIBRIUM_DIR, loss_reduction
        )
        for column in ("previous_level", "previous_terminal_surplus"):
            chains[column] = previous[column].to_numpy()
        reduced_count = int(
            np.count_nonzero(initial < previous["previous_level"].to_numpy())
        )
    else:
        initial = _initial_levels(optimizer)
        reduced_count = 0
    initial_state = problem.evaluate(initial)
    print(f"Initial annual equilibrium GDP: {initial_state.gdp(annual=True):,.2f}")
    state = optimizer.solve_problem(
        problem, x0=initial, options={"maxiter": max_evaluations}, log_every=log_every
    )
    result = optimizer.result
    diagnostics = state.equilibrium_diagnostics
    if result is None or diagnostics is None:
        raise RuntimeError("Supply-chain optimizer did not retain diagnostics.")
    chains["initial_level"] = initial
    chains["level"] = result.x
    summary = optimizer.summary().assign(
        recipe_configuration="era_5_automation",
        max_evaluations=max_evaluations,
        initialization="saved_solution" if resume else "equal_chains",
        loss_reduction=loss_reduction if resume else 0.0,
        reduced_chain_count=reduced_count,
        initial_average_wealth=initial_state.average_wealth,
        initial_gdp_weekly=initial_state.gdp_weekly,
        initial_annual_gdp=initial_state.gdp(annual=True),
    )
    reports = {
        "chain_matrix": optimizer.df_building_levels.reset_index(),
        "chains": chains,
        "buildings": economy.df_buildings(state),
        "market": economy.df_market(state),
        "pop": economy.df_pop(state),
        "goods_buy_packages": economy.df_goods_buy_packages(state).reset_index(),
        "summary": summary,
    }
    SUPPLY_CHAIN_EQUILIBRIUM_DIR.mkdir(parents=True, exist_ok=True)
    for name, report in reports.items():
        path = SUPPLY_CHAIN_EQUILIBRIUM_DIR / f"{name}.csv"
        report.to_csv(path, index=False, encoding="utf-8")
        print(f"Saved {path}")
    print(f"Best annual equilibrium GDP found: {state.gdp(annual=True):,.2f}")
    print(f"Search success: {result.success}; {result.message}")
    print(f"Household equilibrium: {diagnostics.status}; trials: {result.nfev}")
    return economy, state


def main() -> None:
    """Parse search budget and standard progress logging controls."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Start from saved chain levels, reducing loss-making terminal producers' chains.",
    )
    parser.add_argument(
        "--loss-reduction",
        type=float,
        default=0.5,
        help="Fraction to remove from loss-making chains when resuming; 0 keeps saved levels (default: 0.5).",
    )
    parser.add_argument(
        "--max-evaluations",
        type=int,
        default=20_000,
        help="Hard trial budget (default: 20000).",
    )
    parser.add_argument(
        "--log-every",
        type=int,
        default=100,
        help="Log an INFO summary every N trials (default: 100).",
    )
    parser.add_argument(
        "--log-level",
        choices=("WARNING", "INFO", "DEBUG"),
        default="INFO",
        help="Progress verbosity (default: INFO).",
    )
    args = parser.parse_args()
    if args.max_evaluations <= 0:
        parser.error("--max-evaluations must be positive")
    if args.log_every <= 0:
        parser.error("--log-every must be positive")
    if not np.isfinite(args.loss_reduction) or not 0 <= args.loss_reduction < 1:
        parser.error("--loss-reduction must be at least 0 and less than 1")
    logging.basicConfig(
        level=args.log_level, format="%(asctime)s %(levelname)s %(name)s %(message)s"
    )
    run(
        args.max_evaluations,
        log_every=args.log_every,
        resume=args.resume,
        loss_reduction=args.loss_reduction,
    )


if __name__ == "__main__":
    main()
