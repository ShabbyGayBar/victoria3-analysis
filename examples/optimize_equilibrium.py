# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Search equilibrium wealth using production units from era_5_automation chains."""

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

from vic3_analysis import (
    Economy,
    EconomyState,
    EquilibriumOptimizer,
    EquilibriumProblem,
    Scenario,
)
from vic3_analysis.optimize.equilibrium import _is_feasible, _metric


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
            usecols=["building", "production_method", "active"],
            dtype={"building": str, "production_method": str, "active": bool},
            encoding="utf-8",
        )
        keys = processes["building"] + "+" + processes["production_method"]
        configs.update(keys.loc[processes["active"].eq(True)])
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
    """Scale equal allowed configuration levels to one million workers."""
    allowed = ~economy.df_production["building_group"].isin(DEFAULT_BANNED_BGS)
    levels = allowed.to_numpy(dtype=np.float64)
    workers = float(levels @ economy.employment_vector)
    if not np.isfinite(workers) or workers <= 0:
        raise ValueError("The allowed configurations must employ workers.")
    levels *= 1_000_000 / workers
    return levels


def _validate_loss_reduction(loss_reduction: float) -> None:
    """Require a finite fractional reduction for profitability restarts."""
    if not np.isfinite(loss_reduction) or not 0 <= loss_reduction < 1:
        raise ValueError("loss_reduction must be finite, at least 0 and less than 1.")


def _adjust_levels(
    problem: EquilibriumProblem,
    previous: np.ndarray,
    state: EconomyState,
    loss_reduction: float,
) -> np.ndarray:
    """Reduce materially loss-making configurations without rescaling the mix.

    Operating surplus includes all output revenue, including coproducts, less
    input costs. Use the supply-chain example's absolute/relative tolerance.
    """
    _validate_loss_reduction(loss_reduction)
    inputs = previous * (problem.input_matrix @ state.market_prices)
    outputs = previous * (problem.output_matrix @ state.market_prices)
    surplus = previous * (problem.net_matrix @ state.market_prices)
    losses = surplus < -(problem.atol + problem.rtol * np.maximum(inputs, outputs))
    initial = previous.copy()
    initial[losses] *= 1 - loss_reduction
    for config in np.asarray(problem.economy.building_index)[
        losses & (loss_reduction > 0)
    ]:
        print(f"Reducing {config} starting level by {loss_reduction:.0%}")
    return initial


def _load_saved_levels(problem: EquilibriumProblem, directory: Path) -> np.ndarray:
    """Align the saved positive building rows, restoring omitted zeros."""
    saved = pd.read_csv(
        directory / "buildings.csv", encoding="utf-8", float_precision="round_trip"
    )
    if not {"building", "production_method", "level"}.issubset(saved.columns):
        raise ValueError(
            "Saved buildings must contain building, production_method and level columns."
        )
    keys = saved["building"] + "+" + saved["production_method"]
    if keys.duplicated().any() or not set(keys).issubset(
        problem.economy.building_index
    ):
        raise ValueError(
            "Saved building configurations must be unique and match current production units."
        )
    levels = (
        pd.Series(saved["level"].to_numpy(dtype=float), index=keys)
        .reindex(problem.economy.building_index, fill_value=0.0)
        .to_numpy(dtype=float)
    )
    if not np.isfinite(levels).all() or not _is_feasible(problem, levels):
        raise ValueError(
            "Saved building levels must be finite and satisfy current scenario constraints."
        )
    return levels


