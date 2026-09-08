"""
Parser for Victoria 3 pop needs definitions.

Reads pop need data from common/pop_needs and exposes it as a
pyradox.Tree subclass with helper methods for DataFrame conversion.
"""

from pathlib import Path
from typing import Any

import pandas as pd
from pyradox import Tree

from vic3_analysis import get_vic3_directory, parse_merge


class PopNeedsParser(Tree):
    """Parser for Victoria 3 pop need definitions."""

    def __init__(self, game_dir: str | Path | None = None):
        """Initialise and populate the pop-needs tree.

        Args:
            game_dir: Path to the Victoria 3 ``game`` directory. If ``None``,
                locate the directory automatically.
        """
        super().__init__()

        if game_dir is None:
            game_dir = get_vic3_directory()

        parse_dir = Path(game_dir) / "common" / "pop_needs"
        parse_tree = parse_merge(parse_dir)

        self.update(parse_tree)

    def to_dataframe(self) -> pd.DataFrame:
        """Convert the pop-needs tree to a flat ``pandas.DataFrame``.

        Returns:
            A ``DataFrame`` with one row per pop need entry.  Columns include
            ``"key"`` (the pop need type), ``"goods"``, ``"weight"``,
            ``"max_supply_share"``, ``"min_supply_share"``, and ``"is_default"``.
        """

        results: list[dict[str, Any]] = []

        for pop_need_type, pop_need_values in self.items():
            if isinstance(pop_need_values, Tree):
                py = pop_need_values.to_python()
            elif isinstance(pop_need_values, dict):
                py = pop_need_values
            else:
                continue

            default_good = py.get("default")

            entries = py.get("entry")
            if entries is None:
                # A pop need type must have at least one entry
                raise ValueError(f"Pop need type '{pop_need_type}' has no entries.")

            # normalize single entry vs multiple entries
            if not isinstance(entries, list):
                entries = [entries]

            for entry in entries:
                if not isinstance(entry, dict):
                    continue

                goods = entry.get("goods")

                results.append(
                    {
                        "key": pop_need_type,
                        "goods": goods,
                        "weight": entry.get("weight", 1),
                        "max_supply_share": entry.get("max_supply_share", 1),
                        "min_supply_share": entry.get("min_supply_share", 0),
                        "is_default": goods == default_good,
                    }
                )

        return pd.DataFrame(
            results,
            columns=[
                "key",
                "goods",
                "weight",
                "max_supply_share",
                "min_supply_share",
                "is_default",
            ],
        )
