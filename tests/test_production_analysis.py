from . import THIS_DIR
from vic3_analysis import production_analysis
import os

def test_production_analysis():
    df_optimize_buildings = production_analysis()