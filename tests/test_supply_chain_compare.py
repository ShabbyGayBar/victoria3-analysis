# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Exercise per-good comparison exports with exactly solvable economies."""

from pathlib import Path
from xml.etree import ElementTree

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
import pytest

from examples.supply_chain_compare import (
    COMPARISON_COLUMNS,
    TEMPLATES,
    _comparison_figure,
    load_economy,
    main,
    run_supply_chain_compare,
)
from vic3_analysis import Economy


def _economy(*, zero_employment: bool = False) -> Economy:
    """Two auto technologies trade employment for construction; future is era 6."""
    employment = [0.0] * 3 if zero_employment else [1.0, 4.0, 1.0]
    return Economy(
        df_production=pd.DataFrame(
            {
                "building": [
                    "building_auto_fast",
                    "building_auto_manual",
                    "building_future",
                ],
                "production_method": ["pm_fast", "pm_manual", "pm_future"],
                "era": [5, 3, 6],
                "employment": employment,
                "employment_laborers": employment,
                "construction_cost": [4.0, 1.0, 1.0],
                "goods_automobiles": [100.0, 100.0, 0.0],
                "goods_future": [0.0, 0.0, 100.0],
                "building_group": ["bg_manufacturing"] * 3,
            }
        ),
        df_goods=pd.DataFrame(
            {"key": ["automobiles", "future"], "cost": [100.0, 100.0]}
        ),
        df_pop_types=pd.DataFrame(
            {"key": ["laborers"], "start_quality_of_life": [10.0]}
        ),
    )


def _root(output: Path) -> Path:
    return output / "analyses" / "supply_chains"


def test_tradeoffs_failures_and_per_good_exports(tmp_path: Path) -> None:
    initial_figures = plt.get_fignums()
    comparison = run_supply_chain_compare(_economy(), tmp_path)
    assert list(comparison.columns) == COMPARISON_COLUMNS
    assert comparison["good"].tolist() == ["automobiles"] * 3 + ["future"] * 3
    configurations = [template.display_name() for template in TEMPLATES]
    assert configurations == ["era_3_construction", "era_5_automation", "cangshulun"]
    assert comparison["configuration"].tolist() == configurations * 2
    assert comparison["status"].tolist() == ["success"] * 3 + ["failure"] * 3
    assert comparison["target_quantity"].tolist() == [1000.0] * 6
    cases = comparison.loc[comparison["good"].eq("automobiles")].set_index(
        "configuration"
    )
    assert cases.loc["era_3_construction", "system_employment"] == pytest.approx(40.0)
    assert cases.loc["era_3_construction", "system_construction_cost"] == pytest.approx(
        10.0
    )
    assert cases.loc["era_5_automation", "system_employment"] == pytest.approx(10.0)
    assert cases.loc["era_5_automation", "system_construction_cost"] == pytest.approx(
        40.0
    )
    assert cases.loc["cangshulun", "ban_config"] == "cangshulun"
    np.testing.assert_allclose(
        cases["system_gdp_per_capita_annual"], [130_000.0, 520_000.0, 520_000.0]
    )
    assert (
        comparison.loc[
            comparison["status"].eq("failure"), "system_gdp_per_capita_annual"
        ]
        .isna()
        .all()
    )
    assert (
        comparison.loc[comparison["good"].eq("future"), "system_employment"]
        .isna()
        .all()
    )

    csv_names = {
        "goods",
        "processes",
        "flows",
        "workforce",
        "constraints",
        "bottlenecks",
        "alternatives",
    }
    svg_names = {
        "network",
        "contributions_gdp",
        "contributions_employment",
        "contributions_construction_cost",
        "goods_balance",
        "workforce",
        "constraints",
    }
    for configuration in configurations:
        directory = _root(tmp_path) / configuration / "automobiles"
        assert {path.stem for path in directory.glob("*.csv")} == csv_names
        assert {path.stem for path in directory.glob("*.svg")} == svg_names
        for name in ("supply_chain_recipe.mmd", "supply_chain_realised.mmd"):
            assert (
                (directory / name)
                .read_text(encoding="utf-8")
                .startswith("flowchart LR")
            )
        assert pd.read_csv(directory / "alternatives.csv")["config"].nunique() == (
            1 if configuration == "era_3_construction" else 2
        )
        failure_dir = _root(tmp_path) / configuration / "future"
        assert not failure_dir.exists()
        failure = comparison.loc[
            comparison["good"].eq("future")
            & comparison["configuration"].eq(configuration)
        ].iloc[0]
        assert failure["error_type"] == "ValueError"
        assert "infeasible" in str(failure["error_message"]).lower()

    assert {path.name for path in (_root(tmp_path) / "comparison").iterdir()} == {
        "summary.csv",
        "pop.svg",
        "construction_points.svg",
        "gdp_per_capita.svg",
    }
    saved = pd.read_csv(_root(tmp_path) / "comparison/summary.csv")
    pd.testing.assert_frame_equal(
        saved.fillna(""), comparison.fillna(""), check_dtype=False
    )
    for configuration in configurations:
        saved = pd.read_csv(_root(tmp_path) / configuration / "summary.csv")
        expected = comparison.loc[
            comparison["configuration"].eq(configuration)
        ].reset_index(drop=True)
        pd.testing.assert_frame_equal(
            saved.fillna(""), expected.fillna(""), check_dtype=False
        )
    assert not list(_root(tmp_path).glob("*/*/summary.csv"))
    for path in _root(tmp_path).rglob("*.csv"):
        assert not path.read_bytes().startswith(b"\xef\xbb\xbf")
    for path in _root(tmp_path).rglob("*.svg"):
        assert (
            ElementTree.parse(path).getroot().tag == "{http://www.w3.org/2000/svg}svg"
        )
    assert plt.get_fignums() == initial_figures
    assert {path.name for path in _root(tmp_path).iterdir()} == {
        "era_3_construction",
        "era_5_automation",
        "cangshulun",
        "comparison",
    }


