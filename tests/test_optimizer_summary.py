# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Optimizer reports use returned solutions and preserve example CSV fields."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from examples import optimize_equilibrium, optimize_supply_chain_equilibrium
from tests.test_equilibrium_optimizer import toy_economy
from vic3_analysis import (
    Economy,
    EconomyState,
    EquilibriumOptimizer,
    MarketOptimizer,
    NominalOptimizer,
    Scenario,
    SupplyChainEquilibriumOptimizer,
)

__all__ = ["toy_economy"]

type Optimizer = NominalOptimizer | MarketOptimizer | EquilibriumOptimizer

KINDS = ["nominal", "market", "equilibrium", "supply_chain"]
COMMON_COLUMNS = [
    "objective",
    "employment_cap",
    "workforce_ratio",
    "banned_building_groups",
    "min_net_infrastructure",
    "default_min_goods_output",
    "configuration_count",
    "throughput_multiplier",
    "economy_of_scale_level_cap",
    "gdp_weekly",
    "annual_gdp",
    "employment",
    "population",
    "gdp_per_capita",
    "average_wealth",
    "construction_cost",
    "arable_land_consumption",
    "net_infrastructure_usage",
    "search_success",
    "search_status",
    "search_message",
]
EQUILIBRIUM_COLUMNS = [
    "equilibrium_evaluations",
    "failed_equilibrium_evaluations",
    "equilibrium_status",
    "equilibrium_iterations",
    "loss_buildings_count",
    "unaffordable_floor_cells_count",
]


def _optimizer(model: Economy, kind: str) -> Optimizer:
    if kind == "nominal":
        return NominalOptimizer(model)
    if kind == "market":
        return MarketOptimizer(model)
    if kind == "equilibrium":
        return EquilibriumOptimizer(model)
    # One chain spanning two configurations catches coordinate mixups.
    recipes = pd.DataFrame({"food": [1.0, 2.0]}, index=model.building_index)
    return SupplyChainEquilibriumOptimizer(model, recipes)


def _solve(optimizer: Optimizer, scenario: Scenario, compiled: bool) -> EconomyState:
    if isinstance(optimizer, NominalOptimizer):
        return (
            optimizer.solve_problem(optimizer.compile(scenario))
            if compiled
            else optimizer.solve(scenario)
        )
    initial = (
        np.array([0.2])
        if isinstance(optimizer, SupplyChainEquilibriumOptimizer)
        else np.array([0.2, 0.4])
    )
    if isinstance(optimizer, MarketOptimizer):
        return (
            optimizer.solve_problem(optimizer.compile(scenario), x0=initial)
            if compiled
            else optimizer.solve(scenario, x0=initial)
        )
    options = {"maxiter": 1}
    return (
        optimizer.solve_problem(
            optimizer.compile(scenario), x0=initial, options=options
        )
        if compiled
        else optimizer.solve(scenario, x0=initial, options=options)
    )


