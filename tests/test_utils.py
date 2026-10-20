# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

from pathlib import Path

import pytest

from vic3_analysis import parse_merge


@pytest.mark.parametrize(
    "filename", ["_script_values.info", "README.md", "backup.txt.bak"]
)
def test_parse_merge_ignores_non_script_files(tmp_path: Path, filename: str) -> None:
    (tmp_path / "values.txt").write_text(
        "construction_cost_urban = 450\n", encoding="utf-8"
    )
    (tmp_path / filename).write_text("unwanted_value = 999\n", encoding="utf-8")

    assert parse_merge(tmp_path).to_python() == {"construction_cost_urban": 450}


def test_parse_merge_skips_subdirectories(tmp_path: Path) -> None:
    directory = tmp_path / "nested.txt"
    directory.mkdir()
    (directory / "values.txt").write_text("nested_value = 999\n", encoding="utf-8")

    assert len(parse_merge(tmp_path)) == 0


def test_parse_merge_preserves_script_processing_and_order(tmp_path: Path) -> None:
    (tmp_path / "z_values.txt").write_text("value = 2\n", encoding="utf-8")
    (tmp_path / "a_values.txt").write_text(
        "\ufeffvalue = 1\nconditional ?= 3\ncomparison != 4\n", encoding="utf-8"
    )

    tree = parse_merge(tmp_path)

    assert list(tree.find_all("value")) == [1, 2]
    assert tree["conditional"] == 3
    assert tree["comparison"] == 4
