# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Compare nominal supply chains and export every terminal good's reports."""

from __future__ import annotations

import argparse
from collections.abc import Iterable
from pathlib import Path

import matplotlib.pyplot as plt
import numpy as np
import pandas as pd
from matplotlib.figure import Figure
from matplotlib.lines import Line2D
from matplotlib.ticker import MaxNLocator, StrMethodFormatter

if __package__:
    from . import (
        ARTIFACTS_DIR,
        CANGSHULUN_BANNED_PMS,
        CANGSHULUN_BUILDING_LIMITS,
        DATASETS_DIR,
        DEFAULT_BANNED_BGS,
    )
else:
    from __init__ import (
        ARTIFACTS_DIR,
        CANGSHULUN_BANNED_PMS,
        CANGSHULUN_BUILDING_LIMITS,
        DATASETS_DIR,
        DEFAULT_BANNED_BGS,
    )

from vic3_analysis import Economy, Scenario, SupplyChainResult, sweep_supply_chains
from vic3_analysis.analysis.supply_chain.sweep import SWEEP_COLUMNS

NORMALIZED_VALUE = 100_000.0
TEMPLATES = (
    Scenario(
        name="era_3_construction",
        objective="construction_cost",
        banned_building_groups=DEFAULT_BANNED_BGS,
        era_cap=3,
    ),
    Scenario(
        name="era_5_automation",
        objective="automation",
        banned_building_groups=DEFAULT_BANNED_BGS,
        era_cap=5,
    ),
    Scenario(
        name="cangshulun",
        objective="automation",
        banned_building_groups=DEFAULT_BANNED_BGS,
        era_cap=5,
        banned_pms=CANGSHULUN_BANNED_PMS,
        building_limits=CANGSHULUN_BUILDING_LIMITS,
    ),
)
COMPARISON_COLUMNS = [
    "good",
    "configuration",
    "ban_config",
    *SWEEP_COLUMNS[1:],
    "system_gdp_per_capita_annual",
]


def load_economy(datasets_dir: Path) -> Economy:
    """Read each authoritative input CSV once, without parsing game files."""
    tables: dict[str, pd.DataFrame] = {}
    for name in ("production_table", "goods", "pop_types"):
        collection = "production" if name == "production_table" else "parsed"
        path = (datasets_dir / collection / f"{name}.csv").resolve()
        print(f"Input: {path}")
        tables[name] = pd.read_csv(path, encoding="utf-8")
    return Economy(
        df_production=tables["production_table"],
        df_goods=tables["goods"],
        df_pop_types=tables["pop_types"],
    )


def _write_csv(frame: pd.DataFrame, path: Path) -> None:
    path.parent.mkdir(parents=True, exist_ok=True)
    frame.to_csv(path, index=False, encoding="utf-8")
    print(f"Written: {path}")


def _save_figure(figure: Figure, path: Path) -> None:
    try:
        path.parent.mkdir(parents=True, exist_ok=True)
        figure.savefig(path, format="svg", bbox_inches="tight")
        print(f"Written: {path}")
    finally:
        plt.close(figure)


def _export_result(result: SupplyChainResult, output_dir: Path) -> None:
    reports = {
        "goods": result.goods(),
        "processes": result.processes(),
        "flows": result.flows(),
        "workforce": result.workforce(),
        "constraints": result.constraints(),
        "bottlenecks": result.bottlenecks(),
        "alternatives": result.alternatives(),
    }
    for name, frame in reports.items():
        _write_csv(frame, output_dir / f"{name}.csv")
    for view, name in (
        ("allowed", "supply_chain_recipe.mmd"),
        ("realized", "supply_chain_realised.mmd"),
    ):
        path = output_dir / name
        path.write_text(result.to_mermaid(view=view), encoding="utf-8")
        print(f"Written: {path}")
    _save_figure(result.plot_network(metric="value"), output_dir / "network.svg")
    for metric in ("gdp", "employment", "construction_cost"):
        _save_figure(
            result.plot_contributions(metric=metric, scope="chain"),
            output_dir / f"contributions_{metric}.svg",
        )
    _save_figure(result.plot_goods_balance(), output_dir / "goods_balance.svg")
    _save_figure(result.plot_constraints(), output_dir / "constraints.svg")
    workforce = (
        reports["workforce"].groupby("profession", sort=True)["employment"].sum()
    )
    workforce = workforce.sort_values(ascending=False, kind="stable")
    figure, axis = plt.subplots(figsize=(10, 6), layout="constrained")
    if workforce.empty:
        axis.text(0.5, 0.5, "No terminal-chain workforce", ha="center", va="center")
        axis.axis("off")
    else:
        axis.barh(workforce.index[::-1], workforce.to_numpy()[::-1])
        axis.set_xlabel("Employment (workers)")
    axis.set_title(f"{result.terminal_good} chain employment by profession")
    _save_figure(figure, output_dir / "workforce.svg")


