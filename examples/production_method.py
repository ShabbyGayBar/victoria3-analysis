from __init__ import THIS_DIR
from vic3_analysis import production_method
import os

df = production_method()
df.to_csv(os.path.join(THIS_DIR, "..", "tables", "production_methods.csv"), index=False)
