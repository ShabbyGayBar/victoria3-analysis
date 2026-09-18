from pathlib import Path

import numpy as np
import pandas as pd

from vic3_analysis.analysis.supply_chain.sweep import SWEEP_COLUMNS

TABLE_PATH = (
    Path(__file__).resolve().parent.parent / "tables" / "supply_chain_cangshulun.csv"
)

VARIANT_NAMES = {
    "glass_bone_china",
    "luxury_furniture",
    "logging_hardwood",
    "groceries_with_liquor",
    "luxury_clothes",
    "urban_center_transportation",
    "coal_fired_plant",
}


def test_product_details_schema_and_normalization():
    df = pd.read_csv(TABLE_PATH)
    expected_columns = ["good", "variant", "ban_config", *SWEEP_COLUMNS[1:]]
    assert list(df.columns) == expected_columns
    np.testing.assert_allclose(df["target_base_value"], 100000.0)
    np.testing.assert_allclose(
        df["target_quantity"] * df["terminal_base_price"],
        100000.0,
    )
    assert set(df["ban_config"]) == {"cangshulun_video"}
    assert set(df["status"]) == {"success"}
    errors = df["error_message"]
    if not isinstance(errors, pd.Series):
        raise TypeError("error_message must select one Series.")
    assert errors.isna().all()  # pyright: ignore[reportGeneralTypeIssues]
    assert set(df.loc[df["variant"] != "base", "variant"]) == VARIANT_NAMES


def test_product_details_chain_metrics_are_bounded_by_system_metrics():
    df = pd.read_csv(TABLE_PATH)
    np.testing.assert_allclose(df["chain_gdp_weekly"], df["system_gdp_weekly"])
    assert np.asarray(df["chain_employment_share"] <= 1.0 + 1e-9).all()
    assert np.asarray(df["chain_construction_share"] <= 1.0 + 1e-9).all()
    assert np.asarray(df["realized_process_count"] > 0).all()
