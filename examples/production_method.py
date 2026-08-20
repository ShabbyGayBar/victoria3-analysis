from __init__ import THIS_DIR
from vic3_analysis import production_method

df = production_method()
df.to_csv(THIS_DIR / ".." / "tables" / "production_methods.csv", index=False)
