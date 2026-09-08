"""MkDocs hooks for generated artifact downloads and CSV previews."""

from __future__ import annotations

import csv
import html
import logging
from pathlib import Path
import re

from mkdocs.config.defaults import MkDocsConfig
from mkdocs.structure.files import File, Files
from mkdocs.structure.pages import Page

_LOG = logging.getLogger("mkdocs")
_ROOT = Path(__file__).resolve().parent.parent
_ARTIFACT_DIRS = ("figures", "tables")
_TABLE_PREVIEW = re.compile(
    r"<!--\s*table-preview:\s*(?P<path>[^|]+?)\s*\|\s*"
    r"columns=(?P<columns>[^|]+?)\s*\|\s*rows=(?P<rows>\d+)\s*-->"
)


def on_files(files: Files, config: MkDocsConfig, **kwargs: object) -> Files:
    """Add repository-level generated artifacts to MkDocs' static files."""
    del kwargs
    known = {file.src_uri for file in files}
    for directory in _ARTIFACT_DIRS:
        for path in sorted((_ROOT / directory).rglob("*")):
            if not path.is_file():
                continue
            relative = path.relative_to(_ROOT).as_posix()
            if relative not in known:
                files.append(
                    File(
                        relative,
                        str(_ROOT),
                        config.site_dir,
                        config.use_directory_urls,
                    )
                )
    return files


def _cell(value: str, width: int = 64) -> str:
    """Return a compact, Markdown-safe table cell."""
    compact = " ".join(value.split())
    if len(compact) > width:
        compact = f"{compact[: width - 1]}…"
    return html.escape(compact or "—").replace("|", "\\|")


def _render_preview(relative_path: str, columns_text: str, rows_text: str) -> str:
    """Render one validated CSV preview directive as a Markdown table."""
    path = (_ROOT / relative_path.strip()).resolve()
    tables_root = (_ROOT / "tables").resolve()
    if tables_root not in path.parents or path.suffix.lower() != ".csv":
        raise ValueError(f"table preview path must be a CSV under tables/: {path}")
    if not path.is_file():
        raise ValueError(f"table preview file does not exist: {path}")

    columns = [column.strip() for column in columns_text.split(",") if column.strip()]
    row_limit = int(rows_text)
    if not columns or not 1 <= row_limit <= 20:
        raise ValueError("table previews require columns and between 1 and 20 rows")

    with path.open(encoding="utf-8-sig", newline="") as handle:
        reader = csv.DictReader(handle)
        fieldnames = reader.fieldnames or []
        missing = [column for column in columns if column not in fieldnames]
        if missing:
            raise ValueError(
                f"unknown column(s) in {path.relative_to(_ROOT)}: {', '.join(missing)}"
            )
        rows = []
        for index, row in enumerate(reader):
            if index >= row_limit:
                break
            rows.append([_cell(row.get(column, "")) for column in columns])

    header = f"| {' | '.join(_cell(column) for column in columns)} |"
    divider = f"| {' | '.join('---' for _ in columns)} |"
    body = [f"| {' | '.join(row)} |" for row in rows]
    return "\n".join((header, divider, *body))


def on_page_markdown(
    markdown: str, page: Page, config: MkDocsConfig, **kwargs: object
) -> str:
    """Expand table-preview directives, warning on invalid declarations."""
    del config, kwargs

    def replace(match: re.Match[str]) -> str:
        try:
            return _render_preview(
                match.group("path"), match.group("columns"), match.group("rows")
            )
        except (OSError, ValueError) as error:
            _LOG.warning("%s: %s", page.file.src_uri, error)
            return f'> **Table preview unavailable:** {_cell(str(error))}'

    return _TABLE_PREVIEW.sub(replace, markdown)
