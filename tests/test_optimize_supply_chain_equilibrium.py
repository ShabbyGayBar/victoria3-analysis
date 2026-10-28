# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Saved-recipe loading, chain initialization, and exported matrix accounting."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from examples import DATASETS_DIR, PRODUCTION_DIR, SUPPLY_CHAIN_EQUILIBRIUM_DIR
from examples import optimize_supply_chain_equilibrium as example
from examples.optimize_supply_chain_equilibrium import (
    ALLOWED_CHAIN_GOODS,
    _initial_levels,
    _resume_levels,
    load_recipes,
)
from examples.supply_chain_compare import TEMPLATES, load_economy
from tests.test_equilibrium_optimizer import toy_economy
from vic3_analysis import (
    Economy,
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
