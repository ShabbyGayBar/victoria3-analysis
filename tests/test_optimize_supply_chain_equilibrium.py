# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Saved-recipe loading, chain initialization, and exported matrix accounting."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from examples import DATASETS_DIR, PRODUCTION_DIR, SUPPLY_CHAIN_EQUILIBRIUM_DIR
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


def _reports(root: Path) -> Path:
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
            "good": ["steel", "paper", "failed"],
            "status": ["success", "success", "failure"],
            "target_quantity": [2000.0, 2500.0, np.nan],
            "target_base_value": [100_000.0, 100_000.0, np.nan],
        }
    ).to_csv(root / "summary.csv", index=False, encoding="utf-8")
    pd.DataFrame(
        {
            "steel": [3.0, 1.0, 0.0],
            "paper": [1.0, 2.0, 0.0],
            "failed": [np.nan, np.nan, np.nan],
        },
        index=pd.Index(["mine+pump", "mill+automatic", "unused+manual"], name="config"),
    ).to_csv(root / "building_levels.csv", encoding="utf-8")
    return path


def test_loading_aligns_keys_preserves_order_and_supporting_processes(tmp_path: Path):
    production_path = _reports(tmp_path)
    production, matrix, metadata = load_recipes(production_path, tmp_path)
    assert production["building"].tolist() == ["mill", "mine"]
    expected = pd.DataFrame(
        {"steel": [1.0, 3.0], "paper": [2.0, 1.0]},
        index=pd.Index(["mill+automatic", "mine+pump"], name="config"),
    )
    pd.testing.assert_frame_equal(matrix, expected)
    np.testing.assert_array_equal(matrix.to_numpy() @ np.ones(2), [3, 4])
    assert metadata["target_quantity"].tolist() == [2000, 2500]
    report = tmp_path / "building_levels.csv"
    levels = pd.read_csv(report, index_col="config", encoding="utf-8")
    levels.iloc[::-1].to_csv(report, encoding="utf-8")
    _, reordered, _ = load_recipes(production_path, tmp_path)
    pd.testing.assert_frame_equal(reordered, expected)


@pytest.mark.parametrize(
    "failure",
    [
        "missing_matrix",
        "unknown_config",
        "negative_level",
        "duplicate_config",
        "partial_nan",
        "infinite_level",
        "zero_recipe",
        "missing_config",
        "missing_good",
    ],
)
def test_invalid_recipe_matrices(tmp_path: Path, failure: str):
    production = _reports(tmp_path)
    path = tmp_path / "building_levels.csv"
    if failure == "missing_matrix":
        path.unlink()
        with pytest.raises(FileNotFoundError, match="examples.supply_chain_compare"):
            load_recipes(production, tmp_path)
        return
    report = pd.read_csv(path, index_col="config", encoding="utf-8")
    if failure == "unknown_config":
        report.index = ["unknown+pm", *report.index[1:]]
    elif failure == "negative_level":
        report.iloc[0, 0] = -1.0
    elif failure == "duplicate_config":
        report.index = [report.index[1], *report.index[1:]]
    elif failure == "partial_nan":
        report.iloc[0, 0] = np.nan
    elif failure == "infinite_level":
        report.iloc[0, 0] = np.inf
    elif failure == "zero_recipe":
        report["steel"] = 0.0
    elif failure == "missing_config":
        report = report.iloc[:2]
    else:
        report = report.drop(columns="steel")
    report.index.name = "config"
    report.to_csv(path, encoding="utf-8")
    with pytest.raises(ValueError):
        load_recipes(production, tmp_path)


@pytest.mark.parametrize(
    "failure",
    [
        "no_success",
        "missing_columns",
        "duplicate_good",
        "bad_good",
        "target",
        "normalization",
    ],
)
def test_invalid_summary(tmp_path: Path, failure: str):
    production = _reports(tmp_path)
    path = tmp_path / "summary.csv"
    summary = pd.read_csv(path, encoding="utf-8")
    if failure == "no_success":
        summary["status"] = "failure"
    elif failure == "missing_columns":
        summary = summary.drop(columns="target_quantity")
    elif failure == "duplicate_good":
        summary.loc[1, "good"] = "steel"
    elif failure == "bad_good":
        summary.loc[1, "good"] = ""
    elif failure == "target":
        summary.loc[0, "target_quantity"] = 0.0
    else:
        summary.loc[0, "target_base_value"] = 1.0
    summary.to_csv(path, index=False, encoding="utf-8")
    with pytest.raises(ValueError):
        load_recipes(production, tmp_path)


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


