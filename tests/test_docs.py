# Copyright (C) 2026 Brian Li
# SPDX-License-Identifier: GPL-3.0-or-later

"""Documentation structure, artifact coverage, and public API checks."""

import ast
import csv
import re
import tomllib
from collections import Counter
from pathlib import Path

from mkdocs.config import load_config

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SRC_PACKAGE = ROOT / "src" / "vic3_analysis"
SUBMODULE_INIT = "git submodule update --init --recursive"
HISTORICAL_ARTIFACTS = (
    "https://raw.githubusercontent.com/ShabbyGayBar/victoria3-analysis-artifacts/"
    "19fdf73d3453da8c152e29223f826536c8e6b33c/datasets/"
)


def _require_artifact_checkout() -> None:
    """Fail artifact-backed tests with the submodule initialization command."""
    if not (ROOT / "artifacts/.git").exists():
        raise AssertionError(
            "Artifact submodule is not initialized. Run "
            f"`{SUBMODULE_INIT}` from the repository root."
        )


def _registry() -> list[dict[str, object]]:
    """Load and narrow the artifact registry collections."""
    data = tomllib.loads(
        (DOCS / "showcase" / "artifacts.toml").read_text(encoding="utf-8")
    )
    collections = data.get("collection")
    if not isinstance(collections, list):
        raise TypeError("artifact registry must contain [[collection]] entries")
    for collection in collections:
        if not isinstance(collection, dict):
            raise TypeError("each artifact collection must be a table")
    return collections


def _string(collection: dict[str, object], key: str) -> str:
    """Return a required string field from a registry collection."""
    value = collection.get(key)
    if not isinstance(value, str):
        raise TypeError(f"artifact collection {key!r} must be a string")
    return value


def _patterns(collection: dict[str, object]) -> list[str]:
    """Return a collection's artifact patterns after validating them."""
    value = collection.get("artifacts")
    if not isinstance(value, list) or not all(isinstance(item, str) for item in value):
        raise TypeError("artifact collection 'artifacts' must be a string array")
    return value


def _package_exports() -> list[str]:
    """Read literal package exports without importing the package."""
    tree = ast.parse((SRC_PACKAGE / "__init__.py").read_text(encoding="utf-8"))
    for node in tree.body:
        if isinstance(node, ast.Assign) and any(
            isinstance(target, ast.Name) and target.id == "__all__"
            for target in node.targets
        ):
            exports = ast.literal_eval(node.value)
            if not isinstance(exports, list) or not all(
                isinstance(name, str) for name in exports
            ):
                raise TypeError("vic3_analysis.__all__ must be a string list")
            return exports
    raise AssertionError("vic3_analysis.__all__ was not found")


def _export_origins() -> dict[str, tuple[str, str]]:
    """Map re-exported names to their defining module and source name."""
    tree = ast.parse((SRC_PACKAGE / "__init__.py").read_text(encoding="utf-8"))
    origins: dict[str, tuple[str, str]] = {}
    for node in tree.body:
        if not isinstance(node, ast.ImportFrom) or node.module is None:
            continue
        for alias in node.names:
            module, source_name = node.module, alias.name
            path = ROOT / "src" / Path(*module.split("."))
            while path.is_dir():
                package = ast.parse((path / "__init__.py").read_text(encoding="utf-8"))
                imports = [
                    (item.module, name.name)
                    for item in package.body
                    if isinstance(item, ast.ImportFrom) and item.module is not None
                    for name in item.names
                    if (name.asname or name.name) == source_name
                ]
                assert len(imports) == 1, f"cannot resolve {module}.{source_name}"
                module, source_name = imports[0]
                path = ROOT / "src" / Path(*module.split("."))
            origins[alias.asname or alias.name] = (module, source_name)
    return origins


