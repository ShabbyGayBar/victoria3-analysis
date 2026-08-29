from vic3_analysis import PopTypesParser


def test_pop_types():
    parser = PopTypesParser()
    parser.to_dataframe()
    parser.flags()
