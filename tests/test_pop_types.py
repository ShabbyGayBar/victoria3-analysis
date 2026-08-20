from vic3_analysis import PopTypesParser


def test_pop_types():
    parser = PopTypesParser()
    df = parser.to_dataframe()
    flags = parser.flags()
