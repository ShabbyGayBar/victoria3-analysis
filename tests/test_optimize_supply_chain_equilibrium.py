# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Saved-recipe loading, chain initialization, and exported matrix accounting."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from examples import PRODUCTION_DIR, SUPPLY_CHAIN_EQUILIBRIUM_DIR, SUPPLY_CHAINS_DIR
from examples.optimize_supply_chain_equilibrium import (
    ALLOWED_CHAIN_GOODS,
    _initial_levels,
    _resume_levels,
    load_recipes,
)
from tests.test_equilibrium_optimizer import toy_economy
from vic3_analysis import (
    Economy,
    Scenario,
    SupplyChainBasis,
    SupplyChainEquilibriumOptimizer,
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
    for good, levels in (("steel", [3.0, 1.0]), ("paper", [1.0, 2.0])):
        directory = root / good
        directory.mkdir()
        pd.DataFrame(
            {
                "config": ["mine+pump", "mill+automatic", "unused+manual"],
                "active": [True, True, False],
                "in_terminal_chain": [False, True, False],
                "level": [*levels, 0.0],
                "throughput_multiplier": [1.0, 1.0, 1.0],
            }
        ).to_csv(directory / "processes.csv", index=False, encoding="utf-8")
    return path


def test_loading_aligns_keys_preserves_order_and_supporting_processes(tmp_path: Path):
    production_path = _reports(tmp_path)
    production, basis, metadata = load_recipes(production_path, tmp_path)
    assert production["building"].tolist() == ["mill", "mine"]
    assert basis.chain_index == ("steel", "paper")
    assert basis.building_index == ("mill+automatic", "mine+pump")
    np.testing.assert_array_equal(basis.matrix, [[1, 2], [3, 1]])
    np.testing.assert_array_equal(basis.to_building_levels(np.ones(2)), [3, 4])
    assert metadata["target_quantity"].tolist() == [2000, 2500]
    report = tmp_path / "steel/processes.csv"
    processes = pd.read_csv(report, encoding="utf-8")
    processes.iloc[::-1].to_csv(report, index=False, encoding="utf-8")
    _, reordered, _ = load_recipes(production_path, tmp_path)
    np.testing.assert_array_equal(reordered.matrix, basis.matrix)


@pytest.mark.parametrize(
    "failure",
    [
        "missing_report",
        "unknown_config",
        "negative_level",
        "duplicate_config",
        "throughput",
        "invalid_active",
        "zero_active",
    ],
)
def test_invalid_process_reports(tmp_path: Path, failure: str):
    production = _reports(tmp_path)
    path = tmp_path / "steel/processes.csv"
    if failure == "missing_report":
        path.unlink()
        with pytest.raises(FileNotFoundError, match="Missing recipe"):
            load_recipes(production, tmp_path)
        return
    report = pd.read_csv(path, encoding="utf-8")
    if failure == "unknown_config":
        report.loc[0, "config"] = "unknown+pm"
    elif failure == "negative_level":
        report.loc[0, "level"] = -1.0
    elif failure == "duplicate_config":
        report.loc[0, "config"] = report.loc[1, "config"]
    elif failure == "throughput":
        report.loc[0, "throughput_multiplier"] = 2.0
    elif failure == "invalid_active":
        report["active"] = ["bad", "True", "False"]
    else:
        report["active"] = False
    report.to_csv(path, index=False, encoding="utf-8")
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
        summary.loc[1, "good"] = "../paper"
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
    basis = SupplyChainBasis(
        tuple(toy_economy.building_index), ("a", "b"), np.array([[1, 0], [0.5, 2]])
    )
    levels = _initial_levels(toy_economy, basis)
    assert levels[0] == levels[1]
    assert float(
        basis.to_building_levels(levels) @ toy_economy.employment_vector
    ) == pytest.approx(1_000_000)


def test_real_recipes_align_and_preserve_normalization():
    production, basis, metadata = load_recipes(
        PRODUCTION_DIR / "production_table.csv",
        SUPPLY_CHAINS_DIR / "era_5_automation",
        allowed_goods=ALLOWED_CHAIN_GOODS,
    )
    assert basis.matrix.shape == (len(production), len(metadata))
    assert basis.chain_index == tuple(metadata["good"])
    assert basis.chain_index == ALLOWED_CHAIN_GOODS
    assert (metadata["target_base_value"] == 100_000.0).all()
    assert np.isfinite(basis.matrix).all()


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


def test_missing_process_columns_and_duplicate_production(tmp_path: Path):
    path = _reports(tmp_path)
    production = pd.read_csv(path, encoding="utf-8")
    pd.concat([production, production.iloc[:1]]).to_csv(
        path, index=False, encoding="utf-8"
    )
    with pytest.raises(ValueError, match="duplicate configuration"):
        load_recipes(path, tmp_path)
    production.to_csv(path, index=False, encoding="utf-8")
    report = tmp_path / "steel/processes.csv"
    processes = pd.read_csv(report, encoding="utf-8").drop(columns="level")
    processes.to_csv(report, index=False, encoding="utf-8")
    with pytest.raises(ValueError, match="required process columns"):
        load_recipes(path, tmp_path)


def test_selected_recipes_preserve_requested_order_and_skip_other_reports(
    tmp_path: Path,
):
    production = _reports(tmp_path)
    _, basis, metadata = load_recipes(
        production, tmp_path, allowed_goods=("paper", "steel")
    )
    assert basis.chain_index == ("paper", "steel")
    assert metadata["good"].tolist() == ["paper", "steel"]
    np.testing.assert_array_equal(basis.matrix, [[2, 1], [1, 3]])
    (tmp_path / "steel/processes.csv").unlink()
    _, selected, _ = load_recipes(production, tmp_path, allowed_goods=("paper",))
    assert selected.chain_index == ("paper",)
    np.testing.assert_array_equal(selected.matrix, [[2], [1]])


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
    basis = SupplyChainBasis(
        tuple(model.building_index),
        ("food", "input"),
        np.array([[1.0, 0.0], [0.0, 2.0]]),
    )
    problem = SupplyChainEquilibriumOptimizer(model, basis).compile(
        Scenario(objective="gdp", default_min_goods_output=None, employment_cap=50_000)
    )
    previous = np.array([0.5000000000000001, 0.7000000000000001])
    pd.DataFrame({"good": basis.chain_index, "level": previous}).iloc[::-1].to_csv(
        tmp_path / "chains.csv", index=False, encoding="utf-8"
    )
    matrix = pd.DataFrame(
        basis.matrix, index=basis.building_index, columns=basis.chain_index
    )
    matrix.index.name = "config"
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
    pd.DataFrame({"good": basis.chain_index, "level": previous}).to_csv(
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
    basis = SupplyChainBasis(
        tuple(toy_economy.building_index), ("food",), np.ones((2, 1))
    )
    problem = SupplyChainEquilibriumOptimizer(toy_economy, basis).compile(
        Scenario(objective="gdp")
    )
    with pytest.raises(ValueError, match="loss_reduction"):
        _resume_levels(problem, tmp_path, reduction)
