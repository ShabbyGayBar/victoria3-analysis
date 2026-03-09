from __init__ import THIS_DIR
from vic3_analysis import BuildingsParser
import os
import json

parser = BuildingsParser()
df = parser.to_dataframe()
df.to_csv(os.path.join(THIS_DIR, "..", "tables", "buildings.csv"), index=False)
# json.dump(parser.to_python(), open(os.path.join(THIS_DIR, "..", "tables", "buildings.json"), "w"), indent=4)
