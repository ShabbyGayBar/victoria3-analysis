"""Tests for :class:`vic3_analysis.ProductionMethodParser`."""

from vic3_analysis import ProductionMethodParser


def test_production_method() -> None:
    parser = ProductionMethodParser()
    parser.to_dataframe()


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
