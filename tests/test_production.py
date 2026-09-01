"""Tests for :func:`vic3_analysis.production_table`."""

from pathlib import Path

import numpy as np
import pandas as pd
import pytest

from vic3_analysis import production_table

TABLES_DIR = Path(__file__).resolve().parent.parent / "tables"

META_COLUMNS = [
    "building",
    "production_method",
    "building_group",
    "urbanization",
    "infrastructure_usage_per_level",
    "era",
    "unlocking_tech",
    "employment",
    "construction_cost",
    "value_goods_inputs_nominal",
    "value_goods_outputs_nominal",
    "profit_nominal",
    "profit_margin_nominal",
    "profit_per_capita_nominal",
    "profit_per_construction_cost_nominal",
]


@pytest.fixture(scope="module")
def df_buildings() -> pd.DataFrame:
    return pd.read_csv(TABLES_DIR / "buildings.csv")


@pytest.fixture(scope="module")
def df_goods() -> pd.DataFrame:
    return pd.read_csv(TABLES_DIR / "goods.csv")


@pytest.fixture(scope="module")
def df_pm() -> pd.DataFrame:
    return pd.read_csv(TABLES_DIR / "production_methods.csv")


@pytest.fixture(scope="module")
def df_tech() -> pd.DataFrame:
    return pd.read_csv(TABLES_DIR / "technology.csv")


@pytest.fixture(scope="module")
def df_production(
    df_buildings: pd.DataFrame,
    df_goods: pd.DataFrame,
    df_pm: pd.DataFrame,
    df_tech: pd.DataFrame,
) -> pd.DataFrame:
    return production_table(df_buildings, df_goods, df_pm, df_tech)


def test_schema(
    df_production: pd.DataFrame,
    df_goods: pd.DataFrame,
    df_pm: pd.DataFrame,
) -> None:
    goods_cols = [f"goods_{key}" for key in df_goods["key"]]
    profession_cols = [col for col in df_pm.columns if col.startswith("employment_")]

    assert df_production.shape == (1638, 82)
    assert list(df_production.columns) == [*META_COLUMNS, *goods_cols, *profession_cols]
    assert df_production.index.equals(pd.RangeIndex(len(df_production)))
    assert df_production["era"].dtype == np.int64
    assert df_production["employment"].dtype == np.int64
    assert df_production["construction_cost"].dtype == np.int64
    assert df_production["profit_nominal"].dtype == np.float64
    assert isinstance(df_production["unlocking_tech"].dtype, pd.StringDtype)


def test_all_buildings_kept_with_zero_default_cost(
    df_production: pd.DataFrame,
    df_buildings: pd.DataFrame,
) -> None:
    assert set(df_production["building"]) == set(df_buildings["key"])

    per_building = df_production.groupby("building")["construction_cost"].nunique()
    assert (per_building == 1).all()

    expected = dict(
        zip(
            df_buildings["key"],
            df_buildings["required_construction_points"].fillna(0).astype(np.int64),
        )
    )
    actual = df_production.groupby("building", sort=False)["construction_cost"].first()
    assert actual.to_dict() == expected


def test_food_industry_default_combination(
    df_production: pd.DataFrame,
    df_goods: pd.DataFrame,
) -> None:
    row = df_production[
        (df_production["building"] == "building_food_industry")
        & (
            df_production["production_method"]
            == "pm_bakery+pm_disabled_canning+pm_disabled_distillery+pm_manual_dough_processing"
        )
    ].iloc[0]

    cost = dict(zip(df_goods["key"], df_goods["cost"]))
    expected_inputs = 40 * cost["grain"]
    expected_outputs = 45 * cost["groceries"]
    expected_profit = expected_outputs - expected_inputs

    assert row["employment"] == 5000
    assert row["employment_laborers"] == 4500
    assert row["employment_shopkeepers"] == 500
    assert row["goods_grain"] == -40
    assert row["goods_groceries"] == 45
    assert row["era"] == 1
    assert row["unlocking_tech"] == "manufacturies"
    assert row["construction_cost"] == 600
    assert row["value_goods_inputs_nominal"] == pytest.approx(expected_inputs)
    assert row["value_goods_outputs_nominal"] == pytest.approx(expected_outputs)
    assert row["profit_nominal"] == pytest.approx(expected_profit)
    assert row["profit_margin_nominal"] == pytest.approx(
        expected_profit / expected_outputs
    )
    assert row["profit_per_capita_nominal"] == pytest.approx(expected_profit / 5000)
    assert row["profit_per_construction_cost_nominal"] == pytest.approx(
        expected_profit / 600
    )