@pytest.mark.parametrize("kind", KINDS)
@pytest.mark.parametrize("compiled", [False, True])
def test_summary_matches_returned_solution(
    toy_economy: Economy, kind: str, compiled: bool, monkeypatch: pytest.MonkeyPatch
) -> None:
    optimizer = _optimizer(toy_economy, kind)
    scenario = Scenario(
        objective="gdp",
        default_min_goods_output=None,
        employment_cap=10_000.0,
        workforce_ratio=0.4,
        banned_building_groups=() if kind == "market" else ("unused_a", "unused_b"),
        min_net_infrastructure=-1.0,
    )
    state = _solve(optimizer, scenario, compiled)
    result = optimizer.result
    assert result is not None

    def unexpected_solve(*args, **kwargs):
        pytest.fail("summary must not solve or evaluate the economy again")

    monkeypatch.setattr(Economy, "solve", unexpected_solve)
    report = optimizer.summary()
    columns = COMMON_COLUMNS.copy()
    if "nfev" in result:
        columns.append("trial_evaluations")
    if isinstance(optimizer, EquilibriumOptimizer):
        columns.extend(EQUILIBRIUM_COLUMNS)
    if isinstance(optimizer, SupplyChainEquilibriumOptimizer):
        columns.append("chain_count")
    assert report.shape == (1, len(columns))
    assert report.columns.tolist() == columns
    row = report.iloc[0]
    expected = {
        "employment_cap": 10_000.0,
        "workforce_ratio": 0.4,
        "min_net_infrastructure": -1.0,
        "configuration_count": 2,
        "throughput_multiplier": 1.0,
        "economy_of_scale_level_cap": 0.0,
        "gdp_weekly": state.gdp_weekly,
        "annual_gdp": state.gdp_weekly * 52,
        "employment": state.total_employment,
        "population": state.total_employment / 0.4,
        "gdp_per_capita": state.gdp_weekly * 52 / state.total_population,
        "average_wealth": state.average_wealth,
        "construction_cost": float(state.building_levels @ np.array([1.0, 2.0])),
        "arable_land_consumption": state.building_levels[0],
        "net_infrastructure_usage": float(state.building_levels.sum()),
    }
    for name, value in expected.items():
        assert row[name] == pytest.approx(value)
    assert row["objective"] == "gdp"
    assert row["default_min_goods_output"] is None
    assert row["banned_building_groups"] == ";".join(scenario.banned_building_groups)
    assert row["search_success"] == bool(result.success)
    assert row["search_status"] == int(result.status)
    assert row["search_message"] == str(result.message)
    if "nfev" in result:
        assert row["trial_evaluations"] == result.nfev
    if isinstance(optimizer, EquilibriumOptimizer):
        diagnostics = state.equilibrium_diagnostics
        assert diagnostics is not None
        assert not row["search_success"]  # Budget exhaustion still returns a state.
        assert row["equilibrium_status"] == "converged"
        assert row["equilibrium_iterations"] == diagnostics.iterations
        assert row["equilibrium_evaluations"] == result.equilibrium_evaluations
        assert row["failed_equilibrium_evaluations"] == sum(
            result.equilibrium_failures.values()
        )
        assert row["loss_buildings_count"] == len(diagnostics.loss_buildings)
        assert row["unaffordable_floor_cells_count"] == len(
            diagnostics.unaffordable_floor_cells
        )
    if isinstance(optimizer, SupplyChainEquilibriumOptimizer):
        assert row["chain_count"] == 1
    unchanged = report.copy(deep=True)
    report.loc[0, "annual_gdp"] = -1.0
    report["extra"] = "changed"
    pd.testing.assert_frame_equal(optimizer.summary(), unchanged)


@pytest.mark.parametrize("kind", KINDS)
def test_summary_solution_lifecycle(toy_economy: Economy, kind: str) -> None:
    optimizer = _optimizer(toy_economy, kind)
    scenario = Scenario(
        objective="gdp", default_min_goods_output=None, employment_cap=10_000.0
    )
    with pytest.raises(ValueError, match="no returned solution"):
        optimizer.summary()
    optimizer.compile(scenario)
    with pytest.raises(ValueError, match="no returned solution"):
        optimizer.summary()
    _solve(optimizer, scenario, compiled=False)
    optimizer.summary()
    optimizer.compile(scenario)
    with pytest.raises(ValueError, match="no returned solution"):
        optimizer.summary()
    _solve(optimizer, scenario, compiled=True)
    impossible = replace(
        scenario, employment_cap=0.0, min_goods_output=(("food", 1.0),)
    )
    with pytest.raises(ValueError):
        _solve(optimizer, impossible, compiled=False)
    with pytest.raises(ValueError, match="no returned solution"):
        optimizer.summary()


@pytest.mark.parametrize(
    "multipliers,expected", [((2.0, 2.0), 2.0), ((1.0, 2.0), np.nan)]
)
def test_summary_reports_compiled_throughput(
    toy_economy: Economy, multipliers: tuple[float, float], expected: float
) -> None:
    optimizer = NominalOptimizer(toy_economy)
    optimizer.solve(
        Scenario(
            objective="gdp",
            employment_cap=10_000.0,
            throughput_multipliers=tuple(zip(("farm_a", "farm_b"), multipliers)),
        )
    )
    actual = optimizer.summary().loc[0, "throughput_multiplier"]
    if np.isnan(expected):
        assert pd.isna(actual)
    else:
        assert actual == expected


