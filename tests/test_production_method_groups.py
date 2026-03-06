from . import THIS_DIR
from vic3_analysis import production_method_groups
import os

def test_production_method_groups():
    df = production_method_groups()
