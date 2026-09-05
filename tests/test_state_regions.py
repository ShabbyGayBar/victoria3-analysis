import pandas as pd
import pytest

from vic3_analysis import (
    StateRegionsParser,
    state_region_arable_land_limit,
    state_region_resource_limits,
)


def test_buildings():
    parser = StateRegionsParser()
    parser.to_dataframe()


@pytest.fixture
def state_regions_df() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "key": ["STATE_A", "STATE_B", "STATE_C"],
            "arable_land": [100, 200, 300],
            "resource_building_coal_mine": [10, 4, 0],
            "resource_building_oil_rig": [0, 3, 0],
            "resource_building_gold_field": [2, 0, 0],
            "resource_building_gold_mine": [0, 1, 0],
            "discovered_amount_resource_building_oil_rig": [0, 1, 0],
            "undiscovered_amount_resource_building_oil_rig": [0, 2, 0],
        }
    )


def test_state_region_resource_limits_aggregate_total_potential(
    state_regions_df: pd.DataFrame,
):
    limits = state_region_resource_limits(
        state_regions_df, ["STATE_A", "STATE_B", "STATE_A"]
    )

    assert list(limits) == [
        "building_coal_mine",
        "building_oil_rig",
        "building_gold_field",
        "building_gold_mine",
    ]
    assert limits == {
        "building_coal_mine": 14.0,
        "building_oil_rig": 3.0,
        "building_gold_field": 0.0,
        "building_gold_mine": 3.0,
    }


def test_state_region_resource_limits_include_absent_resources(
    state_regions_df: pd.DataFrame,
):
    limits = state_region_resource_limits(state_regions_df, ["STATE_C"])

    assert limits == {
        "building_coal_mine": 0.0,
        "building_oil_rig": 0.0,
        "building_gold_field": 0.0,
        "building_gold_mine": 0.0,
    }


def test_state_region_resource_limits_reject_unknown_key(
    state_regions_df: pd.DataFrame,
):
    with pytest.raises(ValueError, match="Unknown state-region key"):
        state_region_resource_limits(state_regions_df, ["STATE_UNKNOWN"])


def test_state_region_resource_limits_require_key_column():
    with pytest.raises(ValueError, match="must contain a 'key' column"):
        state_region_resource_limits(pd.DataFrame({"resource_x": [1]}), ["STATE_A"])


def test_state_region_arable_land_limit_deduplicates_regions(
    state_regions_df: pd.DataFrame,
):
    assert state_region_arable_land_limit(
        state_regions_df, ["STATE_A", "STATE_B", "STATE_A"]
    ) == pytest.approx(300.0)


def test_state_region_arable_land_limit_requires_column():
    with pytest.raises(ValueError, match="must contain an 'arable_land' column"):
        state_region_arable_land_limit(pd.DataFrame({"key": ["STATE_A"]}), ["STATE_A"])
