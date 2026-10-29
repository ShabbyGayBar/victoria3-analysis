# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check the equilibrium example's production selection and feasible starting mix."""

from collections.abc import Mapping
from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from examples import DEFAULT_BANNED_BGS
from examples import optimize_equilibrium as example
from examples.optimize_equilibrium import (
    _adjust_levels,
    _initial_levels,
    _load_saved_levels,
    load_production_units,
)
from tests.test_equilibrium_optimizer import toy_economy
from vic3_analysis import (
    Economy,
    EconomyState,
    EquilibriumError,
    EquilibriumOptimizer,
    EquilibriumProblem,
    Scenario,
)

__all__ = ["toy_economy"]


@pytest.fixture(scope="module")
def seed_economy() -> Economy:
    return Economy(
        df_production=pd.DataFrame(
            {
                "building": ["consumer", "supplier_a", "supplier_b", "banned"],
                "production_method": ["pm"] * 4,
                "building_group": ["bg_industry"] * 3 + [DEFAULT_BANNED_BGS[0]],
                "goods_food": [1.0] * 4,
                "employment": [1.0, 2.0, 3.0, 4.0],
                "infrastructure_usage_per_level": [8.0, -2.0, -2.0, -100.0],
            }
        ),
        df_goods=pd.DataFrame({"key": ["food"], "cost": [1.0]}),
        df_pop_types=pd.DataFrame({"key": ["workers"], "start_quality_of_life": [1]}),
        df_pop_needs=pd.DataFrame(),
        df_buy_packages=pd.DataFrame(),
    )


@pytest.mark.parametrize(
    ("usage", "relative_levels"),
    [
        ([2.0, -2.0, -2.0, -100.0], [1.0, 1.0, 1.0, 0.0]),
        ([4.0, -2.0, -2.0, -100.0], [1.0, 1.0, 1.0, 0.0]),
        ([8.0, -2.0, -2.0, -100.0], [1.0, 1.0, 1.0, 0.0]),
        ([0.0, 0.0, 0.0, -100.0], [1.0, 1.0, 1.0, 0.0]),
    ],
)
def test_initial_levels_ignore_infrastructure_and_scale_employment(
    seed_economy: Economy, usage: list[float], relative_levels: list[float]
) -> None:
    production = seed_economy.df_production.copy()
    production["infrastructure_usage_per_level"] = usage
    model = replace(seed_economy, df_production=production)
    levels = _initial_levels(model)
    expected = np.array(relative_levels)
    expected *= 1_000_000 / float(expected @ model.employment_vector)
    np.testing.assert_allclose(levels, expected)
    assert float(levels @ model.employment_vector) == pytest.approx(1_000_000)
    assert levels[-1] == 0.0


def test_initial_levels_allow_consumption_without_active_supplier(
    seed_economy: Economy,
) -> None:
    production = seed_economy.df_production.copy()
    production["infrastructure_usage_per_level"] = [1.0, 0.0, 0.0, -100.0]
    model = replace(seed_economy, df_production=production)
    levels = _initial_levels(model)
    expected = np.array([1.0, 1.0, 1.0, 0.0])
    expected *= 1_000_000 / float(expected @ model.employment_vector)
    np.testing.assert_allclose(levels, expected)
    assert float(levels @ model.infrastructure_vector) > 0


def test_initial_levels_reject_empty_workforce(seed_economy: Economy) -> None:
    production = seed_economy.df_production.copy()
    production["employment"] = 0.0
    model = replace(seed_economy, df_production=production)
    with pytest.raises(ValueError, match="must employ workers"):
        _initial_levels(model)


