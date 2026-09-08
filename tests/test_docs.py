"""Documentation structure, artifact coverage, and public API checks."""

import ast
from collections import Counter
from pathlib import Path
import re
import tomllib

ROOT = Path(__file__).resolve().parent.parent
DOCS = ROOT / "docs"
SRC_PACKAGE = ROOT / "src" / "vic3_analysis"


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
            origins[alias.asname or alias.name] = (node.module, alias.name)
    return origins


def test_artifact_registry_covers_outputs_and_examples() -> None:
    """Every generated artifact and producer script is registered exactly once."""
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
        for directory in (ROOT / "tables", ROOT / "figures")
        for path in directory.rglob("*")
        if path.is_file()
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
                    assert relative in markdown


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
                if isinstance(member, (ast.FunctionDef, ast.AsyncFunctionDef)) and (
                    not member.name.startswith("_") or member.name == "__init__"
                ):
                    if not ast.get_docstring(member):
                        missing.append(f"{export}.{member.name}")
    assert not missing, f"missing public docstrings: {', '.join(missing)}"
