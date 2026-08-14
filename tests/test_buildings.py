from vic3_analysis import BuildingsParser

def test_buildings():
    parser = BuildingsParser()
    df = parser.to_dataframe()
    building_groups = parser.building_groups()
