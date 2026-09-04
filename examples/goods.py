from __init__ import TABLES_DIR
from vic3_analysis import goods

df = goods()
df.to_csv(TABLES_DIR / "goods.csv", index=False)
