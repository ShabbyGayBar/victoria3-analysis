from __init__ import THIS_DIR
from vic3_analysis import production_table
import os

df_production_table = production_table()
df_production_table.to_csv(
    os.path.join(THIS_DIR, "..", "tables", "production_table.csv"), index=False
)