def test_production_units_are_union_of_active_chain_configurations(
    tmp_path: Path,
) -> None:
    production = pd.DataFrame(
        {
            "building": ["mill", "mill", "mine", "farm"],
            "production_method": ["manual", "automatic", "pump", "tractor"],
            "employment": [100, 50, 30, 20],
        }
    )
    production_path = tmp_path / "production.csv"
    production.to_csv(production_path, index=False, encoding="utf-8")
    analysis_dir = tmp_path / "era_5_automation"
    for good, configs, active in (
        ("paper", ["mill+automatic", "mill+manual"], [True, False]),
        ("iron", ["mine+pump", "mill+automatic"], [True, True]),
    ):
        directory = analysis_dir / good
        directory.mkdir(parents=True)
        pd.DataFrame(
            {
                "building": [config.split("+", 1)[0] for config in configs],
                "production_method": [config.split("+", 1)[1] for config in configs],
                "active": active,
            }
        ).to_csv(directory / "processes.csv", index=False, encoding="utf-8")
    other = tmp_path / "era_3_construction" / "grain"
    other.mkdir(parents=True)
    pd.DataFrame(
        {"building": ["farm"], "production_method": ["tractor"], "active": [True]}
    ).to_csv(other / "processes.csv", index=False, encoding="utf-8")

    selected = load_production_units(production_path, analysis_dir)

    pd.testing.assert_frame_equal(
        selected, production.iloc[[1, 2]].reset_index(drop=True)
    )


def test_missing_process_reports(tmp_path: Path) -> None:
    with pytest.raises(FileNotFoundError, match="examples.supply_chain_compare"):
        load_production_units(tmp_path / "production.csv", tmp_path)


def test_no_active_production_units(tmp_path: Path) -> None:
    directory = tmp_path / "paper"
    directory.mkdir()
    pd.DataFrame(
        {"building": ["mill"], "production_method": ["manual"], "active": [False]}
    ).to_csv(directory / "processes.csv", index=False, encoding="utf-8")
    with pytest.raises(ValueError, match="No active production units"):
        load_production_units(tmp_path / "production.csv", tmp_path)


def test_stale_supply_chain_configuration(tmp_path: Path) -> None:
    directory = tmp_path / "paper"
    directory.mkdir()
    pd.DataFrame(
        {"building": ["mill"], "production_method": ["obsolete"], "active": [True]}
    ).to_csv(directory / "processes.csv", index=False, encoding="utf-8")
    production_path = tmp_path / "production.csv"
    pd.DataFrame({"building": ["mill"], "production_method": ["automatic"]}).to_csv(
        production_path, index=False, encoding="utf-8"
    )
    with pytest.raises(
        ValueError, match=r"missing from the production table: mill\+obsolete"
    ):
        load_production_units(production_path, tmp_path)


@pytest.fixture
def example_output(
    tmp_path: Path, monkeypatch: pytest.MonkeyPatch, toy_economy: Economy
) -> Path:
    """Prepare example CSV inputs for two configurations with different wealth."""
    production = toy_economy.df_production.copy()
    # Preserve the toy's two wealth tiers with the example's 40% workforce ratio.
    production["goods_food"] *= 2.5
    production["infrastructure_usage_per_level"] = [0.0, -1.0]
    production.to_csv(tmp_path / "production_table.csv", index=False, encoding="utf-8")
    for name, table in (
        ("goods", toy_economy.df_goods),
        ("pop_types", toy_economy.df_pop_types),
        ("pop_needs", toy_economy.df_pop_needs),
        ("buy_packages", toy_economy.df_buy_packages),
    ):
        table.to_csv(tmp_path / f"{name}.csv", index=False, encoding="utf-8")
    directory = tmp_path / "era_5_automation" / "food"
    directory.mkdir(parents=True)
    production.assign(active=True).to_csv(
        directory / "processes.csv", index=False, encoding="utf-8"
    )
    for constant in (
        "PRODUCTION_DIR",
        "PARSED_DIR",
        "BUY_PACKAGES_DIR",
        "SUPPLY_CHAINS_DIR",
    ):
        monkeypatch.setattr(example, constant, tmp_path)
    output = tmp_path / "output"
    monkeypatch.setattr(example, "EQUILIBRIUM_DIR", output)
    return output


