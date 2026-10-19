# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

import pandas as pd

if __package__:
    from . import PARSED_DIR, PRODUCTION_DIR
else:
    from __init__ import PARSED_DIR, PRODUCTION_DIR

from vic3_analysis import production_table

df_buildings = pd.read_csv(PARSED_DIR / "buildings.csv")
df_goods = pd.read_csv(PARSED_DIR / "goods.csv")
df_pm = pd.read_csv(PARSED_DIR / "production_methods.csv")
df_tech = pd.read_csv(PARSED_DIR / "technology.csv")
df_pop_types = pd.read_csv(PARSED_DIR / "pop_types.csv")

df_production_table = production_table(
    df_buildings, df_goods, df_pm, df_tech, df_pop_types
)
PRODUCTION_DIR.mkdir(parents=True, exist_ok=True)
df_production_table.to_csv(PRODUCTION_DIR / "production_table.csv", index=False)
