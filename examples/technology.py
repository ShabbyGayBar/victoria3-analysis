# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

from __init__ import TABLES_DIR

from vic3_analysis import technology

df = technology()
df.to_csv(TABLES_DIR / "technology.csv", index=False)
