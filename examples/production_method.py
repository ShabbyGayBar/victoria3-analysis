from __init__ import THIS_DIR
from vic3_analysis import ProductionMethodParser

parser = ProductionMethodParser()
df = parser.to_dataframe()
df.to_csv(THIS_DIR / ".." / "tables" / "production_methods.csv", index=False)