def test_unlocking_tech_semantics(
    df_production: pd.DataFrame,
    df_buildings: pd.DataFrame,
    df_tech: pd.DataFrame,
) -> None:
    split = df_production["unlocking_tech"].str.split("+")
    assert not split.map(lambda keys: len(keys) != len(set(keys))).any()

    era_by_tech = dict(zip(df_tech["key"], df_tech["era"]))

    def expected_era(tech_string: str) -> int:
        return max((era_by_tech[t] for t in tech_string.split("+") if t), default=0)

    np.testing.assert_array_equal(
        df_production["unlocking_tech"].map(expected_era).to_numpy(),
        df_production["era"].to_numpy(),
    )

    building_tech = {
        key: techs.split("+")[0]
        for key, techs in zip(
            df_buildings["key"], df_buildings["unlocking_technologies"]
        )
        if isinstance(techs, str) and techs
    }
    for building, tech in building_tech.items():
        rows = df_production.loc[
            df_production["building"] == building, "unlocking_tech"
        ]
        assert (rows.str.split("+").str[0] == tech).all()

    sweeteners = df_production[
        (df_production["building"] == "building_food_industry")
        & (
            df_production["production_method"]
            == "pm_sweeteners+pm_disabled_canning+pm_disabled_distillery+pm_manual_dough_processing"
        )
    ].iloc[0]
    assert sweeteners["unlocking_tech"] == "manufacturies+distillation"


def test_division_semantics(df_production: pd.DataFrame) -> None:
    zero_cost = df_production.query("construction_cost == 0")
    assert not zero_cost.empty

    profitable = zero_cost.query("profit_nominal != 0")
    assert not profitable.empty
    assert np.isinf(profitable["profit_per_construction_cost_nominal"]).all()

    unprofitable = zero_cost.query("profit_nominal == 0")
    assert unprofitable["profit_per_construction_cost_nominal"].isna().to_numpy().all()

    idle = df_production.query("employment == 0 and profit_nominal == 0")
    assert not idle.empty
    assert idle["profit_per_capita_nominal"].isna().to_numpy().all()
    assert idle["profit_margin_nominal"].isna().to_numpy().all()


def test_combinations_match_pm_sums(
    df_production: pd.DataFrame,
    df_buildings: pd.DataFrame,
    df_goods: pd.DataFrame,
    df_pm: pd.DataFrame,
) -> None:
    for building in [
        "building_food_industry",
        "building_textile_mill",
        "building_urban_center",
    ]:
        rows = df_production[df_production["building"] == building]
        pmg_string = df_buildings.loc[
            df_buildings["key"] == building, "production_method_groups"
        ].iloc[0]
        group_sizes = (
            df_pm[df_pm["building"] == building]
            .groupby("production_method_group")
            .size()
        )
        expected_rows = int(
            np.prod([group_sizes[pmg] for pmg in pmg_string.split("+")])
        )
        assert len(rows) == expected_rows

        value_columns = [
            "production_method",
            "employment",
            *[f"goods_{good}" for good in df_goods["key"]],
        ]
        for values in zip(*(rows[column] for column in value_columns)):
            pm_string, employment, *goods_values = values
            pms = pm_string.split("+")
            members = df_pm[
                (df_pm["building"] == building) & (df_pm["production_method"].isin(pms))
            ]
            assert len(members) == len(pms)
            assert members["employment"].sum() == employment
            for good, value in zip(df_goods["key"], goods_values):
                assert members[f"goods_{good}"].sum() == value