def test_empty_workforce_and_bottlenecks(tmp_path: Path) -> None:
    comparison = run_supply_chain_compare(
        _economy(zero_employment=True), tmp_path, goods=["automobiles"]
    )
    assert (comparison["system_gdp_per_capita_annual"] == 0).all()
    directory = _root(tmp_path) / "era_5_automation/automobiles"
    assert pd.read_csv(directory / "workforce.csv").empty
    assert pd.read_csv(directory / "bottlenecks.csv").empty
    assert not list(_root(tmp_path).glob("*/future"))


def test_cli_reads_inputs_and_selects_goods(
    tmp_path: Path, capsys: pytest.CaptureFixture[str]
) -> None:
    economy = _economy()
    datasets = tmp_path / "inputs"
    for collection, name, frame in (
        ("production", "production_table", economy.df_production),
        ("parsed", "goods", economy.df_goods),
        ("parsed", "pop_types", economy.df_pop_types),
    ):
        directory = datasets / collection
        directory.mkdir(parents=True, exist_ok=True)
        frame.to_csv(directory / f"{name}.csv", index=False, encoding="utf-8")
    pd.testing.assert_frame_equal(
        load_economy(datasets).df_production, economy.df_production, check_dtype=False
    )
    output = tmp_path / "output"
    main(
        [
            "--datasets-dir",
            str(datasets),
            "--output-dir",
            str(output),
            "--goods",
            "automobiles",
        ]
    )
    assert (_root(output) / "comparison/summary.csv").is_file()
    assert not list(_root(output).glob("*/future"))
    assert str((datasets / "parsed/goods.csv").resolve()) in capsys.readouterr().out


@pytest.mark.parametrize(
    "goods, message",
    [(["automobiles", "automobiles"], "duplicates"), (["unknown"], "not found")],
)
def test_invalid_selection_fails_before_export(
    tmp_path: Path, goods: list[str], message: str
) -> None:
    with pytest.raises(ValueError, match=message):
        run_supply_chain_compare(_economy(), tmp_path, goods=goods)
    assert not (tmp_path / "analyses").exists()


