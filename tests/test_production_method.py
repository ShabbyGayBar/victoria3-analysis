from vic3_analysis import ProductionMethodParser


def test_production_method():
    parser = ProductionMethodParser()
    parser.to_dataframe()