def _buildings_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "key": ["building_a", "building_b"],
            "building_group": ["bg_a", "bg_a"],
            "urbanization": [10.0, np.nan],
            "infrastructure_usage_per_level": [1.0, np.nan],
            "required_construction_points": [100.0, np.nan],
            "production_method_groups": ["pmg_base_a+pmg_auto_a", "pmg_base_b"],
            "unlocking_technologies": ["tech_1", None],
        }
    )


def _goods_frame() -> pd.DataFrame:
    return pd.DataFrame({"key": ["good_x", "good_y"], "cost": [10, 20]})


def _pm_frame() -> pd.DataFrame:
    return pd.DataFrame(
        {
            "building": [
                "building_a",
                "building_a",
                "building_a",
                "building_a",
                "building_b",
            ],
            "production_method_group": [
                "pmg_base_a",
                "pmg_base_a",
                "pmg_auto_a",
                "pmg_auto_a",
                "pmg_base_b",
            ],
            "production_method": ["pm_a1", "pm_a2", "pm_m1", "pm_m2", "pm_b1"],
            "unlocking_technologies": [None, "tech_2", "tech_1", None, None],
            "employment": [100, 150, 0, -50, 10],
            "employment_laborers": [100, 150, 0, 0, 10],
            "state_infrastructure_add": [0, 2, 0, 0, 1],
            "goods_good_x": [-4, 0, 1, 0, 2],
            "goods_good_y": [3, 5, 0, 0, 0],
        }
    )


def _tech_frame() -> pd.DataFrame:
    return pd.DataFrame({"key": ["tech_1", "tech_2"], "era": [1, 2]})


def test_synthetic_exact_table() -> None:
    expected = pd.DataFrame(
        {
            "building": ["building_a"] * 4 + ["building_b"],
            "production_method": [
                "pm_a1+pm_m1",
                "pm_a1+pm_m2",
                "pm_a2+pm_m1",
                "pm_a2+pm_m2",
                "pm_b1",
            ],
            "building_group": ["bg_a"] * 5,
            "urbanization": [10.0] * 4 + [0.0],
            "infrastructure_usage_per_level": [1.0, 1.0, -1.0, -1.0, -1.0],
            "era": [1, 1, 2, 2, 0],
            "unlocking_tech": [
                "tech_1",
                "tech_1",
                "tech_1+tech_2",
                "tech_1+tech_2",
                "",
            ],
            "employment": [100, 50, 150, 100, 10],
            "construction_cost": [100, 100, 100, 100, 0],
            "value_goods_inputs_nominal": [30.0, 40.0, 0.0, 0.0, 0.0],
            "value_goods_outputs_nominal": [60.0, 60.0, 110.0, 100.0, 20.0],
            "profit_nominal": [30.0, 20.0, 110.0, 100.0, 20.0],
            "profit_margin_nominal": [0.5, 20.0 / 60.0, 1.0, 1.0, 1.0],
            "profit_per_capita_nominal": [0.3, 0.4, 110.0 / 150.0, 1.0, 2.0],
            "profit_per_construction_cost_nominal": [0.3, 0.2, 1.1, 1.0, np.inf],
            "goods_good_x": [-3, -4, 1, 0, 2],
            "goods_good_y": [3, 3, 5, 5, 0],
            "employment_laborers": [100, 100, 150, 150, 10],
        }
    )

    result = production_table(
        _buildings_frame(), _goods_frame(), _pm_frame(), _tech_frame()
    )
    pd.testing.assert_frame_equal(result, expected)


def test_unknown_tech_raises() -> None:
    df_pm = _pm_frame()
    df_pm.loc[0, "unlocking_technologies"] = "tech_missing"

    with pytest.raises(ValueError, match="Unknown unlocking technology"):
        production_table(_buildings_frame(), _goods_frame(), df_pm, _tech_frame())


def test_missing_goods_column_zero_filled() -> None:
    df_goods = pd.concat(
        [_goods_frame(), pd.DataFrame({"key": ["good_z"], "cost": [5]})],
        ignore_index=True,
    )

    with pytest.warns(UserWarning, match="zero-filled"):
        result = production_table(
            _buildings_frame(), df_goods, _pm_frame(), _tech_frame()
        )

    assert "goods_good_z" in result.columns
    assert (result["goods_good_z"] == 0).all()


