from __init__ import THIS_DIR
from vic3_analysis import goods
import os

df = goods()
df.to_csv(os.path.join(THIS_DIR, "..", "tables", "goods.csv"), index=False)
