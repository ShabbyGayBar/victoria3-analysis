from __init__ import THIS_DIR
from vic3_analysis import technology

df = technology()
df.to_csv(THIS_DIR / ".." / "tables" / "technology.csv", index=False)
