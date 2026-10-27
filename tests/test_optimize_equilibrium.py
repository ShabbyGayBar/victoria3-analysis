# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Check the equilibrium example's saved supply-chain production selection."""

from pathlib import Path

import pandas as pd
import pytest

from examples.optimize_equilibrium import load_production_units


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
