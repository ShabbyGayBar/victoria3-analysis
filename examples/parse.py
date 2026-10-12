# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Export all parsed game tables and buy-package charts."""

from vic3_analysis import (
    BuildingsParser,
    PopNeedsParser,
    PopTypesParser,
    ProductionMethodParser,
    StateRegionsParser,
    buy_packages,
    goods,
    technology,
)


def main() -> None:
    """Generate the eight parsed CSVs and linear/log-scale buy-package SVGs."""
    if __package__:
        from . import FIGURES_DIR, TABLES_DIR
    else:
        from __init__ import FIGURES_DIR, TABLES_DIR

    import matplotlib

    matplotlib.use("Agg")
    import matplotlib.pyplot as plt

    BuildingsParser().to_dataframe().to_csv(TABLES_DIR / "buildings.csv", index=False)
    goods().to_csv(TABLES_DIR / "goods.csv", index=False)
    ProductionMethodParser().to_dataframe().to_csv(
        TABLES_DIR / "production_methods.csv", index=False
    )
    PopTypesParser().to_dataframe().to_csv(TABLES_DIR / "pop_types.csv", index=False)
    PopNeedsParser().to_dataframe().to_csv(TABLES_DIR / "pop_needs.csv", index=False)
    StateRegionsParser().to_dataframe().to_csv(
        TABLES_DIR / "state_regions.csv", index=False
    )
    technology().to_csv(TABLES_DIR / "technology.csv", index=False)
    data = buy_packages()
    data.to_csv(TABLES_DIR / "buy_packages.csv", index=False)

    figures_dir = FIGURES_DIR / "buy_packages"
    figures_dir.mkdir(parents=True, exist_ok=True)
    wealth = data["wealth"].to_numpy()
    for column in data.columns:
        if column == "wealth":
            continue
        fig, ax = plt.subplots(figsize=(8, 5))
        ax.plot(wealth, data[column].to_numpy(), marker="o", markersize=3, linewidth=1)
        ax.grid()
        ax.set_xlabel("Wealth")
        ax.set_ylabel(column)
        ax.set_title(f"{column} vs wealth")
        fig.tight_layout()
        figure_path = figures_dir / f"{column}.svg"
        fig.savefig(figure_path)
        print(f"Saved {figure_path}")

        ax.set_yscale("log")
        log_figure_path = figures_dir / f"{column}_log.svg"
        fig.savefig(log_figure_path)
        print(f"Saved {log_figure_path}")

        plt.close(fig)


if __name__ == "__main__":
    main()
