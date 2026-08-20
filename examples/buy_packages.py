from __init__ import THIS_DIR
from vic3_analysis import buy_packages

data = buy_packages()
data.to_csv(THIS_DIR / ".." / "tables" / "buy_packages.csv", index=False)
