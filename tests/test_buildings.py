from vic3_analysis import BuildingsParser


def test_buildings():
    parser = BuildingsParser()
    parser.to_dataframe()
    parser.building_groups()


def test_buildings_group_attr_columns():
    parser = BuildingsParser()
    df = parser.to_dataframe()
    # Resolved group attributes are joined under their raw names (no prefix in
    # vanilla, since none collide with building-level columns).
    for col in (
        "category",
        "land_usage",
        "economy_of_scale",
        "cash_reserves_max",
        "urbanization",
        "parent_group",
        "is_subsistence",
    ):
        assert col in df.columns, f"missing joined column {col!r}"
    # No prefixed variants should exist in vanilla data.
    for col in (
        "building_group_category",
        "building_group_land_usage",
        "building_group_economy_of_scale",
    ):
        assert col not in df.columns, f"unexpected prefixed column {col!r}"
    # A building in bg_light_industry should carry its group's urbanization and
    # inherited cash_reserves_max (from bg_manufacturing). category is NOT
    # inherited so it stays NaN for child groups like bg_light_industry.
    row = df[df["key"] == "building_food_industry"].iloc[0]
    assert row["building_group"] == "bg_light_industry"
    assert row["urbanization"] == 20
    assert row["parent_group"] == "bg_manufacturing"
    assert row["cash_reserves_max"] == 25000
