import pytest

from vic3_analysis import Scenario


def test_defaults():
    scenario = Scenario()
    assert scenario.produce == ()
    assert scenario.objective == "automation"
    assert scenario.import_limit == 0.0
    assert scenario.banned_pms == ()
    assert scenario.building_limits == ()
    assert scenario.banned_building_groups == ()
    assert scenario.throughput_bonuses == ()
    assert scenario.era_cap is None
    assert scenario.construction_cost_cap is None
    assert scenario.employment_cap is None
    assert scenario.arable_land_cap is None
    assert scenario.min_infrastructure is None
    assert scenario.urbanization_per_center is None
    assert scenario.imports == ()
    assert scenario.exports == ()
    assert scenario.pop_needs == ()
    assert scenario.name is None


def test_invalid_objective_raises_at_construction():
    with pytest.raises(ValueError, match="Unknown objective"):
        Scenario(objective="bogus")


def test_frozen():
    scenario = Scenario(produce=(("steel", 1.0),))
    with pytest.raises(Exception):
        setattr(scenario, "objective", "gdp")


def test_display_name():
    assert Scenario(name="recipe-a").display_name() == "recipe-a"
    assert Scenario(produce=(("steel", 5.0),)).display_name() == "steel"
    assert (
        Scenario(produce=(("steel", 5.0), ("tools", 2.0))).display_name()
        == "steel+tools"
    )
    assert Scenario().display_name() == "unnamed"
