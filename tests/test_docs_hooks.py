# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Validate publishing and previews without requiring generated snapshots."""

from pathlib import Path

import pytest
from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import File, Files
from mkdocs.structure.pages import Page

from docs import hooks


@pytest.fixture
def artifact_root(tmp_path: Path, monkeypatch: pytest.MonkeyPatch) -> Path:
    """Give publishing hooks an isolated repository with no real snapshots."""
    monkeypatch.setattr(hooks, "_ROOT", tmp_path)
    return tmp_path


def _write(root: Path, relative: str, content: str) -> Path:
    path = root / relative
    path.parent.mkdir(parents=True, exist_ok=True)
    path.write_text(content, encoding="utf-8")
    return path


def _config(root: Path) -> MkDocsConfig:
    config = MkDocsConfig()
    if not isinstance(config, MkDocsConfig):
        raise TypeError("Expected a MkDocsConfig instance")
    config.load_dict({"site_name": "Test", "site_dir": str(root / "site")})
    return config


def test_collects_only_new_collections_without_duplicates(artifact_root: Path) -> None:
    """Keep published paths stable and exclude legacy and escaped files."""
    relative = "artifacts/datasets/parsed/goods.csv"
    _write(artifact_root, relative, "key,cost\nwood,20\n")
    _write(artifact_root, "artifacts/analyses/study/network.svg", "<svg/>")
    outside = _write(artifact_root, "private.csv", "secret\nvalue\n")
    for legacy in (
        "tables/goods.csv",
        "figures/network.svg",
        "artifacts/tables/goods.csv",
        "artifacts/figures/network.svg",
        "artifacts/README.md",
        "artifacts/datasets/.hidden.csv",
        "artifacts/datasets/.cache/ignored.csv",
    ):
        _write(artifact_root, legacy, "ignored")
    (artifact_root / "artifacts/datasets/escape.csv").symlink_to(outside)
    config = _config(artifact_root)
    files = Files([File(relative, str(artifact_root), config.site_dir, True)])
    hooks.on_files(files, config)
    hooks.on_files(files, config)
    assert sorted(file.src_uri for file in files) == [
        "artifacts/analyses/study/network.svg",
        relative,
    ]


def test_missing_collections_are_not_created(artifact_root: Path) -> None:
    files = hooks.on_files(Files([]), _config(artifact_root))
    assert list(files) == []
    assert not (artifact_root / "artifacts").exists()


@pytest.mark.parametrize("collection", ["datasets/parsed", "analyses/study"])
def test_preview_reads_each_collection_and_escapes_cells(
    artifact_root: Path, collection: str
) -> None:
    relative = f"artifacts/{collection}/goods.csv"
    _write(artifact_root, relative, 'key,cost\n"<wood>| plank",20\niron,40\n')
    preview = hooks._render_preview(relative, "key,cost", "1")
    assert preview == ("| key | cost |\n| --- | --- |\n| &lt;wood&gt;\\| plank | 20 |")
    assert "iron" not in preview


@pytest.mark.parametrize(
    "relative",
    [
        "tables/goods.csv",
        "artifacts/tables/goods.csv",
        "artifacts/datasets/../../private.csv",
        "artifacts/datasets/parsed/chart.svg",
        "private.csv",
    ],
)
def test_preview_rejects_paths_outside_collections_or_non_csv(
    artifact_root: Path, relative: str
) -> None:
    with pytest.raises(ValueError, match="CSV under artifacts/datasets/"):
        hooks._render_preview(relative, "key", "1")


def test_preview_rejects_symlink_escape(artifact_root: Path) -> None:
    outside = _write(artifact_root, "private.csv", "key\nprivate\n")
    directory = artifact_root / "artifacts/datasets/parsed"
    directory.mkdir(parents=True)
    (directory / "escape.csv").symlink_to(outside)
    with pytest.raises(ValueError, match="CSV under artifacts/datasets/"):
        hooks._render_preview("artifacts/datasets/parsed/escape.csv", "key", "1")


@pytest.mark.parametrize(
    ("columns", "rows", "message"),
    [
        ("unknown", "1", "unknown column"),
        ("", "1", "require columns"),
        ("key", "0", "between 1 and 20"),
        ("key", "21", "between 1 and 20"),
    ],
)
def test_preview_retains_validation(
    artifact_root: Path, columns: str, rows: str, message: str
) -> None:
    relative = "artifacts/datasets/parsed/goods.csv"
    _write(artifact_root, relative, "key\nwood\n")
    with pytest.raises(ValueError, match=message):
        hooks._render_preview(relative, columns, rows)


def test_missing_preview_reports_actionable_failure(
    artifact_root: Path, caplog: pytest.LogCaptureFixture
) -> None:
    config = _config(artifact_root)
    page = Page(
        "Test",
        File("showcase/test.md", str(artifact_root), config.site_dir, True),
        config,
    )
    relative = "artifacts/datasets/parsed/missing.csv"
    with pytest.raises(ValueError, match="file does not exist"):
        hooks._render_preview(relative, "key", "1")
    rendered = hooks.on_page_markdown(
        f"<!-- table-preview: {relative} | columns=key | rows=1 -->", page, config
    )
    assert "Table preview unavailable" in rendered
    assert relative in caplog.text
    assert "file does not exist" in caplog.text
