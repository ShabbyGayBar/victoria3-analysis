from pathlib import Path

import pandas as pd
import pytest

from vic3_analysis import localization


def _write(root: Path, relative: str, content: str) -> None:
    path = root / "localization" / "english" / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8-sig")


def test_localization_preserves_raw_values_and_sorts(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "z_values_l_english.yml",
        'l_english:\n zed:0 "old"\n raw: "This $foo$ @icon! [GetName]\\nline" # note\n',
    )
    _write(tmp_path, "a_values_l_english.yml", 'l_english:\n zed: "new"\n')
    frame = localization("english", tmp_path)
    expected = pd.DataFrame(
        {
            "key": ["raw", "zed"],
            "localization": ["This $foo$ @icon! [GetName]\\nline", "new"],
        },
        dtype="string",
    )
    pd.testing.assert_frame_equal(frame, expected)


def test_replace_and_duplicate_precedence(tmp_path: Path) -> None:
    _write(tmp_path, "z_values_l_english.yml", 'key: "ordinary"\n')
    _write(
        tmp_path, "replace/a_values_l_english.yml", 'key: "replacement"\nkey: "last"\n'
    )
    assert localization("english", tmp_path).loc[0, "localization"] == "last"


def test_malformed_entries_warn_with_location(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "values_l_english.yml",
        'l_english:\nnot valid\nunterminated: "value\nvalid: "yes"\n',
    )
    with pytest.warns(UserWarning, match=r"values_l_english\.yml:[23]"):
        frame = localization("english", tmp_path)
    assert frame["key"].tolist() == ["valid"]


def test_invalid_or_unknown_language(tmp_path: Path) -> None:
    with pytest.raises(ValueError):
        localization("../english", tmp_path)
    with pytest.raises(ValueError):
        localization("french", tmp_path)


def test_results_are_independent(tmp_path: Path) -> None:
    _write(tmp_path, "values_l_english.yml", 'foo: "bar"\n')
    first = localization("english", tmp_path)
    first.loc[0, "localization"] = "changed"
    second = localization("english", tmp_path)
    assert second.loc[0, "localization"] == "bar"


def test_unescaped_inner_quotes_are_preserved(tmp_path: Path) -> None:
    _write(
        tmp_path,
        "values_l_english.yml",
        'quote: "He said "hello"." # trailing comment with "quotes"\n',
    )
    frame = localization("english", tmp_path)
    assert frame.loc[0, "localization"] == 'He said "hello".'