def _remove_failed_details(directory: Path) -> None:
    """Remove known detailed exports from a formerly successful configuration."""
    filenames = [
        *(
            f"{name}.csv"
            for name in (
                "goods",
                "processes",
                "flows",
                "workforce",
                "constraints",
                "bottlenecks",
                "alternatives",
            )
        ),
        *(
            f"{name}.svg"
            for name in (
                "network",
                "goods_balance",
                "workforce",
                "constraints",
                "contributions_gdp",
                "contributions_employment",
                "contributions_construction_cost",
            )
        ),
        "supply_chain_recipe.mmd",
        "supply_chain_realised.mmd",
    ]
    for name in filenames:
        (directory / name).unlink(missing_ok=True)


def _comparison_figure(comparison: pd.DataFrame, *, metric: str, label: str) -> Figure:
    """Group bars by good with major good ticks and minor configuration ticks."""
    goods = comparison["good"].drop_duplicates().tolist()
    configurations = comparison["configuration"].drop_duplicates().tolist()
    figure, axis = plt.subplots(
        figsize=(max(11.0, 1.05 * len(goods)), 9.5), layout="constrained"
    )
    if not goods:
        axis.text(0.5, 0.5, "No goods selected", ha="center", va="center")
        axis.axis("off")
        return figure

    successful = pd.DataFrame(comparison.loc[comparison["status"].eq("success")])
    values = successful.pivot(index="good", columns="configuration", values=metric)
    values = values.reindex(index=goods, columns=configurations)
    stride = len(configurations) + 1
    starts = np.arange(len(goods), dtype=float) * stride
    colors = plt.get_cmap("tab10")
    missing = False
    for offset, configuration in enumerate(configurations):
        positions = starts + offset
        heights = np.asarray(values[configuration], dtype=float)
        valid = np.isfinite(heights)
        axis.bar(
            positions[valid],
            heights[valid],
            width=0.8,
            color=colors(offset),
            label=configuration,
        )
        for position in positions[~valid]:
            missing = True
            axis.text(
                float(position),
                0.015,
                "×",
                color="#b91c1c",
                ha="center",
                va="bottom",
                transform=axis.get_xaxis_transform(),
            )

    centers = starts + (len(configurations) - 1) / 2
    axis.set_xticks(centers, goods)
    positions = [
        float(start + offset)
        for start in starts
        for offset in range(len(configurations))
    ]
    axis.xaxis.remove_overlapping_locs = False
    axis.set_xticks(positions, configurations * len(goods), minor=True)
    axis.tick_params(
        axis="x", which="major", labelrotation=90, labelsize=10, pad=95, length=0
    )
    axis.tick_params(
        axis="x", which="minor", labelrotation=90, labelsize=7, pad=3, length=3
    )
    for tick in axis.get_xticklabels():
        tick.set_fontweight("bold")
    for start in starts[1:]:
        axis.axvline(float(start - 1), color="#e5e7eb", linewidth=0.7)
    axis.set_xlim(-0.8, float(starts[-1] + len(configurations) - 0.2))
    axis.set_ylim(bottom=0)
    axis.set_ylabel(label)
    axis.yaxis.set_major_locator(MaxNLocator(nbins=6))
    axis.yaxis.set_major_formatter(StrMethodFormatter("{x:,.0f}"))
    axis.set_axisbelow(True)
    axis.grid(axis="y", alpha=0.25)
    handles, labels = axis.get_legend_handles_labels()
    if missing:
        handles.append(Line2D([], [], color="#b91c1c", marker="x", linestyle="none"))
        labels.append("Failed solve")
    axis.legend(handles, labels, loc="upper right")
    axis.set_title(f"{label} at £{NORMALIZED_VALUE:,.0f} weekly target base value")
    return figure


