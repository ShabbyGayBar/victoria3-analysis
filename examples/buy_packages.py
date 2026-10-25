# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Export standard buy packages for an economy with zero building levels."""

import numpy as np

from vic3_analysis import Economy


def main() -> None:
    """Calculate packages from local game data and export default.csv."""
    if __package__:
        from . import ANALYSES_DIR
    else:
        from __init__ import ANALYSES_DIR

    economy = Economy()
    levels = np.zeros(len(economy.building_index), dtype=np.float64)
    state = economy.solve(levels)

    # Standard packages remain defined without workers or market supply.
    # Minimum shares apply first; categories with zero weights use default goods.
    packages = economy.calculate_buy_packages(state)
    output_dir = ANALYSES_DIR / "buy_packages"
    output_dir.mkdir(parents=True, exist_ok=True)
    output_path = output_dir / "default.csv"
    packages.to_csv(output_path, index=True, index_label="wealth", encoding="utf-8")
    print(f"Saved {output_path}")


if __name__ == "__main__":
    main()
