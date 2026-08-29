from vic3_analysis import StateRegionsParser


def test_buildings():
    parser = StateRegionsParser()
    parser.to_dataframe()
