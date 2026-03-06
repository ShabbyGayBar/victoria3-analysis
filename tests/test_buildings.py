from email import parser

from . import THIS_DIR
from vic3_analysis import BuildingsParser
import os
import json

def test_buildings():
    parser = BuildingsParser()
    df = parser.to_dataframe()
