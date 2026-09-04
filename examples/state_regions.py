from __init__ import TABLES_DIR
from vic3_analysis import StateRegionsParser

parser = StateRegionsParser()
df = parser.to_dataframe()
df.to_csv(TABLES_DIR / "state_regions.csv", index=False)
# json.dump(parser.to_python(), open(TABLES_DIR / "state_regions.json", "w"), indent=4)
