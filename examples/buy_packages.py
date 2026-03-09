from __init__ import THIS_DIR
from vic3_analysis import buy_packages
import os

data = buy_packages()
data.to_csv(os.path.join(THIS_DIR, "..", "tables", "buy_packages.csv"), index=False)
