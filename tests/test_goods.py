from vic3_analysis import goods


def test_goods():
    frame = goods(language="english")
    assert list(frame.columns[:2]) == ["key", "key_localization"]
    assert str(frame["key_localization"].dtype) == "string"
    row = frame[frame["key"] == "steel"].iloc[0]
    assert row["key_localization"] == "Steel"
