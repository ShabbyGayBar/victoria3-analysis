from __init__ import THIS_DIR
from vic3_analysis import technology
import os

df = technology()
df.to_csv(os.path.join(THIS_DIR, "..", "tables", "technology.csv"), index=False)
