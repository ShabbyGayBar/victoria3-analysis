from __init__ import TABLES_DIR
from vic3_analysis import ProductionMethodParser

parser = ProductionMethodParser()
df = parser.to_dataframe()
df.to_csv(TABLES_DIR / "production_methods.csv", index=False)
