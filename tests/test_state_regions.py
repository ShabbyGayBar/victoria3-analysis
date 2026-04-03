from vic3_analysis import StateRegionsParser

def test_buildings():
    parser = StateRegionsParser()
    df = parser.to_dataframe()
    