def test_artifact_registry_covers_outputs_and_examples() -> None:
    """Every generated artifact and producer script is registered exactly once."""
    _require_artifact_checkout()
    matches: dict[str, list[str]] = {}
    scripts: set[str] = set()
    for collection in _registry():
        script = _string(collection, "script")
        page = _string(collection, "page")
        scripts.add(script)
        assert (ROOT / script).is_file()
        assert (DOCS / page).is_file()
        for pattern in _patterns(collection):
            resolved = sorted(path for path in ROOT.glob(pattern) if path.is_file())
            assert resolved, f"artifact pattern matched nothing: {pattern}"
            for path in resolved:
                relative = path.relative_to(ROOT).as_posix()
                matches.setdefault(relative, []).append(script)

    expected_artifacts = {
        path.relative_to(ROOT).as_posix()
        for directory in (ROOT / "artifacts/datasets", ROOT / "artifacts/analyses")
        for path in directory.rglob("*")
        if path.is_file() and not path.name.startswith(".")
    }
    assert set(matches) == expected_artifacts
    assert all(len(producers) == 1 for producers in matches.values())

    expected_scripts = {
        path.relative_to(ROOT).as_posix()
        for path in (ROOT / "examples").glob("*.py")
        if path.name != "__init__.py"
    }
    assert scripts == expected_scripts


def test_showcase_pages_reference_registered_outputs() -> None:
    """Each curated showcase page names its producer and resolved artifacts."""
    for collection in _registry():
        script = _string(collection, "script")
        page = _string(collection, "page")
        markdown = (DOCS / page).read_text(encoding="utf-8")
        assert script in markdown
        for pattern in _patterns(collection):
            for path in ROOT.glob(pattern):
                if path.is_file():
                    relative = path.relative_to(ROOT).as_posix()
                    directories = re.findall(
                        r"`(analyses/supply_chains/[^`]+/)`", markdown
                    )
                    documented_directory = any(
                        re.fullmatch(
                            re.escape(directory)
                            .replace(r"<good>", r"[^/]+")
                            .replace(r"<configuration>", r"[^/]+"),
                            path.parent.relative_to(ROOT)
                            .as_posix()
                            .removeprefix("artifacts/")
                            + "/",
                        )
                        for directory in directories
                    )
                    assert relative in markdown or (
                        (
                            documented_directory
                            or path.parent.relative_to(ROOT)
                            .as_posix()
                            .removeprefix("artifacts/")
                            in markdown
                        )
                        and f"`{path.name}`" in markdown
                    )


def test_rankings_editions_link_to_their_own_data() -> None:
    """Edition navigation must not let the archived article consume latest data."""
    latest_name = "production-unit-rankings.md"
    archive_name = "production-unit-rankings-1.13.11.md"
    latest = (DOCS / "showcase" / latest_name).read_text(encoding="utf-8")
    archive = (DOCS / "showcase" / archive_name).read_text(encoding="utf-8")
    assert f"]({archive_name})" in latest
    assert f"]({latest_name})" in archive
    assert "## 相比 1.13.11 的变化" in latest
    assert "date: 2026-09-30" in archive
    assert "game_version: 1.13.11" in archive
    current_csv = "artifacts/datasets/production/production_table.csv"
    historical_csv = f"{HISTORICAL_ARTIFACTS}production/production_table.csv"
    assert f"](../{current_csv})" in latest
    assert f"]({historical_csv})" in archive
    assert f"]({historical_csv})" in latest
    assert current_csv not in archive
    assert "artifacts/datasets/versions/" not in archive + latest
    config = load_config(config_file=str(ROOT / "mkdocs.yml"))
    assert isinstance(config.nav, list)
    showcase = next(
        section["Showcase"]
        for section in config.nav
        if isinstance(section, dict) and "Showcase" in section
    )
    assert isinstance(showcase, list)
    nav_paths = {
        path
        for entry in showcase
        if isinstance(entry, dict)
        for path in entry.values()
        if isinstance(path, str)
    }
    landing = (DOCS / "showcase/index.md").read_text(encoding="utf-8")
    assert config.not_in_nav is not None
    for name in (archive_name, "buy-packages-zh-CN.md"):
        assert f"showcase/{name}" not in nav_paths
        assert config.not_in_nav.match_file(f"showcase/{name}")
        assert f"]({name})" not in landing
    for name in (latest_name, "buy-packages.md"):
        assert f"showcase/{name}" in nav_paths
        assert f"]({name})" in landing
    english = (DOCS / "showcase/buy-packages.md").read_text(encoding="utf-8")
    mandarin = (DOCS / "showcase/buy-packages-zh-CN.md").read_text(encoding="utf-8")
    assert "](buy-packages-zh-CN.md)" in english
    assert "](buy-packages.md)" in mandarin