def test_real_recipes_align_and_preserve_normalization(tmp_path: Path):
    economy = load_economy(DATASETS_DIR)
    sweep = sweep_supply_chains(
        economy, TEMPLATES[1], goods=ALLOWED_CHAIN_GOODS, target_value=100_000.0
    )
    sweep.summary.to_csv(tmp_path / "summary.csv", index=False, encoding="utf-8")
    sweep.df_building_levels.to_csv(tmp_path / "building_levels.csv", encoding="utf-8")
    production, matrix, metadata = load_recipes(
        PRODUCTION_DIR / "production_table.csv",
        tmp_path,
        allowed_goods=ALLOWED_CHAIN_GOODS,
    )
    assert matrix.shape == (len(production), len(metadata))
    assert tuple(matrix.columns) == tuple(metadata["good"])
    assert tuple(matrix.columns) == ALLOWED_CHAIN_GOODS
    assert (metadata["target_base_value"] == 100_000.0).all()
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


def test_missing_config_column_and_duplicate_production(tmp_path: Path):
    path = _reports(tmp_path)
    production = pd.read_csv(path, encoding="utf-8")
    pd.concat([production, production.iloc[:1]]).to_csv(
        path, index=False, encoding="utf-8"
    )
    with pytest.raises(ValueError, match="duplicate configuration"):
        load_recipes(path, tmp_path)
    production.to_csv(path, index=False, encoding="utf-8")
    report = tmp_path / "building_levels.csv"
    levels = pd.read_csv(report, encoding="utf-8").drop(columns="config")
    levels.to_csv(report, index=False, encoding="utf-8")
    with pytest.raises(ValueError, match="config"):
        load_recipes(path, tmp_path)


def test_selected_recipes_preserve_requested_order_and_skip_other_columns(
    tmp_path: Path,
):
    production = _reports(tmp_path)
    _, matrix, metadata = load_recipes(
        production, tmp_path, allowed_goods=("paper", "steel")
    )
    assert matrix.columns.tolist() == ["paper", "steel"]
    assert metadata["good"].tolist() == ["paper", "steel"]
    np.testing.assert_array_equal(matrix.to_numpy(), [[2, 1], [1, 3]])
    path = tmp_path / "building_levels.csv"
    levels = pd.read_csv(path, index_col="config", encoding="utf-8")
    levels["steel"] = -1.0
    levels.to_csv(path, encoding="utf-8")
    _, selected, _ = load_recipes(production, tmp_path, allowed_goods=("paper",))
    assert selected.columns.tolist() == ["paper"]
    np.testing.assert_array_equal(selected.to_numpy(), [[2], [1]])


def test_loading_skips_failed_columns_and_aligns_metadata(tmp_path: Path):
    production = _reports(tmp_path)
    path = tmp_path / "building_levels.csv"
    levels = pd.read_csv(path, index_col="config", encoding="utf-8")
    levels["steel"] = np.nan
    levels.to_csv(path, encoding="utf-8")
    with pytest.warns(UserWarning, match="steel"):
        _, matrix, metadata = load_recipes(production, tmp_path)
    assert matrix.columns.tolist() == ["paper"]
    assert metadata["good"].tolist() == ["paper"]
    assert metadata["target_quantity"].tolist() == [2500.0]


def test_loading_preserves_round_trip_coefficients(tmp_path: Path):
    production = _reports(tmp_path)
    path = tmp_path / "building_levels.csv"
    levels = pd.read_csv(path, index_col="config", encoding="utf-8")
    coefficient = 1.0000000000000002
    levels.loc["mill+automatic", "steel"] = coefficient
    levels.to_csv(path, encoding="utf-8")
    _, matrix, _ = load_recipes(production, tmp_path)
    assert matrix.loc["mill+automatic", "steel"] == coefficient


@pytest.mark.parametrize("goods", [(), ("paper", "paper"), ("missing",), ("failed",)])
def test_unavailable_or_invalid_selected_recipes(
    tmp_path: Path, goods: tuple[str, ...]
):
    production = _reports(tmp_path)
    with pytest.raises(ValueError):
        load_recipes(production, tmp_path, allowed_goods=goods)


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
