from pathlib import Path

import numpy as np
import pandas as pd


TABLE_PATH = (
    Path(__file__).resolve().parent.parent
    / "tables"
    / "supply_chain_cangshulun.csv"
)

VARIANT_NAMES = {
    "transportation_railway_era3",
    "glass_pure",
    "glass_bone_china",
    "furniture_pure",
    "luxury_furniture",
    "logging_wood",
    "logging_hardwood",
    "groceries_pure",
    "groceries_with_liquor",
    "clothes_pure",
    "luxury_clothes",
    "grain_wheat_no_secondary",
    "services_urban_center",
}


def test_product_details_schema_and_normalization():
    df = pd.read_csv(TABLE_PATH)
    fixed_columns = [
        "scenario",
        "goods",
        "objective",
        "ban_config",
        "production",
        "base_price",
        "annual_gdp",
        "employment",
        "gdp_per_capita",
        "construction_cost",
        "gdp_per_construction",
        "era_cap",
        "arable_land_consumption",
    ]
    tail_columns = [
        "n_active_buildings",
        "chain_depth",
        "n_raw_inputs",
        "bottleneck_good",
        "bottleneck_cost_share",
        "bottleneck_marginal",
        "error",
    ]
    level_columns = [
        column
        for column in df.columns
        if column.startswith("level_") and not column.startswith("level_per_10k_")
    ]
    per_10k_columns = [
        f"level_per_10k_{column.removeprefix('level_')}" for column in level_columns
    ]

    assert list(df.columns) == (
        fixed_columns + level_columns + per_10k_columns + tail_columns
    )
    np.testing.assert_allclose(df["production"] * df["base_price"], 100000.0)
    assert set(df["ban_config"]) == {"cangshulun_video"}
    errors = df["error"]
    if not isinstance(errors, pd.Series):
        raise TypeError("error must select one Series.")
    assert errors.isna().all()  # pyright: ignore[reportGeneralTypeIssues]
    assert set(df.loc[df["scenario"] != "base", "scenario"]) == VARIANT_NAMES
    per_capita = df["gdp_per_capita"]
    if not isinstance(per_capita, pd.Series):
        raise TypeError("gdp_per_capita must select one Series.")
    is_decreasing = per_capita.is_monotonic_decreasing
    if not isinstance(is_decreasing, bool):
        raise TypeError("is_monotonic_decreasing must return a bool.")
    assert is_decreasing


def test_product_details_resource_levels_are_per_10k_employment():
    df = pd.read_csv(TABLE_PATH)
    level_columns = [
        column
        for column in df.columns
        if column.startswith("level_") and not column.startswith("level_per_10k_")
    ]
    for source in level_columns:
        destination = f"level_per_10k_{source.removeprefix('level_')}"
        expected = df[source] / df["employment"] * 10000.0
        np.testing.assert_allclose(df[destination], expected)
