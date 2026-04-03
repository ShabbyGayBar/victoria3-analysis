from __init__ import THIS_DIR
from vic3_analysis import StateRegionsParser
import os
import json

parser = StateRegionsParser()
df = parser.to_dataframe()
df.to_csv(os.path.join(THIS_DIR, "..", "tables", "state_regions.csv"), index=False)
# json.dump(parser.to_python(), open(os.path.join(THIS_DIR, "..", "tables", "state_regions.json"), "w"), indent=4)
