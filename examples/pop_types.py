from __init__ import TABLES_DIR
from vic3_analysis import PopTypesParser

parser = PopTypesParser()
df = parser.to_dataframe()
df.to_csv(TABLES_DIR / "pop_types.csv", index=False)
# json.dump(parser.to_python(), open(TABLES_DIR / "pop_types.json", "w"), indent=4)
