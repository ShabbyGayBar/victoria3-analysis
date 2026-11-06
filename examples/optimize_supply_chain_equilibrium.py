# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Optimize GDP over saved era_5_automation supply-chain levels."""

import argparse
import logging
from copy import copy
from datetime import UTC, datetime
from pathlib import Path
from time import perf_counter

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
    from .optimize_equilibrium import _evaluate_start
else:
    from __init__ import (
        BUY_PACKAGES_DIR,
        DEFAULT_BANNED_BGS,
        PARSED_DIR,
        PRODUCTION_DIR,
        SUPPLY_CHAIN_EQUILIBRIUM_DIR,
        SUPPLY_CHAINS_DIR,
    )
    from optimize_equilibrium import _evaluate_start

from vic3_analysis import (
    Economy,
    EconomyState,
    Scenario,
    SupplyChainEquilibriumOptimizer,
    SupplyChainEquilibriumProblem,
)
from vic3_analysis.optimize.equilibrium import _is_feasible

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
    """Resume saved levels, reducing loss-making terminal producers' chains."""
    _validate_loss_reduction(loss_reduction)
    previous = _load_saved_levels(problem, directory)
    state = problem.evaluate(previous)
    print(f"Saved solution annual equilibrium GDP: {state.gdp(annual=True):,.2f}")
    return _adjust_levels(problem, previous, state, loss_reduction)


def _validate_loss_reduction(loss_reduction: float) -> None:
    """Validate reductions even when starting without a saved solution."""
    if not np.isfinite(loss_reduction) or not 0 <= loss_reduction < 1:
        raise ValueError("loss_reduction must be finite, at least 0 and less than 1.")


def _load_saved_levels(
    problem: SupplyChainEquilibriumProblem, directory: Path
) -> np.ndarray:
    """Align saved levels and require exactly the current recipe matrix."""
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
    if not _is_feasible(problem, previous):
        raise ValueError(
            "Saved chain levels must satisfy current scenario constraints."
        )
    return previous


def _adjust_levels(
    problem: SupplyChainEquilibriumProblem,
    previous: np.ndarray,
    state: EconomyState,
    loss_reduction: float,
) -> tuple[np.ndarray, pd.DataFrame]:
    """Reduce chains with terminal-producer operating losses, without rescaling.

    Include coproduct revenue and retain the existing absolute/relative loss
    tolerance. Upstream profits do not hide terminal-producer losses.
    """
    _validate_loss_reduction(loss_reduction)
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
    for good in np.asarray(problem.chain_index)[losses & (loss_reduction > 0)]:
        print(f"Reducing {good} starting chain level by {loss_reduction:.0%}")
    return initial, details


def _baseline_summary(
    template: pd.DataFrame, problem: SupplyChainEquilibriumProblem, state: EconomyState
) -> pd.DataFrame:
    """Reuse scenario metadata while reporting a re-evaluated saved baseline.

    The baseline is not a local search, so its search diagnostics are empty.
    No optimizer internals or old summary files are needed to report it.
    """
    diagnostics = state.equilibrium_diagnostics
    if diagnostics is None:
        raise RuntimeError("Saved equilibrium did not retain diagnostics.")
    model = problem.economy
    return template.assign(
        iteration=0,
        initialization="saved_solution",
        loss_reduction=0.0,
        reduced_chain_count=0,
        gdp_weekly=state.gdp_weekly,
        annual_gdp=state.gdp(annual=True),
        employment=state.total_employment,
        population=state.total_population,
        gdp_per_capita=state.gdp_per_capita(annual=True),
        average_wealth=state.average_wealth,
        construction_cost=model.construction_cost(state),
        arable_land_consumption=model.arable_land_consumption(state),
        net_infrastructure_usage=float(
            state.building_levels @ model.infrastructure_vector
        ),
        initial_average_wealth=state.average_wealth,
        initial_gdp_weekly=state.gdp_weekly,
        initial_annual_gdp=state.gdp(annual=True),
        initial_equilibrium_status=diagnostics.status,
        gdp_weekly_change=np.nan,
        search_success=None,
        search_status=None,
        search_message=None,
        trial_evaluations=None,
        equilibrium_evaluations=None,
        failed_equilibrium_evaluations=None,
        equilibrium_status=diagnostics.status,
        equilibrium_iterations=diagnostics.iterations,
        loss_buildings_count=len(diagnostics.loss_buildings),
        unaffordable_floor_cells_count=len(diagnostics.unaffordable_floor_cells),
    )


