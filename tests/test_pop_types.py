from vic3_analysis import PopTypesParser


def test_pop_types():
    parser = PopTypesParser()
    frame = parser.to_dataframe(language="english")
    assert list(frame.columns[:2]) == ["key", "key_localization"]
    assert str(frame["key_localization"].dtype) == "string"
    row = frame[frame["key"] == "laborers"].iloc[0]
    assert row["key_localization"] == "@laborers! $laborers_no_icon$"
    parser.flags()
