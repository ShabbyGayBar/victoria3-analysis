from vic3_analysis import PopNeedsParser


def test_pop_needs():
    parser = PopNeedsParser()
    parser.to_dataframe()