def test_shared_buy_package_articles_use_commit_pinned_assets() -> None:
    """Historical charts and downloads stay pinned without requiring a history checkout."""
    historical = f"{HISTORICAL_ARTIFACTS}parsed/buy_packages/"
    current = "artifacts/datasets/parsed/buy_packages/"
    metrics = [
        "political_strength",
        "total_popneeds",
        "popneed_simple_clothing",
        "popneed_basic_food",
        "popneed_heating",
        "popneed_household_items",
        "popneed_standard_clothing",
        "popneed_services",
        "popneed_intoxicants",
        "popneed_luxury_drinks",
        "popneed_free_movement",
        "popneed_communication",
        "popneed_luxury_food",
        "popneed_luxury_items",
        "popneed_leisure",
        "popneed_crude_items",
        "popneed_stimulants",
    ]
    for name, preview_heading, exports_heading in (
        (
            "buy-packages.md",
            "### Table preview",
            "### Historical source and current exports",
        ),
        (
            "buy-packages-zh-CN.md",
            "### 数据预览",
            "### 历史来源与当前生成结果",
        ),
    ):
        markdown = (DOCS / "showcase" / name).read_text(encoding="utf-8")
        article, exports = markdown.split(exports_heading)
        assert "1.13.11" in article and "1.15" in article
        assert current not in article
        assert "artifacts/datasets/versions/" not in markdown
        assert "table-preview:" not in article
        assert f"]({historical}buy_packages.csv)" in article
        urls = re.findall(r"https://raw\.githubusercontent\.com/[^\s)]+", article)
        assert urls and all(url.startswith(historical) for url in urls)
        figures = set(
            re.findall(re.escape(historical) + r"figures/([^\s)]+\.svg)", article)
        )
        assert figures == {
            f"{metric}{suffix}.svg" for metric in metrics for suffix in ("", "_log")
        }
        preview = article.split(preview_heading, 1)[1].split("\n### ", 1)[0]
        rows = re.findall(r"^\| (\d+) \|.*$", preview, re.MULTILINE)
        assert rows == ["1", "2", "3", "4", "5"]
        assert f"](../{current}buy_packages.csv)" in exports
        assert "19fdf73d3453da8c152e29223f826536c8e6b33c" in exports


def test_api_reference_covers_package_exports_once() -> None:
    """Every package-level public export has one explicit API directive."""
    directives: list[str] = []
    pattern = re.compile(r"^::: vic3_analysis\.([A-Za-z_]\w*)$", re.MULTILINE)
    for path in (DOCS / "api").glob("*.md"):
        directives.extend(pattern.findall(path.read_text(encoding="utf-8")))
    assert Counter(directives) == Counter(_package_exports())


def test_exported_objects_and_public_methods_have_docstrings() -> None:
    """Require docstrings on exported definitions and their local public methods."""
    origins = _export_origins()
    missing: list[str] = []
    for export in _package_exports():
        module, source_name = origins[export]
        path = ROOT / "src" / Path(*module.split(".")).with_suffix(".py")
        tree = ast.parse(path.read_text(encoding="utf-8"))
        definitions = [
            node
            for node in tree.body
            if isinstance(node, (ast.ClassDef, ast.FunctionDef, ast.AsyncFunctionDef))
            and node.name == source_name
        ]
        assert len(definitions) == 1, f"cannot locate definition for {export}"
        definition = definitions[0]
        if not ast.get_docstring(definition):
            missing.append(export)
        if isinstance(definition, ast.ClassDef):
            for member in definition.body:
                if (
                    isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef))
                    and (not member.name.startswith("_") or member.name == "__init__")
                    and not ast.get_docstring(member)
                ):
                    missing.append(f"{export}.{member.name}")
    assert not missing, f"missing public docstrings: {', '.join(missing)}"


