import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from __init__ import FIGURES_DIR, TABLES_DIR
from vic3_analysis import buy_packages

BUY_PACKAGES_FIGURES_DIR = FIGURES_DIR / "buy_packages"

data = buy_packages()
data.to_csv(TABLES_DIR / "buy_packages.csv", index=False)

BUY_PACKAGES_FIGURES_DIR.mkdir(parents=True, exist_ok=True)
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
    fig.savefig(str(BUY_PACKAGES_FIGURES_DIR / f"{column}.svg"))
    plt.close(fig)
    print(f"Saved figures/buy_packages/{column}.svg")
