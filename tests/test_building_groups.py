import pytest
from pyradox import Tree

from vic3_analysis import BuildingGroupParser
from vic3_analysis.parse.building_groups import _inherit_attr, _join_group_attrs


def test_building_groups_to_dataframe():
    parser = BuildingGroupParser()
    df = parser.to_dataframe()
    assert "key" in df.columns
    for col in (
        "category",
        "land_usage",
        "economy_of_scale",
        "cash_reserves_max",
        "parent_group",
    ):
        assert col in df.columns
    # bg_manufacturing is a top-level group with several scalar attrs
    row = df[df["key"] == "bg_manufacturing"].iloc[0]
    assert row["category"] == "urban"
    assert row["economy_of_scale"] is True
    assert row["cash_reserves_max"] == 25000


def test_resolved_attributes_inheritance():
    parser = BuildingGroupParser()
    resolved = parser.resolved_attributes()
    # bg_staple_crops has no land_usage; inherits "rural" from bg_agriculture
    assert "land_usage" not in parser._group_to_python(
        "bg_staple_crops", parser["bg_staple_crops"]
    )
    assert resolved["bg_staple_crops"]["land_usage"] == "rural"
    # bg_subsistence_agriculture sets cash_reserves_max=0; inherits 25000
    assert resolved["bg_subsistence_agriculture"]["cash_reserves_max"] == 25000
    # bg_agriculture itself has land_usage set; no inheritance needed
    assert resolved["bg_agriculture"]["land_usage"] == "rural"


def test_group_to_python_dict_and_scalar():
    parser = BuildingGroupParser()
    assert parser._group_to_python("x", {"a": 1}) == {"a": 1}
    assert parser._group_to_python("x", "scalar") == {}


def test_to_dataframe_list_value():
    parser = BuildingGroupParser()
    sub = Tree()
    sub.append("dummy_grouped", "x", in_group=True)
    sub.append("dummy_grouped", "y", in_group=True)
    parser.append("bg_synthetic_list", sub)
    df = parser.to_dataframe()
    row = df[df["key"] == "bg_synthetic_list"].iloc[0]
    assert row["dummy_grouped"] == "x+y"


# --- _inherit_attr synthetic tests ---


def test_inherit_attr_found_in_parent():
    raw = {
        "child": {"parent_group": "parent"},
        "parent": {"land_usage": "rural"},
    }
    assert _inherit_attr("child", raw, "land_usage") == "rural"


def test_inherit_attr_recurse_via_missing():
    raw = {
        "child": {"parent_group": "mid"},
        "mid": {"parent_group": "root"},
        "root": {"land_usage": "urban"},
    }
    assert _inherit_attr("child", raw, "land_usage") == "urban"


def test_inherit_attr_parent_not_in_raw():
    raw = {"child": {"parent_group": "missing"}}
    assert _inherit_attr("child", raw, "land_usage") is None


def test_inherit_attr_cycle():
    raw = {
        "a": {"parent_group": "b"},
        "b": {"parent_group": "a"},
    }
    # a -> b -> a (cycle) should not infinite-loop; returns None
    assert _inherit_attr("a", raw, "land_usage") is None


def test_inherit_attr_skip_zero():
    raw = {
        "child": {"parent_group": "parent"},
        "parent": {"parent_group": "grandparent", "cash_reserves_max": 0},
        "grandparent": {"cash_reserves_max": 25000},
    }
    assert _inherit_attr("child", raw, "cash_reserves_max", skip_zero=True) == 25000


def test_inherit_attr_skip_zero_finds_zero_parent():
    # Without skip_zero, the parent's 0 is returned directly
    raw = {
        "child": {"parent_group": "parent"},
        "parent": {"cash_reserves_max": 0},
    }
    assert _inherit_attr("child", raw, "cash_reserves_max", skip_zero=False) == 0


def test_inherit_attr_group_not_in_raw():
    assert _inherit_attr("absent", {}, "land_usage") is None


def test_inherit_attr_parent_not_str():
    raw = {"child": {"parent_group": 42}}
    assert _inherit_attr("child", raw, "land_usage") is None


def test_inherit_attr_no_parent_key():
    raw = {"child": {"land_usage": "rural"}}
    assert _inherit_attr("child", raw, "land_usage") is None


# --- _join_group_attrs synthetic tests ---


def test_join_group_attrs_basic():
    rows = [{"key": "b1", "building_group": "bg_x"}]
    attrs = {"bg_x": {"category": "urban", "urbanization": 20}}
    _join_group_attrs(rows, attrs)
    assert rows[0]["category"] == "urban"
    assert rows[0]["urbanization"] == 20


def test_join_group_attrs_collision_prefix():
    rows = [{"key": "b1", "building_group": "bg_x", "category": "existing"}]
    attrs = {"bg_x": {"category": "urban"}}
    _join_group_attrs(rows, attrs)
    assert rows[0]["category"] == "existing"
    assert rows[0]["building_group_category"] == "urban"


def test_join_group_attrs_missing_group_warns():
    rows = [{"key": "b1", "building_group": "bg_unknown"}]
    with pytest.warns(UserWarning, match="unknown building group"):
        _join_group_attrs(rows, {})


def test_join_group_attrs_no_building_group():
    rows = [{"key": "b1"}]
    _join_group_attrs(rows, {"bg_x": {"category": "urban"}})
    assert rows[0] == {"key": "b1"}


def test_join_group_attrs_list_and_nested():
    rows = [{"key": "b1", "building_group": "bg_x"}]
    attrs = {
        "bg_x": {
            "lens": ["a", "b"],
            "should_auto_expand": {"trigger": "yes"},  # nested dict -> skipped
        }
    }
    _join_group_attrs(rows, attrs)
    assert rows[0]["lens"] == "a+b"
    assert "should_auto_expand" not in rows[0]
