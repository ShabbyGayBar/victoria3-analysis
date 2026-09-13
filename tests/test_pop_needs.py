from vic3_analysis import PopNeedsParser


def test_pop_needs():
    parser = PopNeedsParser()
    frame = parser.to_dataframe(language="english")
    assert list(frame.columns[:2]) == ["key", "key_localization"]
    assert str(frame["key_localization"].dtype) == "string"
    row = frame[frame["key"] == "popneed_basic_food"].iloc[0]
    assert row["key_localization"] == "Basic Food"
