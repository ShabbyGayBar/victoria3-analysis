import matplotlib

matplotlib.use("Agg")
import matplotlib.pyplot as plt

from __init__ import THIS_DIR
from vic3_analysis import buy_packages

FIGURES_DIR = THIS_DIR / ".." / "figures" / "buy_packages"

data = buy_packages()
data.to_csv(THIS_DIR / ".." / "tables" / "buy_packages.csv", index=False)

FIGURES_DIR.mkdir(parents=True, exist_ok=True)
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
    fig.savefig(str(FIGURES_DIR / f"{column}.svg"))
    plt.close(fig)
    print(f"Saved figures/buy_packages/{column}.svg")
