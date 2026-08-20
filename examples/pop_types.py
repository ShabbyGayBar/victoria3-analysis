from __init__ import THIS_DIR
from vic3_analysis import PopTypesParser
import json

parser = PopTypesParser()
df = parser.to_dataframe()
df.to_csv(THIS_DIR / ".." / "tables" / "pop_types.csv", index=False)
# json.dump(parser.to_python(), open(THIS_DIR / ".." / "tables" / "pop_types.json", "w"), indent=4)
