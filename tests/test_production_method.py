# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Tests for :class:`vic3_analysis.ProductionMethodParser`."""

from pathlib import Path

import pandas as pd
import pytest

from vic3_analysis import ProductionMethodParser


def _goods_parser(tmp_path: Path, modifiers: str) -> ProductionMethodParser:
    directory = tmp_path / "common" / "production_methods"
    directory.mkdir(parents=True)
    (directory / "test.txt").write_text(
        "pm_test = { building_modifiers = { workforce_scaled = { "
        + modifiers
        + " } } }",
        encoding="utf-8",
    )
    return ProductionMethodParser(game_dir=tmp_path)


@pytest.mark.parametrize(
    ("input_prefix", "output_prefix"),
    [
        ("goods", "goods"),
        ("building", "building"),
        ("building", "goods"),
        ("goods", "building"),
    ],
)
def test_goods_flows_support_modern_and_legacy_modifiers(
    tmp_path: Path, input_prefix: str, output_prefix: str
) -> None:
    parser = _goods_parser(
        tmp_path,
        f"{input_prefix}_input_tools_add = 5\n"
        f"{output_prefix}_output_coal_add = 25.5\n"
        f"{input_prefix}_input_small_arms_add = -2\n"
        f"{output_prefix}_output_grain_add = -1.5\n"
        f"{output_prefix}_output_tools_mult = 99\n"
        "building_employment_laborers_add = 99\n",
    )
    frame = parser.to_dataframe(
        df_goods=pd.DataFrame(
            {"key": ["tools", "coal", "small_arms", "grain", "wood"]}
        ),
        df_buildings=pd.DataFrame(
            {"key": ["building_test"], "production_method_groups": [["pmg_test"]]}
        ),
        pmg_dict={"pmg_test": ["pm_test"]},
    )

    assert len(frame) == 1
    assert frame.filter(like="goods_").iloc[0].to_dict() == {
        "goods_tools": -5,
        "goods_coal": 25.5,
        "goods_small_arms": 2,
        "goods_grain": -1.5,
        "goods_wood": 0,
    }


@pytest.mark.parametrize("prefix", ["goods", "building"])
def test_goods_flows_reject_unknown_good(tmp_path: Path, prefix: str) -> None:
    parser = _goods_parser(tmp_path, f"{prefix}_input_unknown_add = 5")

    with pytest.raises(ValueError, match=f"{prefix}_input_unknown_add"):
        parser.to_dataframe(
            df_goods=pd.DataFrame({"key": ["tools"]}),
            df_buildings=pd.DataFrame(
                {"key": ["building_test"], "production_method_groups": [["pmg_test"]]}
            ),
            pmg_dict={"pmg_test": ["pm_test"]},
        )


def test_production_method() -> None:
    parser = ProductionMethodParser()
    frame = parser.to_dataframe(language="english")
    expected = [
        "building",
        "building_localization",
        "production_method_group",
        "production_method_group_localization",
        "production_method",
        "production_method_localization",
    ]
    assert list(frame.columns[:6]) == expected
    for column in expected[1::2]:
        assert str(frame[column].dtype) == "string"
    row = frame[frame["production_method"] == "pm_bakery"].iloc[0]
    assert row["building_localization"] == "Food Industries"
    assert row["production_method_localization"] == "Bakeries"


def test_state_modifiers() -> None:
    parser = ProductionMethodParser()
    modifiers = parser.state_modifiers()

    assert modifiers["pm_basic_port"] == {"state_infrastructure_add": 3}
    assert modifiers["pm_early_trains"] == {
        "state_infrastructure_add": 20,
        "state_pollution_generation_add": 25,
    }
    assert modifiers["pm_trade_center_trade_quantity_limited"] == {
        "state_trade_quantity_mult": -0.5
    }
    assert "pm_no_passenger_trains" not in modifiers


def test_to_dataframe_state_modifier_columns() -> None:
    parser = ProductionMethodParser()
    df = parser.to_dataframe()

    ports = df[df["production_method"] == "pm_basic_port"]
    assert (ports["state_infrastructure_add"] == 3).all()

    trains = df[df["production_method"] == "pm_early_trains"]
    assert (trains["state_infrastructure_add"] == 20).all()
    assert (trains["state_pollution_generation_add"] == 25).all()

    limited = df[df["production_method"] == "pm_trade_center_trade_quantity_limited"]
    assert (limited["state_trade_quantity_mult"] == -0.5).all()

    passenger = df[df["production_method"] == "pm_no_passenger_trains"]
    assert (passenger["state_infrastructure_add"] == 0).all()
    assert (passenger["state_pollution_generation_add"] == 0).all()
