from __init__ import THIS_DIR
from vic3_analysis import production_analysis
import os

df_optimize_buildings = production_analysis()
df_optimize_buildings.to_csv(
    os.path.join(THIS_DIR, "..", "tables", "production_analysis.csv"), index=False
)
