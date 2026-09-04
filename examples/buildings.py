from __init__ import TABLES_DIR
from vic3_analysis import BuildingsParser

parser = BuildingsParser()
df = parser.to_dataframe()
df.to_csv(TABLES_DIR / "buildings.csv", index=False)
# json.dump(parser.to_python(), open(TABLES_DIR / "buildings.json", "w"), indent=4)
