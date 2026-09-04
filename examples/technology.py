from __init__ import TABLES_DIR
from vic3_analysis import technology

df = technology()
df.to_csv(TABLES_DIR / "technology.csv", index=False)