@pytest.mark.parametrize(
    ("endpoints", "best_iteration", "max_iterations", "stop_reason"),
    [
        (
            [[30, 10], [10, 10], [10, 10], [2, 6], [10, 10]],
            4,
            None,
            "objective_worsened",
        ),
        ([[30, 10], [10, 10], [10, 10], [30, 10]], 2, None, "objective_worsened"),
        ([[10, 10], [10, 10], [10, 10]], 1, 3, "max_iterations"),
        ([[30, 10], [10, 10]], 2, 2, "max_iterations"),
    ],
)
def test_iteration_uses_wealth_and_exports_only_best(
    example_output: Path,
    monkeypatch: pytest.MonkeyPatch,
    endpoints: list[list[float]],
    best_iteration: int,
    max_iterations: int | None,
    stop_reason: str,
):
    """Control local endpoints while retaining real search verification/reporting."""
    original_solve = EquilibriumOptimizer.solve_problem
    original_adjust = example._adjust_levels
    starts: list[np.ndarray] = []
    adjusted: list[np.ndarray] = []
    budgets: list[object] = []

    def solve(
        self: EquilibriumOptimizer,
        problem: EquilibriumProblem,
        *,
        x0: np.ndarray | None = None,
        options: Mapping[str, object] | None = None,
        log_every: int = 100,
    ) -> EconomyState:
        assert x0 is not None and options is not None
        assert not example_output.exists()
        starts.append(x0.copy())
        budgets.append(options["maxiter"])
        return original_solve(
            self,
            problem,
            x0=np.array(endpoints[len(starts) - 1], dtype=float),
            options={"maxiter": 1},
            log_every=log_every,
        )

    def adjust(
        problem: EquilibriumProblem,
        previous: np.ndarray,
        state: EconomyState,
        loss_reduction: float,
    ) -> np.ndarray:
        np.testing.assert_array_equal(previous, endpoints[len(starts) - 1])
        np.testing.assert_array_equal(state.building_levels, previous)
        assert loss_reduction == 0.25
        levels = original_adjust(problem, previous, state, loss_reduction)
        adjusted.append(levels.copy())
        return levels

    monkeypatch.setattr(EquilibriumOptimizer, "solve_problem", solve)
    monkeypatch.setattr(example, "_adjust_levels", adjust)
    model, state = example.run(
        max_evaluations=7, max_iterations=max_iterations, loss_reduction=0.25
    )
    report = pd.read_csv(example_output / "summary.csv", encoding="utf-8")
    assert budgets == [7] * len(endpoints)
    for start, expected in zip(starts[1:], adjusted, strict=True):
        np.testing.assert_array_equal(start, expected)
    assert report["iteration"].tolist() == list(range(1, len(endpoints) + 1))
    assert report["is_best"].tolist() == [
        iteration == best_iteration for iteration in report["iteration"]
    ]
    assert (report["stop_reason"] == stop_reason).all()
    assert (report["completed_iterations"] == len(endpoints)).all()
    assert (report["total_trial_evaluations"] == len(endpoints)).all()
    assert (report["best_iteration"] == best_iteration).all()
    assert report["initialization"].tolist() == ["equal_configurations"] + [
        "previous_iteration"
    ] * (len(endpoints) - 1)
    assert report["loss_reduction"].tolist() == [0.0] + [0.25] * (len(endpoints) - 1)
    np.testing.assert_allclose(report["objective_value"], report["average_wealth"])
    np.testing.assert_allclose(
        report["objective_change"].to_numpy()[1:], np.diff(report["objective_value"])
    )
    assert report["objective_change"].isna().iloc[0]
    assert (report["elapsed_seconds"] >= 0).all()
    assert (report["total_elapsed_seconds"] >= report["elapsed_seconds"].sum()).all()
    assert pd.to_datetime(report["started_at_utc"], utc=True).is_monotonic_increasing
    np.testing.assert_array_equal(state.building_levels, endpoints[best_iteration - 1])
    assert not state.building_levels.flags.writeable
    assert not state.market_prices.flags.writeable
    if endpoints[0] == [30, 10]:
        # Wealth improves even though GDP falls; the loop must continue.
        assert report["gdp_weekly_change"].to_numpy(dtype=float)[1] < 0
        assert report["objective_change"].to_numpy(dtype=float)[1] > 0
    if best_iteration == 4:
        # The stopping result has higher GDP and lower wealth than the best.
        assert report["gdp_weekly_change"].to_numpy(dtype=float)[-1] > 0
        assert report["objective_change"].to_numpy(dtype=float)[-1] < 0
    for name, expected in (
        ("buildings", model.df_buildings(state)),
        ("market", model.df_market(state)),
        ("pop", model.df_pop(state)),
        ("goods_buy_packages", model.df_goods_buy_packages(state).reset_index()),
    ):
        actual = pd.read_csv(example_output / f"{name}.csv", encoding="utf-8")
        pd.testing.assert_frame_equal(actual, expected.reset_index(drop=True))


