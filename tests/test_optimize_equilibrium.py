# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check the equilibrium example's production selection and feasible starting mix."""

from dataclasses import replace
from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from examples import DEFAULT_BANNED_BGS
from examples.optimize_equilibrium import _initial_levels, load_production_units
from vic3_analysis import Economy


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
        ([8.0, -2.0, -2.0, -100.0], [1.0, 2.0, 2.0, 0.0]),
        ([0.0, 0.0, 0.0, -100.0], [1.0, 1.0, 1.0, 0.0]),
    ],
)
def test_initial_levels_cover_infrastructure_and_scale_employment(
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
    assert float(levels @ model.infrastructure_vector) <= 1e-7
    assert levels[-1] == 0.0


def test_initial_levels_reject_consumption_without_active_supplier(
    seed_economy: Economy,
) -> None:
    production = seed_economy.df_production.copy()
    production["infrastructure_usage_per_level"] = [1.0, 0.0, 0.0, -100.0]
    model = replace(seed_economy, df_production=production)
    with pytest.raises(ValueError, match="no active supplier"):
        _initial_levels(model)


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
        pd.DataFrame({"config": configs, "active": active}).to_csv(
            directory / "processes.csv", index=False, encoding="utf-8"
        )
    other = tmp_path / "era_3_construction" / "grain"
    other.mkdir(parents=True)
    pd.DataFrame({"config": ["farm+tractor"], "active": [True]}).to_csv(
        other / "processes.csv", index=False, encoding="utf-8"
    )

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
    pd.DataFrame({"config": ["mill+manual"], "active": [False]}).to_csv(
        directory / "processes.csv", index=False, encoding="utf-8"
    )
    with pytest.raises(ValueError, match="No active production units"):
        load_production_units(tmp_path / "production.csv", tmp_path)


def test_stale_supply_chain_configuration(tmp_path: Path) -> None:
    directory = tmp_path / "paper"
    directory.mkdir()
    pd.DataFrame({"config": ["mill+obsolete"], "active": [True]}).to_csv(
        directory / "processes.csv", index=False, encoding="utf-8"
    )
    production_path = tmp_path / "production.csv"
    pd.DataFrame({"building": ["mill"], "production_method": ["automatic"]}).to_csv(
        production_path, index=False, encoding="utf-8"
    )
    with pytest.raises(
        ValueError, match=r"missing from the production table: mill\+obsolete"
    ):
        load_production_units(production_path, tmp_path)