def _baseline_summary(
    template: pd.DataFrame, problem: EquilibriumProblem, state: EconomyState
) -> pd.DataFrame:
    """Report the re-evaluated saved state with empty local-search diagnostics."""
    diagnostics = state.equilibrium_diagnostics
    if diagnostics is None:
        raise RuntimeError("Saved equilibrium did not retain diagnostics.")
    model = problem.economy
    return template.assign(
        iteration=0,
        initialization="saved_solution",
        loss_reduction=0.0,
        reduced_configuration_count=0,
        objective_value=_metric(state, problem.scenario.objective),
        objective_change=np.nan,
        gdp_weekly_change=np.nan,
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
    loss_reduction: float = 0.5,
    max_iterations: int | None = None,
) -> tuple[Economy, EconomyState]:
    """Restart local searches until the objective decreases, exporting the best.

    Each local search gets ``max_evaluations`` trials. Equal objectives continue;
    ``max_iterations`` optionally limits completed searches. Errors propagate
    before any exports are overwritten. Callers configure logging.
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
    economy = Economy(
        df_production=load_production_units(
            PRODUCTION_DIR / "production_table.csv",
            SUPPLY_CHAINS_DIR / "era_5_automation",
        ),
        df_goods=pd.read_csv(PARSED_DIR / "goods.csv", encoding="utf-8"),
        df_pop_types=pd.read_csv(PARSED_DIR / "pop_types.csv", encoding="utf-8"),
        df_pop_needs=pd.read_csv(PARSED_DIR / "pop_needs.csv", encoding="utf-8"),
        df_buy_packages=pd.read_csv(
            BUY_PACKAGES_DIR / "buy_packages.csv", encoding="utf-8"
        ),
    )
    scenario = Scenario(
        objective="average_wealth",
        employment_cap=1_000_000,
        workforce_ratio=0.4,
        banned_building_groups=DEFAULT_BANNED_BGS,
        min_net_infrastructure=None,
        min_goods_balance=None,
        throughput_multipliers=(),
    )
    optimizer = EquilibriumOptimizer(economy)
    problem = optimizer.compile(scenario)

    best_state: EconomyState | None = None
    best_iteration = 0
    previous_value: float | None = None
    previous_gdp: float | None = None
    reduced_count = 0
    history: list[pd.DataFrame] = []
    if resume:
        saved_levels = _load_saved_levels(problem, EQUILIBRIUM_DIR)
        best_state = copy(problem.evaluate(saved_levels))
        previous_value = _metric(best_state, scenario.objective)
        previous_gdp = best_state.gdp_weekly
        levels = _adjust_levels(problem, saved_levels, best_state, loss_reduction)
        reduced_count = int(np.count_nonzero(levels < saved_levels))
    else:
        levels = _initial_levels(economy)
    baseline_elapsed = perf_counter() - started
    iteration = 0
    total_trials = 0
    while True:
        iteration += 1
        iteration_started_at = datetime.now(UTC).isoformat()
        iteration_started = perf_counter()
        initial_state = problem.evaluate(levels)
        print(
            f"Iteration {iteration} initial {scenario.objective}: "
            f"{_metric(initial_state, scenario.objective):,.12g}"
        )
        state = optimizer.solve_problem(
            problem,
            x0=levels,
            options={"maxiter": max_evaluations},
            log_every=log_every,
        )
        result = optimizer.result
        if result is None or state.equilibrium_diagnostics is None:
            raise RuntimeError("The equilibrium optimizer did not retain diagnostics.")
        value = _metric(state, scenario.objective)
        total_trials += int(result.nfev)
        row = optimizer.summary().assign(
            max_evaluations=max_evaluations,
            iteration=iteration,
            initialization=(
                "previous_iteration"
                if iteration > 1
                else ("saved_solution" if resume else "equal_configurations")
            ),
            loss_reduction=loss_reduction if resume or iteration > 1 else 0.0,
            reduced_configuration_count=reduced_count,
            initial_average_wealth=initial_state.average_wealth,
            initial_gdp_weekly=initial_state.gdp_weekly,
            initial_annual_gdp=initial_state.gdp(annual=True),
            objective_value=value,
            objective_change=np.nan
            if previous_value is None
            else value - previous_value,
            gdp_weekly_change=np.nan
            if previous_gdp is None
            else state.gdp_weekly - previous_gdp,
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
        if best_state is None or value > _metric(best_state, scenario.objective):
            # Share immutable components to preserve their read-only arrays.
            best_state = copy(state)
            best_iteration = iteration
        print(
            f"Iteration {iteration} {scenario.objective}: {value:,.12g}; "
            f"search success: {result.success}; trials: {result.nfev}"
        )
        if previous_value is not None and value < previous_value:
            stop_reason = "objective_worsened"
            break
        if max_iterations is not None and iteration >= max_iterations:
            stop_reason = "max_iterations"
            break
        previous_value = value
        previous_gdp = state.gdp_weekly
        levels = _adjust_levels(problem, result.x, state, loss_reduction)
        reduced_count = int(np.count_nonzero(levels < result.x))

    if best_state is None:
        raise RuntimeError("The equilibrium optimizer did not retain a best solution.")
    state = best_state
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
        "summary": summary,
        "buildings": economy.df_buildings(state),
        "market": economy.df_market(state),
        "pop": economy.df_pop(state),
        "goods_buy_packages": economy.df_goods_buy_packages(state).reset_index(),
    }
    EQUILIBRIUM_DIR.mkdir(parents=True, exist_ok=True)
    for name, report in reports.items():
        report.to_csv(EQUILIBRIUM_DIR / f"{name}.csv", index=False, encoding="utf-8")
    print(
        f"Best {scenario.objective} found: {_metric(state, scenario.objective):,.12g}"
    )
    print(f"Annual equilibrium GDP: {state.gdp(annual=True):,.2f}")
    print(
        f"Workers: {state.total_employment:,.2f}; population: {state.total_population:,.2f}"
    )
    print(
        f"Best iteration: {best_iteration}; stopped: {stop_reason}; trials: {total_trials}"
    )
    for name in reports:
        print(f"Saved {EQUILIBRIUM_DIR / f'{name}.csv'}")
    return economy, state


def main() -> None:
    """Parse per-search budgets, restart controls, and progress logging."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--resume",
        action="store_true",
        help="Start from saved building levels, reducing loss-making configurations.",
    )
    parser.add_argument(
        "--loss-reduction",
        type=float,
        default=0.5,
        help="Fraction removed from loss-making configurations before each restart (default: 0.5).",
    )
    parser.add_argument(
        "--max-iterations",
        type=int,
        default=None,
        help="Maximum local searches; omitted means continue until the objective decreases.",
    )
    parser.add_argument(
        "--max-evaluations",
        type=int,
        default=20_000,
        help="Hard trial-evaluation budget per local search (default: 20000).",
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
    if args.max_iterations is not None and args.max_iterations <= 0:
        parser.error("--max-iterations must be positive")
    if not np.isfinite(args.loss_reduction) or not 0 <= args.loss_reduction < 1:
        parser.error("--loss-reduction must be at least 0 and less than 1")
    if args.log_every <= 0:
        parser.error("--log-every must be positive")
    logging.basicConfig(
        level=args.log_level,
        format="%(asctime)s %(levelname)s %(name)s %(message)s",
    )
    run(
        args.max_evaluations,
        log_every=args.log_every,
        resume=args.resume,
        loss_reduction=args.loss_reduction,
        max_iterations=args.max_iterations,
    )


if __name__ == "__main__":
    main()