def test_resume_preserves_saved_best(
    example_output: Path, monkeypatch: pytest.MonkeyPatch
):
    monkeypatch.setattr(
        example, "_initial_levels", lambda economy: np.array([1.0, 3.0])
    )
    _, saved_state = example.run(max_evaluations=1, max_iterations=1)
    saved_files = {path.name: path.read_bytes() for path in example_output.iterdir()}
    original_solve = EquilibriumOptimizer.solve_problem

    def solve(
        self: EquilibriumOptimizer,
        problem: EquilibriumProblem,
        *,
        x0: np.ndarray | None = None,
        options: Mapping[str, object] | None = None,
        log_every: int = 100,
    ) -> EconomyState:
        np.testing.assert_array_equal(x0, saved_state.building_levels)
        assert {p.name: p.read_bytes() for p in example_output.iterdir()} == saved_files
        return original_solve(
            self,
            problem,
            x0=np.array([30.0, 10.0]),
            options=options,
            log_every=log_every,
        )

    monkeypatch.setattr(EquilibriumOptimizer, "solve_problem", solve)
    _, state = example.run(max_evaluations=1, resume=True, loss_reduction=0)
    assert state.average_wealth == saved_state.average_wealth
    report = pd.read_csv(example_output / "summary.csv", encoding="utf-8")
    assert report["iteration"].tolist() == [0, 1]
    assert report["is_best"].tolist() == [True, False]
    assert report["stop_reason"].tolist() == ["objective_worsened"] * 2
    assert report["gdp_weekly_change"].to_numpy(dtype=float)[1] > 0
    assert report["objective_change"].to_numpy(dtype=float)[1] < 0
    assert report["objective_value"].to_numpy(dtype=float)[0] == state.average_wealth
    assert (
        report.loc[0, ["search_success", "trial_evaluations"]].isna().to_numpy().all()
    )
    for name, contents in saved_files.items():
        if name != "summary.csv":
            assert (example_output / name).read_bytes() == contents