@pytest.mark.parametrize("kind", ["equilibrium", "supply_chain", "resume"])
def test_example_summary_exports(
    toy_economy: Economy, tmp_path: Path, monkeypatch: pytest.MonkeyPatch, kind: str
) -> None:
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
    recipe_dir = tmp_path / "era_5_automation"
    processes_dir = recipe_dir / "food"
    processes_dir.mkdir(parents=True)
    production.assign(active=True).to_csv(
        processes_dir / "processes.csv", index=False, encoding="utf-8"
    )
    pd.DataFrame(
        {"food": [1.0, 2.0]},
        index=pd.Index(toy_economy.building_index, name="config"),
    ).to_csv(recipe_dir / "building_levels.csv", encoding="utf-8")
    example = (
        optimize_equilibrium
        if kind == "equilibrium"
        else optimize_supply_chain_equilibrium
    )
    for constant in (
        "PRODUCTION_DIR",
        "PARSED_DIR",
        "BUY_PACKAGES_DIR",
        "SUPPLY_CHAINS_DIR",
    ):
        monkeypatch.setattr(example, constant, tmp_path)
    output = tmp_path / "output"
    if kind == "equilibrium":
        monkeypatch.setattr(optimize_equilibrium, "EQUILIBRIUM_DIR", output)
        model, state = optimize_equilibrium.run(max_evaluations=1)
    else:
        monkeypatch.setattr(
            optimize_supply_chain_equilibrium, "SUPPLY_CHAIN_EQUILIBRIUM_DIR", output
        )
        monkeypatch.setattr(
            optimize_supply_chain_equilibrium, "ALLOWED_CHAIN_GOODS", ("food",)
        )
        model, state = optimize_supply_chain_equilibrium.run(max_evaluations=1)
        if kind == "resume":
            model, state = optimize_supply_chain_equilibrium.run(
                max_evaluations=1, resume=True, loss_reduction=0.25
            )
    report = pd.read_csv(output / "summary.csv", encoding="utf-8")
    assert len(report) == 1
    assert set(COMMON_COLUMNS + EQUILIBRIUM_COLUMNS).issubset(report.columns)
    row = report.iloc[0]
    assert row["max_evaluations"] == 1
    assert row["employment_cap"] == 1_000_000
    assert row["workforce_ratio"] == 0.4
    assert row["objective"] == ("average_wealth" if kind == "equilibrium" else "gdp")
    assert row["gdp_weekly"] == pytest.approx(state.gdp_weekly)
    assert row["annual_gdp"] == pytest.approx(state.gdp(annual=True))
    assert row["initial_gdp_weekly"] == pytest.approx(state.gdp_weekly)
    assert row["initial_annual_gdp"] == pytest.approx(state.gdp(annual=True))
    assert row["equilibrium_status"] == "converged"
    assert row["trial_evaluations"] == 1
    assert not row["search_success"]
    assert row["net_infrastructure_usage"] == pytest.approx(
        state.building_levels @ model.infrastructure_vector
    )
    assert row["net_infrastructure_usage"] < 0
    if kind != "equilibrium":
        chains = pd.read_csv(output / "chains.csv", encoding="utf-8")
        assert chains["good"].tolist() == ["food"]
        assert chains["target_base_value"].tolist() == [100_000.0]
        np.testing.assert_allclose(
            chains["target_quantity"].to_numpy(), 100_000.0 / model.base_prices
        )
        matrix = pd.read_csv(
            output / "chain_matrix.csv", index_col="config", encoding="utf-8"
        )
        np.testing.assert_allclose(
            matrix.loc[list(model.building_index), chains["good"].tolist()].to_numpy()
            @ chains["level"].to_numpy(),
            state.building_levels,
        )
        assert row["recipe_configuration"] == "era_5_automation"
        assert row["initialization"] == (
            "saved_solution" if kind == "resume" else "equal_chains"
        )
        assert row["loss_reduction"] == (0.25 if kind == "resume" else 0.0)
        assert row["reduced_chain_count"] == 0
        assert row["initial_average_wealth"] == pytest.approx(state.average_wealth)
        assert row["chain_count"] == 1
        assert row["configuration_count"] == 2
