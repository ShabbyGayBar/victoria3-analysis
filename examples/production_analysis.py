import pandas as pd
from __init__ import TABLES_DIR

from vic3_analysis import production_table

df_buildings = pd.read_csv(TABLES_DIR / "buildings.csv")
df_goods = pd.read_csv(TABLES_DIR / "goods.csv")
df_pm = pd.read_csv(TABLES_DIR / "production_methods.csv")
df_tech = pd.read_csv(TABLES_DIR / "technology.csv")
df_pop_types = pd.read_csv(TABLES_DIR / "pop_types.csv")

df_production_table = production_table(
    df_buildings, df_goods, df_pm, df_tech, df_pop_types
)
df_production_table.to_csv(TABLES_DIR / "production_table.csv", index=False)