@pytest.mark.parametrize("price", [0.0, -1.0, float("nan"), float("inf")])
def test_invalid_base_price_fails_before_export(tmp_path: Path, price: float) -> None:
    original = _economy()
    goods = original.df_goods.copy()
    goods.loc[goods["key"].eq("automobiles"), "cost"] = price
    economy = Economy(
        df_production=original.df_production,
        df_goods=goods,
        df_pop_types=original.df_pop_types,
    )
    with pytest.raises(ValueError, match="positive finite base price"):
        run_supply_chain_compare(economy, tmp_path)
    assert not (tmp_path / "analyses").exists()


def test_empty_selection_writes_fixed_schema(tmp_path: Path) -> None:
    comparison = run_supply_chain_compare(_economy(), tmp_path, goods=[])
    assert comparison.empty
    assert (
        list(pd.read_csv(_root(tmp_path) / "comparison/summary.csv").columns)
        == COMPARISON_COLUMNS
    )
    for template in TEMPLATES:
        summary = pd.read_csv(_root(tmp_path) / template.display_name() / "summary.csv")
        assert summary.empty
        assert list(summary.columns) == COMPARISON_COLUMNS


def test_failed_rerun_removes_previous_details(tmp_path: Path) -> None:
    economy = _economy()
    run_supply_chain_compare(economy, tmp_path, goods=["automobiles"])
    production = economy.df_production.copy()
    production["era"] = 6
    unavailable = Economy(
        df_production=production,
        df_goods=economy.df_goods,
        df_pop_types=economy.df_pop_types,
    )
    directory = _root(tmp_path) / "era_5_automation/automobiles"
    (directory / "notes.txt").write_text("Keep my notes", encoding="utf-8")
    comparison = run_supply_chain_compare(unavailable, tmp_path, goods=["automobiles"])
    assert comparison["status"].tolist() == ["failure"] * 3
    for template in TEMPLATES:
        directory = _root(tmp_path) / template.display_name() / "automobiles"
        assert {path.name for path in directory.iterdir()} == (
            {"notes.txt"} if template.name == "era_5_automation" else set()
        )


@pytest.mark.parametrize(
    "metric,label,scale",
    [
        ("system_employment", "Population (workers)", 1.0),
        ("system_construction_cost", "Construction (points)", 10.0),
        ("system_gdp_per_capita_annual", "Annual GDP per capita (£/worker/year)", 52.0),
    ],
)
def test_comparison_chart_groups_goods_and_marks_failures(
    metric: str, label: str, scale: float
) -> None:
    configurations = [template.display_name() for template in TEMPLATES]
    rows = []
    for good, base in (("automobiles", 0.0), ("future", float("nan")), ("steel", 30.0)):
        for offset, configuration in enumerate(configurations):
            rows.append(
                {
                    "good": good,
                    "configuration": configuration,
                    "status": "failure" if good == "future" else "success",
                    metric: (base + offset * 10.0) * scale,
                }
            )
    figure = _comparison_figure(pd.DataFrame(rows), metric=metric, label=label)
    try:
        axis = figure.axes[0]
        assert [tick.get_text() for tick in axis.get_xticklabels()] == [
            "automobiles",
            "future",
            "steel",
        ]
        assert [
            tick.get_text() for tick in axis.get_xticklabels(minor=True)
        ] == configurations * 3
        np.testing.assert_allclose(axis.get_xticks(), [1.0, 5.0, 9.0])
        np.testing.assert_allclose(
            axis.get_xticks(minor=True), [0, 1, 2, 4, 5, 6, 8, 9, 10]
        )
        heights = [
            bar.get_height() for container in axis.containers for bar in container
        ]
        np.testing.assert_allclose(heights, np.array([0, 30, 10, 40, 20, 50]) * scale)
        failures = [text for text in axis.texts if text.get_text() == "×"]
        assert sorted(text.get_position()[0] for text in failures) == [4, 5, 6]
        assert axis.get_ylabel() == label
    finally:
        plt.close(figure)
