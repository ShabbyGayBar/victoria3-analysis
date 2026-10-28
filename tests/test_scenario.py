# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

from dataclasses import FrozenInstanceError

import pytest

from vic3_analysis import Scenario


def test_defaults():
    scenario = Scenario()
    assert scenario.min_goods_output == ()
    assert scenario.objective == "automation"
    assert scenario.default_min_goods_output == 0.0
    assert scenario.banned_pms == ()
    assert scenario.building_level_caps == ()
    assert scenario.banned_building_groups == ()
    assert scenario.throughput_multipliers == ()
    assert scenario.era_cap is None
    assert scenario.construction_cost_cap is None
    assert scenario.employment_cap is None
    assert scenario.arable_land_cap is None
    assert scenario.min_net_infrastructure is None
    assert scenario.urbanization_per_center is None
    assert scenario.goods_import == ()
    assert scenario.goods_export == ()
    assert scenario.workforce_ratio == 1.0
    assert scenario.name is None


def test_invalid_objective_raises_at_construction():
    with pytest.raises(ValueError, match="Unknown objective"):
        Scenario(objective="bogus")


@pytest.mark.parametrize(
    "ratio", [0.0, -0.25, 1.01, float("nan"), float("inf"), -float("inf")]
)
def test_invalid_workforce_ratio(ratio: float):
    with pytest.raises(ValueError, match="workforce_ratio"):
        Scenario(workforce_ratio=ratio)


def test_frozen():
    scenario = Scenario(min_goods_output=(("steel", 1.0),))
    with pytest.raises(FrozenInstanceError):
        setattr(scenario, "objective", "gdp")  # noqa: B010


def test_display_name():
    assert Scenario(name="recipe-a").display_name() == "recipe-a"
    assert Scenario(min_goods_output=(("steel", 5.0),)).display_name() == "steel"
    assert (
        Scenario(min_goods_output=(("steel", 5.0), ("tools", 2.0))).display_name()
        == "steel+tools"
    )
    assert Scenario().display_name() == "unnamed"