def _dictionary_columns(page: str, section: str | None = None) -> set[str]:
    """Read named first-column entries, requiring complete four-cell rows."""
    markdown = (DOCS / "data-dictionary" / page).read_text(encoding="utf-8")
    if section is not None:
        heading = f"## {section}\n"
        assert heading in markdown, f"missing dictionary section: {section}"
        markdown = markdown.split(heading, 1)[1].split("\n## ", 1)[0]
    columns: set[str] = set()
    for line in markdown.splitlines():
        if not line.startswith("| `"):
            continue
        cells = [cell.strip() for cell in line.strip("|").split("|")]
        assert len(cells) == 4 and all(cells), f"incomplete dictionary row: {line}"
        match = re.fullmatch(r"`([^`]+)`", cells[0])
        assert match is not None, f"invalid dictionary column name: {cells[0]}"
        assert match[1] not in columns, f"duplicate column in {section}: {match[1]}"
        columns.add(match[1])
    return columns


def _schema_assignment(relative: str, name: str) -> ast.expr:
    """Locate one schema assignment without importing parsers or examples."""
    tree = ast.parse((ROOT / relative).read_text(encoding="utf-8"))
    values = [
        node.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Assign)
        and any(
            isinstance(target, ast.Name) and target.id == name
            for target in node.targets
        )
    ]
    assert len(values) == 1, f"cannot locate unique schema: {relative}:{name}"
    return values[0]


def _assert_columns_documented(columns: set[str], entries: set[str]) -> None:
    """Match fixed names or placeholder families against actual column names."""
    patterns = [
        re.compile(re.sub(r"<[^>]+>", ".+", re.escape(entry))) for entry in entries
    ]
    missing = {
        column
        for column in columns
        if not any(pattern.fullmatch(column) for pattern in patterns)
    }
    assert not missing, f"undocumented columns: {sorted(missing)}"