@pytest.mark.parametrize(
    ("coproduct_price", "reduction", "expected"),
    [
        (1.0, 0.5, [1.0, 2.0]),
        (3.0, 0.5, [2.0, 2.0]),
        ((8.0 - 1e-9) / 4.0, 0.5, [2.0, 2.0]),
        (1.0, 0.0, [2.0, 2.0]),
    ],
)
def test_adjustment_uses_configuration_surplus_and_tolerance(
    toy_economy: Economy,
    coproduct_price: float,
    reduction: float,
    expected: list[float],
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
    problem = EquilibriumOptimizer(model).compile(Scenario(objective="average_wealth"))
    previous = np.array([2.0, 2.0])
    state = model.solve(previous)
    initial = _adjust_levels(problem, previous, state, reduction)
    np.testing.assert_array_equal(initial, expected)
    np.testing.assert_array_equal(previous, [2.0, 2.0])


def test_saved_levels_align_and_restore_zeros(tmp_path: Path, toy_economy: Economy):
    problem = EquilibriumOptimizer(toy_economy).compile(
        Scenario(objective="average_wealth")
    )
    pd.DataFrame(
        {
            "building": ["farm_b"],
            "production_method": ["pm_b"],
            "level": [0.30000000000000004],
        }
    ).to_csv(tmp_path / "buildings.csv", index=False, encoding="utf-8")
    np.testing.assert_array_equal(
        _load_saved_levels(problem, tmp_path), [0.0, 0.30000000000000004]
    )


@pytest.mark.parametrize(
    "kind", ["missing", "duplicate", "unknown", "negative", "nan", "infeasible"]
)
def test_saved_levels_reject_invalid_reports(
    tmp_path: Path, toy_economy: Economy, kind: str
):
    problem = EquilibriumOptimizer(toy_economy).compile(
        Scenario(objective="average_wealth", employment_cap=10_000)
    )
    saved = pd.DataFrame(
        {"building": ["farm_a"], "production_method": ["pm_a"], "level": [0.5]}
    )
    if kind == "missing":
        saved = saved.drop(columns="level")
    elif kind == "duplicate":
        saved = pd.concat([saved, saved], ignore_index=True)
    elif kind == "unknown":
        saved["building"] = "other"
    else:
        saved["level"] = {"negative": -0.1, "nan": np.nan, "infeasible": 2.0}[kind]
    saved.to_csv(tmp_path / "buildings.csv", index=False, encoding="utf-8")
    with pytest.raises(ValueError, match="Saved building"):
        _load_saved_levels(problem, tmp_path)


def test_later_failure_preserves_exports(
    example_output: Path, monkeypatch: pytest.MonkeyPatch
):
    example.run(max_evaluations=1, max_iterations=1)
    saved_files = {path.name: path.read_bytes() for path in example_output.iterdir()}
    original_solve = EquilibriumOptimizer.solve_problem
    calls = 0

    def solve(
        self: EquilibriumOptimizer,
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

    monkeypatch.setattr(EquilibriumOptimizer, "solve_problem", solve)
    with pytest.raises(ValueError, match="Invalid restart"):
        example.run(max_evaluations=1, max_iterations=2, resume=True)
    assert calls == 2
    assert {
        path.name: path.read_bytes() for path in example_output.iterdir()
    } == saved_files


@pytest.mark.parametrize("limit", [0, -1, 1.5, True, np.nan])
def test_invalid_iteration_limit(limit: int):
    with pytest.raises(ValueError, match="max_iterations"):
        example.run(max_iterations=limit)


@pytest.mark.parametrize("reduction", [-0.1, 1.0, np.nan])
def test_invalid_loss_reduction(reduction: float):
    with pytest.raises(ValueError, match="loss_reduction"):
        example.run(loss_reduction=reduction, max_iterations=1)


def test_cli_iteration_controls(monkeypatch: pytest.MonkeyPatch):
    calls: list[dict[str, object]] = []

    def run(max_evaluations: int, **kwargs: object) -> None:
        calls.append({"max_evaluations": max_evaluations, **kwargs})

    monkeypatch.setattr(example, "run", run)
    monkeypatch.setattr(
        "sys.argv",
        [
            "optimize",
            "--resume",
            "--subsidize-operating-losses",
            "--max-iterations",
            "3",
            "--loss-reduction",
            "0",
        ],
    )
    example.main()
    assert calls[0]["max_iterations"] == 3
    assert calls[0]["subsidize_operating_losses"] is True
    assert calls[0]["loss_reduction"] == 0.0
    assert calls[0]["resume"] is True
    monkeypatch.setattr("sys.argv", ["optimize"])
    example.main()
    assert calls[1]["max_iterations"] is None
    assert calls[1]["subsidize_operating_losses"] is True
    monkeypatch.setattr("sys.argv", ["optimize", "--no-subsidize-operating-losses"])
    example.main()
    assert calls[2]["subsidize_operating_losses"] is False
    assert calls[1]["loss_reduction"] == 0.5
    for args in (["--max-iterations", "0"], ["--loss-reduction", "1"]):
        monkeypatch.setattr("sys.argv", ["optimize", *args])
        with pytest.raises(SystemExit) as error:
            example.main()
        assert error.value.code == 2


@pytest.mark.parametrize("enabled", [False, True])
def test_operating_loss_policy_applies_to_resume_and_restarts(
    example_output: Path, enabled: bool
):
    production_path = example_output.parent / "production_table.csv"
    production = pd.read_csv(production_path, encoding="utf-8")
    production["goods_food"] = [5.25, -0.1]
    production.to_csv(production_path, index=False, encoding="utf-8")
    _, default_state = example.run(max_evaluations=1, max_iterations=1)
    assert default_state.context.subsidize_operating_losses
    assert default_state.pop_income_tax is not None
    assert default_state.pop_income_tax.sum() > 0
    # Save an unsubsidized mix, then re-evaluate it under the requested policy.
    example.run(max_evaluations=1, max_iterations=1, subsidize_operating_losses=False)
    model, state = example.run(
        max_evaluations=1,
        max_iterations=2,
        resume=True,
        loss_reduction=0,
        subsidize_operating_losses=enabled,
    )
    assert state.context.subsidize_operating_losses is enabled
    assert state.pop_income is not None
    assert state.pop_income_tax is not None
    assert state.building_deficit.sum() > 0
    assert state.pop_income_tax.sum() == pytest.approx(
        state.building_deficit.sum() if enabled else 0
    )
    np.testing.assert_allclose(state.pop_income, model.pop_income(state))
    report = pd.read_csv(example_output / "summary.csv", encoding="utf-8")
    assert report["iteration"].tolist() == [0, 1, 2]
    assert report["subsidize_operating_losses"].tolist() == [enabled] * 3


@pytest.mark.parametrize("resume", [False, True])
def test_unfundable_start_enters_search(example_output: Path, resume: bool):
    production_path = example_output.parent / "production_table.csv"
    production = pd.read_csv(production_path, encoding="utf-8")
    production["goods_food"] = [5.25, -6.0]
    production.to_csv(production_path, index=False, encoding="utf-8")
    if resume:
        example.run(
            max_evaluations=1, max_iterations=1, subsidize_operating_losses=False
        )
    model, state = example.run(max_evaluations=100, max_iterations=1, resume=resume)
    assert state.pop_income_tax is not None
    assert state.equilibrium_diagnostics is not None
    assert state.equilibrium_diagnostics.status == "converged"
    assert state.pop_income_tax.sum() == pytest.approx(state.building_deficit.sum())
    assert state.pop_income is not None
    np.testing.assert_allclose(state.pop_income, model.pop_income(state))
    report = pd.read_csv(example_output / "summary.csv", encoding="utf-8")
    # An unfunded saved mix is not eligible as an iteration-zero incumbent.
    assert report["iteration"].tolist() == [1]
    assert report.loc[0, "initial_equilibrium_status"] == "insufficient_income"
    assert (
        report.loc[
            0, ["initial_average_wealth", "initial_gdp_weekly", "initial_annual_gdp"]
        ]
        .isna()
        .to_numpy()
        .all()
    )
    assert report["failed_equilibrium_evaluations"].to_numpy()[0] > 0
    assert report.loc[0, "equilibrium_status"] == "converged"
    assert report.loc[0, "loss_reduction"] == 0


def test_unfundable_start_exhausts_budget_without_overwriting_exports(
    example_output: Path,
):
    production_path = example_output.parent / "production_table.csv"
    production = pd.read_csv(production_path, encoding="utf-8")
    production["goods_food"] = [-1.0, -2.0]
    production.to_csv(production_path, index=False, encoding="utf-8")
    example.run(max_evaluations=1, max_iterations=1, subsidize_operating_losses=False)
    before = {path.name: path.read_bytes() for path in example_output.iterdir()}
    with pytest.raises(
        ValueError, match="No feasible converged equilibrium.*maxiter=5"
    ):
        example.run(max_evaluations=5, max_iterations=1, resume=True)
    assert {path.name: path.read_bytes() for path in example_output.iterdir()} == before


def test_nonfunding_initial_error_still_propagates(
    toy_economy: Economy, monkeypatch: pytest.MonkeyPatch
):
    problem = EquilibriumOptimizer(toy_economy).compile(
        Scenario(objective="average_wealth")
    )
    state = problem.evaluate(np.ones(2))
    diagnostics = state.equilibrium_diagnostics
    assert diagnostics is not None
    error = EquilibriumError(
        "Cycle at initialization",
        replace(state, equilibrium_diagnostics=replace(diagnostics, status="cycle")),
    )

    def fail(self: EquilibriumProblem, levels: np.ndarray) -> EconomyState:
        raise error

    monkeypatch.setattr(EquilibriumProblem, "evaluate", fail)
    with pytest.raises(EquilibriumError) as caught:
        example._evaluate_start(problem, np.ones(2))
    assert caught.value is error
