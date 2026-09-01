import pandas as pd

from vic3_analysis import production_table

from __init__ import THIS_DIR

df_buildings = pd.read_csv(THIS_DIR / ".." / "tables" / "buildings.csv")
df_goods = pd.read_csv(THIS_DIR / ".." / "tables" / "goods.csv")
df_pm = pd.read_csv(THIS_DIR / ".." / "tables" / "production_methods.csv")
df_tech = pd.read_csv(THIS_DIR / ".." / "tables" / "technology.csv")

df_production_table = production_table(df_buildings, df_goods, df_pm, df_tech)
df_production_table.to_csv(
    THIS_DIR / ".." / "tables" / "production_table.csv", index=False
)