def test_dictionary_covers_supply_chain_schemas() -> None:
    """Each detailed report and summary exactly documents its fixed schema."""
    relative = "src/vic3_analysis/analysis/supply_chain/result.py"
    schemas = {
        "Summary": "SUMMARY_FIELDS",
        "Processes": "PROCESS_COLUMNS",
        "Goods": "GOOD_COLUMNS",
        "Flows": "FLOW_COLUMNS",
        "Workforce": "WORKFORCE_COLUMNS",
        "Constraints and bottlenecks": "CONSTRAINT_COLUMNS",
        "Alternatives": "ALTERNATIVE_COLUMNS",
    }
    for section, name in schemas.items():
        columns = ast.literal_eval(_schema_assignment(relative, name))
        assert isinstance(columns, list) and all(
            isinstance(column, str) for column in columns
        )
        assert _dictionary_columns("supply-chain.md", section) == set(columns)
    sweep_columns = _schema_assignment(
        "src/vic3_analysis/analysis/supply_chain/sweep.py", "SWEEP_COLUMNS"
    )
    sweep_prefix = {
        node.value
        for node in ast.walk(sweep_columns)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    assert (
        _dictionary_columns("supply-chain.md", "Sweep summary and failures")
        == sweep_prefix
    )


def test_dictionary_covers_analytical_csv_headers() -> None:
    """Analytical CSVs have no uncovered columns, including dynamic families."""
    _require_artifact_checkout()
    for filename, page, sections in (
        ("datasets/production/production_table.csv", "production.md", ()),
        (
            "analyses/supply_chains/comparison/summary.csv",
            "supply-chain.md",
            (
                "Summary",
                "Resource building levels",
                "Sweep summary and failures",
                "Example CSV additions",
            ),
        ),
        (
            "analyses/supply_chains/cangshulun_video/summary.csv",
            "supply-chain.md",
            (
                "Summary",
                "Resource building levels",
                "Sweep summary and failures",
                "Example CSV additions",
            ),
        ),
        (
            "analyses/optimization/japan/employment_sweep.csv",
            "economy.md",
            ("Japan optimization comparison",),
        ),
        (
            "analyses/optimization/equilibrium/summary.csv",
            "economy.md",
            ("Equilibrium optimization summary",),
        ),
        (
            "analyses/optimization/equilibrium/buildings.csv",
            "economy.md",
            ("Building registry", "Historical building registry"),
        ),
    ):
        entries = (
            set().union(*(_dictionary_columns(page, section) for section in sections))
            if sections
            else _dictionary_columns(page)
        )
        with (ROOT / "artifacts" / filename).open(
            encoding="utf-8", newline=""
        ) as handle:
            columns = set(next(csv.reader(handle)))
        # Keep saved artifacts unchanged while checking the current summary schema.
        if filename == "analyses/optimization/equilibrium/summary.csv":
            columns = {
                "min_goods_balance" if column == "default_min_goods_output" else column
                for column in columns
            }
        _assert_columns_documented(columns, entries)


def test_dictionary_covers_optional_production_fields() -> None:
    """Source-defined metadata/enrichments remain covered beyond snapshot headers."""
    relative = "src/vic3_analysis/analysis/production.py"
    order = _schema_assignment(relative, "column_order")
    columns = {
        node.value
        for node in ast.walk(order)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    defaults = _schema_assignment(relative, "building_metadata_defaults")
    assert isinstance(defaults, ast.Dict)
    columns.update(
        key.value
        for key in defaults.keys
        if isinstance(key, ast.Constant) and isinstance(key.value, str)
    )
    _assert_columns_documented(columns, _dictionary_columns("production.md"))


def test_dictionary_covers_economy_report_columns() -> None:
    """Public state export dictionaries have a complete table-specific reference."""
    tree = ast.parse(
        (SRC_PACKAGE / "analysis" / "economy" / "reports.py").read_text(
            encoding="utf-8"
        )
    )
    for method, section in (
        ("df_buildings", "Building registry"),
        ("df_market", "Market report"),
        ("df_pop", "Population report"),
    ):
        functions = [
            node
            for node in ast.walk(tree)
            if isinstance(node, ast.FunctionDef) and node.name == method
        ]
        assert len(functions) == 1
        columns = {
            key.value
            for node in ast.walk(functions[0])
            if isinstance(node, ast.Dict)
            for key in node.keys
            if isinstance(key, ast.Constant) and isinstance(key.value, str)
        }
        for node in ast.walk(functions[0]):
            if isinstance(node, ast.DictComp) and isinstance(node.key, ast.JoinedStr):
                parts: list[str] = []
                for part in node.key.values:
                    if isinstance(part, ast.Constant) and isinstance(part.value, str):
                        parts.append(part.value)
                    else:
                        assert isinstance(part, ast.FormattedValue)
                        assert isinstance(part.value, ast.Name)
                        parts.append(f"<{part.value.id}>")
                columns.add("".join(parts))
        assert columns
        assert _dictionary_columns("economy.md", section) == columns


def test_dictionary_covers_normalized_parser_columns() -> None:
    """Explicit population-need and buy-package schemas are fully documented."""
    tree = ast.parse(
        (SRC_PACKAGE / "parse" / "pop_needs.py").read_text(encoding="utf-8")
    )
    columns_lists = [
        keyword.value
        for node in ast.walk(tree)
        if isinstance(node, ast.Call)
        for keyword in node.keywords
        if keyword.arg == "columns"
    ]
    assert len(columns_lists) == 1
    columns = ast.literal_eval(columns_lists[0])
    assert isinstance(columns, list)
    assert _dictionary_columns("parsers.md", "Population needs") == set(columns)
    fieldnames = _schema_assignment(
        "src/vic3_analysis/parse/buy_packages.py", "fieldnames"
    )
    columns = {
        node.value
        for node in ast.walk(fieldnames)
        if isinstance(node, ast.Constant) and isinstance(node.value, str)
    }
    columns.add("popneed_<need>")
    assert _dictionary_columns("parsers.md", "Buy packages") == columns