def test_missing_state_infrastructure_column_zero_filled() -> None:
    df_pm = _pm_frame().drop(columns="state_infrastructure_add")

    with pytest.warns(UserWarning, match="State-infrastructure column missing"):
        result = production_table(
            _buildings_frame(), _goods_frame(), df_pm, _tech_frame()
        )

    assert (result["infrastructure_usage_per_level"] == [1.0] * 4 + [0.0]).all()


def test_net_infrastructure_usage(df_production: pd.DataFrame) -> None:
    railways = df_production[
        (df_production["building"] == "building_railway")
        & df_production["production_method"].str.startswith("pm_early_trains+")
    ]
    assert (railways["infrastructure_usage_per_level"] == -20).all()

    ports = df_production[
        (df_production["building"] == "building_port")
        & df_production["production_method"].str.startswith("pm_basic_port+")
    ]
    assert (ports["infrastructure_usage_per_level"] == -3).all()

    food = df_production[
        (
            df_production["production_method"]
            == "pm_bakery+pm_disabled_canning+pm_disabled_distillery+pm_manual_dough_processing"
        )
    ]
    assert (food["infrastructure_usage_per_level"] == 1.5).all()


def test_unpriced_goods_column_ignored() -> None:
    df_pm = _pm_frame()
    df_pm["goods_good_w"] = [1, 2, 3, 4, 5]

    with pytest.warns(UserWarning, match="without a base price"):
        result = production_table(
            _buildings_frame(), _goods_frame(), df_pm, _tech_frame()
        )

    assert "goods_good_w" not in result.columns


def test_buildings_without_pmg_string_skipped() -> None:
    df_buildings = _buildings_frame()
    df_buildings.loc[1, "production_method_groups"] = None
    df_buildings.loc[len(df_buildings)] = {
        "key": "building_c",
        "building_group": "bg_a",
        "urbanization": 0.0,
        "infrastructure_usage_per_level": 0.0,
        "required_construction_points": 50.0,
        "production_method_groups": "",
        "unlocking_technologies": None,
    }

    with pytest.warns(UserWarning, match="no production method groups"):
        result = production_table(
            df_buildings, _goods_frame(), _pm_frame(), _tech_frame()
        )

    assert set(result["building"]) == {"building_a"}


def test_pmg_without_methods_skipped() -> None:
    df_buildings = _buildings_frame()
    df_buildings.loc[len(df_buildings)] = {
        "key": "building_d",
        "building_group": "bg_a",
        "urbanization": 0.0,
        "infrastructure_usage_per_level": 0.0,
        "required_construction_points": 50.0,
        "production_method_groups": "pmg_base_a+pmg_ghost",
        "unlocking_technologies": None,
    }
    df_pm = _pm_frame()
    df_pm.loc[len(df_pm)] = {
        "building": "building_d",
        "production_method_group": "pmg_base_a",
        "production_method": "pm_d1",
        "unlocking_technologies": None,
        "employment": 5,
        "employment_laborers": 5,
        "goods_good_x": 0,
        "goods_good_y": 0,
    }

    with pytest.warns(UserWarning, match="no production methods in group pmg_ghost"):
        result = production_table(df_buildings, _goods_frame(), df_pm, _tech_frame())

    assert "building_d" not in set(result["building"])
    assert {"building_a", "building_b"} <= set(result["building"])


def test_empty_buildings_returns_empty_frame() -> None:
    df_buildings = _buildings_frame().iloc[:0]
    goods_cols = [f"goods_{key}" for key in _goods_frame()["key"]]
    profession_cols = [
        col for col in _pm_frame().columns if col.startswith("employment_")
    ]

    result = production_table(df_buildings, _goods_frame(), _pm_frame(), _tech_frame())

    assert result.empty
    assert list(result.columns) == [*META_COLUMNS, *goods_cols, *profession_cols]