def _export_comparison(comparison: pd.DataFrame, directory: Path) -> None:
    """Write the combined summary and grouped comparison charts."""
    _write_csv(comparison, directory / "summary.csv")
    for metric, label, filename in (
        ("system_employment", "Population (workers)", "pop.svg"),
        (
            "system_construction_cost",
            "Construction (points)",
            "construction_points.svg",
        ),
        (
            "system_gdp_per_capita_annual",
            "Annual GDP per capita (£/worker/year)",
            "gdp_per_capita.svg",
        ),
    ):
        _save_figure(
            _comparison_figure(comparison, metric=metric, label=label),
            directory / filename,
        )


def run_supply_chain_compare(
    economy: Economy, output_dir: Path, *, goods: Iterable[str] | None = None
) -> pd.DataFrame:
    """Export each good's three configurations, continuing after failed solves.

    Only one detailed result is retained at a time. The complete request is
    validated before any outputs are written.
    """
    selected = list(economy.producible_goods) if goods is None else list(goods)
    if len(selected) != len(set(selected)):
        raise ValueError("goods must not contain duplicates.")
    prices = dict(zip(economy.goods_index, economy.base_prices))
    for good in selected:
        if good not in prices:
            raise ValueError(f"Goods not found in goods index: {good}")
        price = float(prices[good])
        if not 0 < price < float("inf"):
            raise ValueError(f"Good '{good}' must have a positive finite base price.")

    root = output_dir.resolve() / "analyses" / "supply_chains"
    frames: list[pd.DataFrame] = []
    print(
        f"Comparing {len(selected)} goods across {len(TEMPLATES)} configurations; "
        f"weekly target base value £{NORMALIZED_VALUE:,.0f}; autarky."
    )
    for good in selected:
        good_frames: list[pd.DataFrame] = []
        for template in TEMPLATES:
            configuration = template.display_name()
            sweep = sweep_supply_chains(
                economy,
                template,
                goods=[good],
                target_value=NORMALIZED_VALUE,
                keep_results=True,
            )
            frame = sweep.summary
            frame.insert(1, "configuration", configuration)
            frame.insert(
                2, "ban_config", "cangshulun" if configuration == "cangshulun" else ""
            )
            good_frames.append(frame)
            result_dir = root / configuration / good
            if good in sweep.results:
                _export_result(sweep.result_for(good), result_dir)
            else:
                _remove_failed_details(result_dir)
            print(f"{good} / {configuration}: {frame.iloc[0]['status']}")
        frames.append(pd.concat(good_frames, ignore_index=True))

    combined = (
        pd.concat(frames, ignore_index=True)
        if frames
        else pd.DataFrame(columns=COMPARISON_COLUMNS)
    )
    employment = np.asarray(combined["system_employment"], dtype=float)
    combined["system_gdp_per_capita_annual"] = np.divide(
        np.asarray(combined["system_gdp_annual"], dtype=float),
        employment,
        out=np.zeros(len(combined)),
        where=employment != 0,
    )
    for template in TEMPLATES:
        configuration = template.display_name()
        summary = pd.DataFrame(
            combined.loc[combined["configuration"].eq(configuration)]
        )
        _write_csv(summary, root / configuration / "summary.csv")
    _export_comparison(combined, root / "comparison")
    return combined


def main(argv: list[str] | None = None) -> None:
    """Run all producible goods, or a selected set, from the saved datasets."""
    parser = argparse.ArgumentParser(description=__doc__)
    parser.add_argument(
        "--datasets-dir",
        type=Path,
        default=DATASETS_DIR,
        help="Dataset root containing production/ and parsed/ CSVs.",
    )
    parser.add_argument(
        "--output-dir",
        type=Path,
        default=ARTIFACTS_DIR,
        help="Artifact root; exports go beneath analyses/supply_chains/<configuration>/<good>/.",
    )
    parser.add_argument(
        "--goods",
        nargs="+",
        help="Terminal good keys; defaults to all producible goods.",
    )
    args = parser.parse_args(argv)
    run_supply_chain_compare(
        load_economy(args.datasets_dir), args.output_dir, goods=args.goods
    )


if __name__ == "__main__":
    main()
