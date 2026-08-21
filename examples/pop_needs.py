from __init__ import THIS_DIR
from vic3_analysis import PopNeedsParser
import json

parser = PopNeedsParser()
df = parser.to_dataframe()
df.to_csv(THIS_DIR / ".." / "tables" / "pop_needs.csv", index=False)
# json.dump(parser.to_python(), open(THIS_DIR / ".." / "tables" / "pop_needs.json", "w"), indent=4)