def run(
    max_evaluations: int = 20_000,
    *,
    log_every: int = 100,
    resume: bool = False,
    subsidize_operating_losses: bool = True,
    loss_reduction: float = 0.5,
    max_iterations: int | None = None,
) -> tuple[Economy, EconomyState]:
    """Repeat local searches until GDP decreases, exporting only the best state.

    Each search gets ``max_evaluations`` trials. Equal GDP continues; an optional
    ``max_iterations`` bounds the number of local searches on plateaus.
    ``subsidize_operating_losses`` enables income-tax-funded operating losses
    for every evaluation, including saved baselines and restarts.
    """
    if max_iterations is not None and (
        isinstance(max_iterations, (bool, np.bool_))
        or not isinstance(max_iterations, (int, np.integer))
        or max_iterations <= 0
    ):
        raise ValueError("max_iterations must be a positive integer or None.")
    _validate_loss_reduction(loss_reduction)
    started_at = datetime.now(UTC).isoformat()
    started = perf_counter()
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
        min_net_infrastructure=None,
        min_goods_balance=None,
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
    problem = optimizer.compile(
        scenario, subsidize_operating_losses=subsidize_operating_losses
    )
    best_state: EconomyState | None = None
    best_levels: np.ndarray | None = None
    best_iteration = 0
    previous_gdp: float | None = None
    history: list[pd.DataFrame] = []
    if resume:
        saved_levels = _load_saved_levels(problem, SUPPLY_CHAIN_EQUILIBRIUM_DIR)
        saved_state = _evaluate_start(problem, saved_levels)
        if saved_state is None:
            initial = saved_levels.copy()
            chains["previous_level"] = saved_levels
            chains["previous_terminal_surplus"] = np.nan
            reduced_count = 0
        else:
            best_state = copy(saved_state)
            best_levels = saved_levels.copy()
            previous_gdp = best_state.gdp_weekly
            initial, previous = _adjust_levels(
                problem, saved_levels, best_state, loss_reduction
            )
            for column in ("previous_level", "previous_terminal_surplus"):
                chains[column] = previous[column].to_numpy()
            reduced_count = int(
                np.count_nonzero(initial < previous["previous_level"].to_numpy())
            )
    else:
        initial = _initial_levels(optimizer)
        reduced_count = 0
    chains["initial_level"] = initial
    baseline_elapsed = perf_counter() - started
    iteration = 0
    total_trials = 0
    while True:
        iteration += 1
        iteration_started_at = datetime.now(UTC).isoformat()
        iteration_started = perf_counter()
        initial_state = _evaluate_start(problem, initial)
        print(
            f"Iteration {iteration} initial annual equilibrium GDP: "
            + (
                "unavailable"
                if initial_state is None
                else f"{initial_state.gdp(annual=True):,.2f}"
            )
        )
        state = optimizer.solve_problem(
            problem,
            x0=initial,
            options={"maxiter": max_evaluations},
            log_every=log_every,
        )
        result = optimizer.result
        if result is None or state.equilibrium_diagnostics is None:
            raise RuntimeError("Supply-chain optimizer did not retain diagnostics.")
        total_trials += int(result.nfev)
        row = optimizer.summary().assign(
            subsidize_operating_losses=subsidize_operating_losses,
            recipe_configuration="era_5_automation",
            max_evaluations=max_evaluations,
            iteration=iteration,
            initialization=(
                "previous_iteration"
                if iteration > 1
                else ("saved_solution" if resume else "equal_chains")
            ),
            loss_reduction=loss_reduction
            if iteration > 1 or (resume and best_state is not None)
            else 0.0,
            reduced_chain_count=reduced_count,
            initial_average_wealth=np.nan
            if initial_state is None
            else initial_state.average_wealth,
            initial_gdp_weekly=np.nan
            if initial_state is None
            else initial_state.gdp_weekly,
            initial_annual_gdp=np.nan
            if initial_state is None
            else initial_state.gdp(annual=True),
            initial_equilibrium_status="insufficient_income"
            if initial_state is None
            else "converged",
            gdp_weekly_change=(
                np.nan if previous_gdp is None else state.gdp_weekly - previous_gdp
            ),
            started_at_utc=iteration_started_at,
            elapsed_seconds=perf_counter() - iteration_started,
        )
        if iteration == 1 and best_state is not None:
            history.append(
                _baseline_summary(row, problem, best_state).assign(
                    started_at_utc=started_at, elapsed_seconds=baseline_elapsed
                )
            )
        history.append(row)
        if best_state is None or state.gdp_weekly > best_state.gdp_weekly:
            # Frozen components and diagnostics can be shared. A shallow copy
            # preserves their read-only arrays while detaching the snapshot.
            best_state = copy(state)
            best_levels = np.array(result.x, dtype=float, copy=True)
            best_iteration = iteration
        print(
            f"Iteration {iteration} annual equilibrium GDP: {state.gdp(annual=True):,.2f}; "
            f"search success: {result.success}; trials: {result.nfev}"
        )
        if previous_gdp is not None and state.gdp_weekly < previous_gdp:
            stop_reason = "objective_worsened"
            break
        if max_iterations is not None and iteration >= max_iterations:
            stop_reason = "max_iterations"
            break
        previous_gdp = state.gdp_weekly
        initial, _ = _adjust_levels(problem, result.x, state, loss_reduction)
        reduced_count = int(np.count_nonzero(initial < result.x))

    if best_state is None or best_levels is None:
        raise RuntimeError("Supply-chain optimizer did not retain a best solution.")
    state = best_state
    chains["level"] = best_levels
    summary = pd.concat(history, ignore_index=True).assign(
        completed_iterations=iteration,
        total_trial_evaluations=total_trials,
        total_elapsed_seconds=perf_counter() - started,
        best_iteration=best_iteration,
        max_iterations=max_iterations,
        stop_reason=stop_reason,
    )
    summary["is_best"] = summary["iteration"] == best_iteration
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
    print(
        f"Best iteration: {best_iteration}; stopped: {stop_reason}; trials: {total_trials}"
    )
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
        "--subsidize-operating-losses",
        action=argparse.BooleanOptionalAction,
        default=True,
        help="Fund operating losses by taxing all household income proportionally (default: enabled); no payroll guarantee.",
    )
    parser.add_argument(
        "--loss-reduction",
        type=float,
        default=0.5,
        help="Fraction removed from loss-making chains before each restart (default: 0.5).",
    )
    parser.add_argument(
        "--max-evaluations",
        type=int,
        default=20_000,
        help="Hard trial budget per local search (default: 20000).",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum local searches; omitted means continue until GDP decreases.",
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
    if args.max_iterations is not None and args.max_iterations <= 0:
        parser.error("--max-iterations must be positive")
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
        subsidize_operating_losses=args.subsidize_operating_losses,
        loss_reduction=args.loss_reduction,
        max_iterations=args.max_iterations,
    )


if __name__ == "__main__":
    main()
