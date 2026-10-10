# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

from __init__ import TABLES_DIR

from vic3_analysis import goods

df = goods()
df.to_csv(TABLES_DIR / "goods.csv", index=False)
