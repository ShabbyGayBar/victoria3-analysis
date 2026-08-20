from __init__ import THIS_DIR
from vic3_analysis import goods

df = goods()
df.to_csv(THIS_DIR / ".." / "tables" / "goods.csv", index=False)
