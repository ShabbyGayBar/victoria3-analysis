# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Saved-recipe loading, chain initialization, and exported matrix accounting."""

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from examples import DATASETS_DIR, PRODUCTION_DIR, SUPPLY_CHAIN_EQUILIBRIUM_DIR
from examples import optimize_supply_chain_equilibrium as example
from examples.optimize_supply_chain_equilibrium import (
    ALLOWED_CHAIN_GOODS,
    _adjust_levels,
    _initial_levels,
    _resume_levels,
    load_recipes,
)
from examples.supply_chain_compare import TEMPLATES, load_economy
from tests.test_equilibrium_optimizer import toy_economy
from vic3_analysis import (
    Economy,
    EconomyState,
    EquilibriumProblem,
    Scenario,
    SupplyChainEquilibriumOptimizer,
    sweep_supply_chains,
)

__all__ = ["toy_economy"]  # Re-export the shared pytest fixture.


def _reports(root: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    monkeypatch.setattr(example, "ALLOWED_CHAIN_GOODS", ("steel", "paper"))
    production = pd.DataFrame(
        {
            "building": ["mill", "mine", "unused"],
            "production_method": ["automatic", "pump", "manual"],
        }
    )
    path = root / "production.csv"
    production.to_csv(path, index=False, encoding="utf-8")
    pd.DataFrame(
        {
            "steel": [3.0, 1.0, 0.0],
            "paper": [1.0, 2.0, 0.0],
            "failed": [np.nan, np.nan, np.nan],
            "other": [0.0, 0.0, 5.0],
        },
        index=pd.Index(["mine+pump", "mill+automatic", "unused+manual"], name="config"),
    ).to_csv(root / "building_levels.csv", encoding="utf-8")
    return path


def test_loading_aligns_keys_preserves_order_and_supporting_processes(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    production_path = _reports(tmp_path, monkeypatch)
    assert not (tmp_path / "summary.csv").exists()
    production, matrix = load_recipes(production_path, tmp_path)
    assert production["building"].tolist() == ["mill", "mine"]
    expected = pd.DataFrame(
        {"steel": [1.0, 3.0], "paper": [2.0, 1.0]},
        index=pd.Index(["mill+automatic", "mine+pump"], name="config"),
    )
    pd.testing.assert_frame_equal(matrix, expected)
    np.testing.assert_array_equal(matrix.to_numpy() @ np.ones(2), [3, 4])
    report = tmp_path / "building_levels.csv"
    levels = pd.read_csv(report, index_col="config", encoding="utf-8")
    levels.iloc[::-1].to_csv(report, encoding="utf-8")
    _, reordered = load_recipes(production_path, tmp_path)
    pd.testing.assert_frame_equal(reordered, expected)


def test_initial_chain_levels_preserve_recipes_and_scale_workforce(
    toy_economy: Economy,
):
    recipes = pd.DataFrame(
        [[1.0, 0.0], [0.5, 2.0]], index=toy_economy.building_index, columns=["a", "b"]
    )
    optimizer = SupplyChainEquilibriumOptimizer(toy_economy, recipes)
    levels = _initial_levels(optimizer)
    assert levels[0] == levels[1]
    assert float(
        optimizer.to_building_levels(levels) @ toy_economy.employment_vector
    ) == pytest.approx(1_000_000)


def test_real_recipes_align_and_preserve_coefficients(tmp_path: Path):
    economy = load_economy(DATASETS_DIR)
    sweep = sweep_supply_chains(
        economy, TEMPLATES[1], goods=ALLOWED_CHAIN_GOODS, target_value=100_000.0
    )
    sweep.df_building_levels.to_csv(tmp_path / "building_levels.csv", encoding="utf-8")
    production, matrix = load_recipes(
        PRODUCTION_DIR / "production_table.csv",
        tmp_path,
    )
    assert matrix.shape == (len(production), len(ALLOWED_CHAIN_GOODS))
    assert tuple(matrix.columns) == ALLOWED_CHAIN_GOODS
    assert np.isfinite(matrix.to_numpy()).all()
    expected = sweep.df_building_levels
    expected = pd.DataFrame(expected.loc[(expected > 0).any(axis=1)])
    pd.testing.assert_frame_equal(matrix, expected)
    assert (
        matrix.index.tolist()
        == (production["building"] + "+" + production["production_method"]).tolist()
    )


def test_saved_matrix_and_chain_levels_reproduce_building_report():
    directory = SUPPLY_CHAIN_EQUILIBRIUM_DIR
    matrix = pd.read_csv(
        directory / "chain_matrix.csv", index_col="config", encoding="utf-8"
    )
    chains = pd.read_csv(directory / "chains.csv", encoding="utf-8").set_index("good")
    assert tuple(chains.index) == ALLOWED_CHAIN_GOODS
    buildings = pd.read_csv(directory / "buildings.csv", encoding="utf-8")
    summary = pd.read_csv(directory / "summary.csv", encoding="utf-8")
    levels = matrix.to_numpy() @ chains.loc[matrix.columns, "level"].to_numpy()
    expected = pd.Series(levels, index=matrix.index)
    keys = buildings["building"] + "+" + buildings["production_method"]
    np.testing.assert_allclose(
        buildings["level"].to_numpy(),
        expected.reindex(keys).to_numpy(),
        rtol=1e-12,
        atol=1e-10,
    )
    assert set(keys) == set(matrix.index[levels > 0])
    assert summary.loc[0, "chain_count"] == len(chains)
    assert summary.loc[0, "configuration_count"] == len(matrix)
    assert summary.loc[0, "equilibrium_status"] == "converged"
    assert summary.loc[0, "objective"] == "gdp"
    final_gdp, initial_gdp = summary[["gdp_weekly", "initial_gdp_weekly"]].to_numpy(
        dtype=float
    )[0]
    assert final_gdp >= initial_gdp


def test_selected_recipes_preserve_fixed_order_and_skip_other_columns(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    production = _reports(tmp_path, monkeypatch)
    monkeypatch.setattr(example, "ALLOWED_CHAIN_GOODS", ("paper", "steel"))
    _, matrix = load_recipes(production, tmp_path)
    assert matrix.columns.tolist() == ["paper", "steel"]
    np.testing.assert_array_equal(matrix.to_numpy(), [[2, 1], [1, 3]])


def test_loading_preserves_round_trip_coefficients(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch
):
    production = _reports(tmp_path, monkeypatch)
    path = tmp_path / "building_levels.csv"
    levels = pd.read_csv(path, index_col="config", encoding="utf-8")
    coefficient = 1.0000000000000002
    levels.loc["mill+automatic", "steel"] = coefficient
    levels.to_csv(path, encoding="utf-8")
    _, matrix = load_recipes(production, tmp_path)
    assert matrix.loc["mill+automatic", "steel"] == coefficient


def test_resume_reduces_terminal_losses_and_preserves_other_levels(
    tmp_path: Path, toy_economy: Economy
):
    production = toy_economy.df_production.copy()
    production["goods_food"] = [2.1, 0.0]
    production["goods_input"] = [-10.0, 3.0]
    model = replace(
        toy_economy,
        df_production=production,
        df_goods=pd.DataFrame({"key": ["food", "input"], "cost": [1.0, 1.0]}),
        df_buy_packages=toy_economy.df_buy_packages.iloc[:1].copy(),
    )
    recipes = pd.DataFrame(
        np.array([[1.0, 0.0], [0.0, 2.0]]),
        index=pd.Index(model.building_index, name="config"),
        columns=["food", "input"],
    )
    problem = SupplyChainEquilibriumOptimizer(model, recipes).compile(
        Scenario(objective="gdp", default_min_goods_output=None, employment_cap=50_000)
    )
    previous = np.array([0.5000000000000001, 0.7000000000000001])
    pd.DataFrame({"good": problem.chain_index, "level": previous}).iloc[::-1].to_csv(
        tmp_path / "chains.csv", index=False, encoding="utf-8"
    )
    matrix = recipes.copy(deep=True)
    matrix.iloc[::-1].to_csv(tmp_path / "chain_matrix.csv", encoding="utf-8")
    initial, details = _resume_levels(problem, tmp_path, 0.5)
    np.testing.assert_array_equal(details["previous_level"].to_numpy(), previous)
    np.testing.assert_array_equal(initial, previous * [0.5, 1.0])
    assert details["previous_terminal_surplus"].to_numpy()[0] < 0
    assert details["previous_terminal_surplus"].to_numpy()[1] > 0
    state = problem.evaluate(previous)
    adjusted, in_memory = _adjust_levels(problem, previous, state, 0.5)
    np.testing.assert_array_equal(adjusted, initial)
    pd.testing.assert_frame_equal(in_memory, details)
    np.testing.assert_array_equal(previous, [0.5000000000000001, 0.7000000000000001])
    unchanged, _ = _resume_levels(problem, tmp_path, 0.0)
    np.testing.assert_array_equal(unchanged, previous)
    pd.DataFrame({"good": ["food", "wrong"], "level": previous}).to_csv(
        tmp_path / "chains.csv", index=False, encoding="utf-8"
    )
    with pytest.raises(ValueError, match="goods must match"):
        _resume_levels(problem, tmp_path, 0.5)
    pd.DataFrame({"good": problem.chain_index, "level": previous}).to_csv(
        tmp_path / "chains.csv", index=False, encoding="utf-8"
    )
    matrix *= 2
    matrix.to_csv(tmp_path / "chain_matrix.csv", encoding="utf-8")
    with pytest.raises(ValueError, match="matrix must match"):
        _resume_levels(problem, tmp_path, 0.5)


@pytest.mark.parametrize("reduction", [1.0, -0.1, np.nan])
def test_resume_rejects_invalid_reductions(
    tmp_path: Path, toy_economy: Economy, reduction: float
):
    recipes = pd.DataFrame({"food": [1.0, 1.0]}, index=toy_economy.building_index)
    problem = SupplyChainEquilibriumOptimizer(toy_economy, recipes).compile(
        Scenario(objective="gdp")
    )
    with pytest.raises(ValueError, match="loss_reduction"):
        _resume_levels(problem, tmp_path, reduction)


@pytest.fixture
def example_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, toy_economy: Economy
) -> Path:
    """Supply the actual example with small deterministic input CSVs."""
    production = toy_economy.df_production.copy()
    production["infrastructure_usage_per_level"] = [0.0, -1.0]
    production.to_csv(tmp_path / "production_table.csv", index=False, encoding="utf-8")
    for name, table in (
        ("goods", toy_economy.df_goods),
        ("pop_types", toy_economy.df_pop_types),
        ("pop_needs", toy_economy.df_pop_needs),
        ("buy_packages", toy_economy.df_buy_packages),
    ):
        table.to_csv(tmp_path / f"{name}.csv", index=False, encoding="utf-8")
    recipes = tmp_path / "era_5_automation"
    recipes.mkdir()
    pd.DataFrame(
        {"food": [1.0, 2.0]},
        index=pd.Index(toy_economy.building_index, name="config"),
    ).to_csv(recipes / "building_levels.csv", encoding="utf-8")
    for constant in (
        "PRODUCTION_DIR",
        "PARSED_DIR",
        "BUY_PACKAGES_DIR",
        "SUPPLY_CHAINS_DIR",
    ):
        monkeypatch.setattr(example, constant, tmp_path)
    output = tmp_path / "output"
    monkeypatch.setattr(example, "SUPPLY_CHAIN_EQUILIBRIUM_DIR", output)
    monkeypatch.setattr(example, "ALLOWED_CHAIN_GOODS", ("food",))
    return output


@pytest.mark.parametrize(
    ("coproduct_price", "reduced"),
    [(1.0, True), (3.0, False), ((8.0 - 1e-9) / 4.0, False)],
)
def test_adjustment_includes_coproducts_and_respects_loss_tolerance(
    toy_economy: Economy, coproduct_price: float, reduced: bool
):
    production = toy_economy.df_production.copy()
    production["goods_food"] = [2.0, 0.0]
    production["goods_input"] = [-10.0, 20.0]
    production["goods_coproduct"] = [4.0, 0.0]
    model = replace(
        toy_economy,
        df_production=production,
        df_goods=pd.DataFrame(
            {"key": ["food", "input", "coproduct"], "cost": [1.0, 1.0, coproduct_price]}
        ),
    )
    optimizer = SupplyChainEquilibriumOptimizer(
        model, pd.DataFrame({"food": [1.0, 1.0]}, index=model.building_index)
    )
    problem = optimizer.compile(Scenario(objective="gdp"))
    previous = np.array([2.0])
    state = model.solve(problem.to_building_levels(previous))
    initial, details = _adjust_levels(problem, previous, state, 0.5)
    np.testing.assert_array_equal(initial, [1.0 if reduced else 2.0])
    np.testing.assert_array_equal(previous, [2.0])
    # Supporting input production is profitable in every case; only the
    # terminal producer's contribution determines this chain's adjustment.
    assert details["previous_terminal_surplus"].to_numpy()[0] == pytest.approx(
        2 * (2 - 10 + 4 * coproduct_price)
    )


@pytest.mark.parametrize(
    ("scales", "best_iteration", "stop_reason", "max_iterations"),
    [
        ([0.5, 0.75, 0.75, 0.9, 0.6], 4, "objective_worsened", None),
        ([0.5, 0.75, 0.75, 0.6], 2, "objective_worsened", None),
        ([0.5, 0.5, 0.5], 1, "max_iterations", 3),
        ([0.5, 0.75], 2, "max_iterations", 2),
    ],
)
def test_iteration_history_and_best_exports(
    example_output: Path,
    monkeypatch: pytest.MonkeyPatch,
    scales: list[float],
    best_iteration: int,
    stop_reason: str,
    max_iterations: int | None,
):
    """Use real verified equilibria at controlled local-search endpoints."""
    original_solve = SupplyChainEquilibriumOptimizer.solve_problem
    original_adjust = example._adjust_levels
    starts: list[np.ndarray] = []
    endpoints: list[np.ndarray] = []
    adjusted: list[np.ndarray] = []
    budgets: list[object] = []
    summaries: list[pd.DataFrame] = []

    def solve(
        self: SupplyChainEquilibriumOptimizer,
        problem: EquilibriumProblem,
        *,
        x0: np.ndarray | None = None,
        options: Mapping[str, object] | None = None,
        log_every: int = 100,
    ) -> EconomyState:
        assert x0 is not None and options is not None
        # No intermediate iteration exports may be visible.
        assert not example_output.exists()
        starts.append(x0.copy())
        budgets.append(options["maxiter"])
        endpoint = starts[0] * scales[len(starts) - 1]
        endpoints.append(endpoint.copy())
        state = original_solve(
            self, problem, x0=endpoint, options={"maxiter": 1}, log_every=log_every
        )
        summaries.append(self.summary())
        return state

    def adjust(
        problem: example.SupplyChainEquilibriumProblem,
        previous: np.ndarray,
        state: EconomyState,
        loss_reduction: float,
    ) -> tuple[np.ndarray, pd.DataFrame]:
        np.testing.assert_array_equal(previous, endpoints[-1])
        np.testing.assert_array_equal(
            state.building_levels, problem.to_building_levels(previous)
        )
        assert loss_reduction == 0.25
        levels, details = original_adjust(problem, previous, state, loss_reduction)
        adjusted.append(levels.copy())
        return levels, details

    monkeypatch.setattr(SupplyChainEquilibriumOptimizer, "solve_problem", solve)
    monkeypatch.setattr(example, "_adjust_levels", adjust)
    model, state = example.run(
        max_evaluations=7, max_iterations=max_iterations, loss_reduction=0.25
    )
    assert budgets == [7] * len(scales)
    for start, expected in zip(starts[1:], adjusted, strict=True):
        np.testing.assert_array_equal(start, expected)
    report = pd.read_csv(example_output / "summary.csv", encoding="utf-8")
    assert report["iteration"].tolist() == list(range(1, len(scales) + 1))
    assert report["is_best"].tolist() == [
        iteration == best_iteration for iteration in report["iteration"]
    ]
    assert report["initialization"].tolist() == ["equal_chains"] + [
        "previous_iteration"
    ] * (len(scales) - 1)
    assert report["loss_reduction"].tolist() == [0.0] + [0.25] * (len(scales) - 1)
    assert (report["stop_reason"] == stop_reason).all()
    assert (report["completed_iterations"] == len(scales)).all()
    assert (report["total_trial_evaluations"] == len(scales)).all()
    assert (report["best_iteration"] == best_iteration).all()
    assert (report["elapsed_seconds"] >= 0).all()
    assert (report["total_elapsed_seconds"] >= report["elapsed_seconds"].sum()).all()
    assert pd.to_datetime(report["started_at_utc"], utc=True).is_monotonic_increasing
    np.testing.assert_allclose(
        report["gdp_weekly_change"].to_numpy()[1:], np.diff(report["gdp_weekly"])
    )
    best = summaries[best_iteration - 1].iloc[0]
    assert state.gdp_weekly == best["gdp_weekly"]
    assert not state.building_levels.flags.writeable
    assert not state.market_prices.flags.writeable
    chains = pd.read_csv(example_output / "chains.csv", encoding="utf-8")
    np.testing.assert_allclose(chains["initial_level"], starts[0])
    np.testing.assert_allclose(chains["level"], endpoints[best_iteration - 1])
    matrix = pd.read_csv(example_output / "chain_matrix.csv", index_col="config")
    np.testing.assert_allclose(
        matrix.to_numpy() @ chains["level"], state.building_levels
    )
    for name, expected in (
        ("buildings", model.df_buildings(state)),
        ("market", model.df_market(state)),
        ("pop", model.df_pop(state)),
        ("goods_buy_packages", model.df_goods_buy_packages(state).reset_index()),
    ):
        actual = pd.read_csv(example_output / f"{name}.csv", encoding="utf-8")
        pd.testing.assert_frame_equal(actual, expected.reset_index(drop=True))


def test_resume_keeps_saved_best_and_records_worse_attempt(
    example_output: Path, monkeypatch: pytest.MonkeyPatch
):
    _, saved_state = example.run(max_evaluations=1, max_iterations=1)
    saved_chains = pd.read_csv(example_output / "chains.csv", encoding="utf-8")
    saved_files = {path.name: path.read_bytes() for path in example_output.iterdir()}
    original_solve = SupplyChainEquilibriumOptimizer.solve_problem

    def solve(
        self: SupplyChainEquilibriumOptimizer,
        problem: EquilibriumProblem,
        *,
        x0: np.ndarray | None = None,
        options: Mapping[str, object] | None = None,
        log_every: int = 100,
    ) -> EconomyState:
        assert x0 is not None
        assert {p.name: p.read_bytes() for p in example_output.iterdir()} == saved_files
        return original_solve(
            self, problem, x0=x0 * 0.5, options=options, log_every=log_every
        )

    monkeypatch.setattr(SupplyChainEquilibriumOptimizer, "solve_problem", solve)
    _, state = example.run(max_evaluations=1, resume=True, loss_reduction=0)
    assert state.gdp_weekly == saved_state.gdp_weekly
    report = pd.read_csv(example_output / "summary.csv", encoding="utf-8")
    assert report["iteration"].tolist() == [0, 1]
    assert report["is_best"].tolist() == [True, False]
    assert (report["stop_reason"] == "objective_worsened").all()
    assert report["gdp_weekly_change"].to_numpy(dtype=float)[1] < 0
    assert report.loc[0, "gdp_weekly"] == state.gdp_weekly
    assert report.loc[0, "average_wealth"] == state.average_wealth
    assert (
        report.loc[0, ["search_success", "trial_evaluations"]].isna().to_numpy().all()
    )
    chains = pd.read_csv(example_output / "chains.csv", encoding="utf-8")
    np.testing.assert_array_equal(chains["level"], saved_chains["level"])
    for name in ("buildings", "market", "pop", "goods_buy_packages"):
        assert (example_output / f"{name}.csv").read_bytes() == saved_files[
            f"{name}.csv"
        ]


def test_later_search_failure_preserves_existing_exports(
    example_output: Path, monkeypatch: pytest.MonkeyPatch
):
    example.run(max_evaluations=1, max_iterations=1)
    saved_files = {path.name: path.read_bytes() for path in example_output.iterdir()}
    original_solve = SupplyChainEquilibriumOptimizer.solve_problem
    calls = 0

    def solve(
        self: SupplyChainEquilibriumOptimizer,
        problem: EquilibriumProblem,
        *,
        x0: np.ndarray | None = None,
        options: Mapping[str, object] | None = None,
        log_every: int = 100,
    ) -> EconomyState:
        nonlocal calls
        calls += 1
        if calls == 2:
            raise ValueError("Invalid restart")
        return original_solve(
            self, problem, x0=x0, options=options, log_every=log_every
        )

    monkeypatch.setattr(SupplyChainEquilibriumOptimizer, "solve_problem", solve)
    with pytest.raises(ValueError, match="Invalid restart"):
        example.run(max_evaluations=1, max_iterations=2, resume=True)
    assert calls == 2
    assert {
        path.name: path.read_bytes() for path in example_output.iterdir()
    } == saved_files


def test_resume_rejects_infeasible_saved_baseline(example_output: Path):
    example.run(max_evaluations=1, max_iterations=1)
    path = example_output / "chains.csv"
    chains = pd.read_csv(path, encoding="utf-8")
    chains["level"] *= 2
    chains.to_csv(path, index=False, encoding="utf-8")
    saved_files = {path.name: path.read_bytes() for path in example_output.iterdir()}
    with pytest.raises(ValueError, match="Saved chain levels must satisfy"):
        example.run(max_evaluations=1, max_iterations=1, resume=True)
    assert {
        path.name: path.read_bytes() for path in example_output.iterdir()
    } == saved_files


@pytest.mark.parametrize("limit", [0, -1, 1.5, True, np.nan])
def test_invalid_iteration_limit(limit: int):
    with pytest.raises(ValueError, match="max_iterations"):
        example.run(max_iterations=limit)


@pytest.mark.parametrize("reduction", [-0.1, 1.0, np.nan])
def test_invalid_reduction_without_resume(reduction: float):
    with pytest.raises(ValueError, match="loss_reduction"):
        example.run(loss_reduction=reduction, max_iterations=1)


def test_cli_iteration_controls(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, object]] = []

    def run(max_evaluations: int, **kwargs: object) -> None:
        calls.append({"max_evaluations": max_evaluations, **kwargs})

    monkeypatch.setattr(example, "run", run)
    monkeypatch.setattr(
        "sys.argv", ["optimize", "--max-iterations", "3", "--loss-reduction", "0"]
    )
    example.main()
    assert calls[0]["max_iterations"] == 3
    assert calls[0]["loss_reduction"] == 0.0
    monkeypatch.setattr("sys.argv", ["optimize"])
    example.main()
    assert calls[1]["max_iterations"] is None
    monkeypatch.setattr("sys.argv", ["optimize", "--max-iterations", "0"])
    with pytest.raises(SystemExit) as error:
        example.main()
    assert error.value.code == 2
