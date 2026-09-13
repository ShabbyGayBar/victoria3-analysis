from vic3_analysis import technology


def test_technology():
    frame = technology(language="english")
    assert list(frame.columns[:2]) == ["key", "key_localization"]
    assert str(frame["key_localization"].dtype) == "string"
    row = frame[frame["key"] == "mechanical_tools"].iloc[0]
    assert row["key_localization"] == "Mechanical Tools"
